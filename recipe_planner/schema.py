"""Recipe input contract derived from the executable ProcessStep definitions."""
from __future__ import annotations

import math
from numbers import Real


def step_schema(material_db=None):
    import tcad_simulator as tcad
    db = material_db or tcad.MaterialDatabase()
    result = {
        name: {
            spec.key: {"type": spec.type, "default": spec.default,
                       "minimum": spec.minimum, "maximum": spec.maximum,
                       "choices": list(dict.fromkeys([choice[0] for choice in spec.choices or []] + ([spec.default] if spec.type == "enum" else []))),
                       "units": spec.units}
            for spec in factory(db).parameter_specs()
        }
        for name, factory in tcad.PROCESS_STEP_FACTORIES.items()
    }
    # CMP's structured editor is an existing extension to ParameterSpec.
    result["CMP"]["selectivity_pairs"] = {"type": "pairs", "default": tcad.PROCESS_STEP_FACTORIES["CMP"](db).params["selectivity_pairs"]}
    result["CMP"]["selectivity"] = {"type": "text", "default": ""}
    return result


def normalize_params(name, params):
    """Only migrate aliases with identical physical meaning; never guess rates."""
    if not isinstance(params, dict):
        raise ValueError("params 必须是对象")
    result = dict(params)
    aliases = {}
    if name in ("Deposition", "Selective Epitaxy"):
        aliases["thickness_nm"] = "thickness"
    if name == "Mask Exposure":
        aliases["cd_nm"] = "critical_dimension"
    for old, new in aliases.items():
        if old in result:
            if new in result and result[new] != result[old]:
                raise ValueError(f"参数 {old} 与 {new} 冲突")
            result[new] = result.pop(old)
    return result


def parameter_errors(name, params, schema=None, material_db=None):
    schema = schema if schema is not None else step_schema(material_db)
    if not isinstance(name, str) or name not in schema:
        return [f"未知步骤类型 {name}"]
    try:
        params = normalize_params(name, params)
    except ValueError as exc:
        return [str(exc)]
    errors = []
    for key, value in params.items():
        spec = schema[name].get(key)
        if spec is None:
            if name == "Etch" and key == "depth_nm":
                errors.append("Etch 不接受目标深度 depth_nm；请指定刻蚀时间 time（秒）和适用速率/模型，不能将深度当成时间")
            else:
                errors.append(f"未知参数 {key}")
            continue
        if spec["type"] in ("float", "int"):
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                errors.append(f"参数 {key} 必须是有限数值")
                continue
            if spec["type"] == "int" and int(value) != value:
                errors.append(f"参数 {key} 必须是整数")
            if ((spec["minimum"] is not None and value < spec["minimum"]) or
                    (spec["maximum"] is not None and value > spec["maximum"])):
                errors.append(f"参数 {key}={value} 超出范围 [{spec['minimum']}, {spec['maximum']}]")
        elif spec["type"] == "enum" and value not in spec["choices"]:
            # Legacy serialized recipes can contain material IDs.
            import tcad_simulator as tcad
            db = material_db or tcad.MaterialDatabase()
            resolved = tcad._resolve_material_name_any(db, value) if "material" in key else None
            if resolved not in spec["choices"]:
                errors.append(f"参数 {key}={value!r} 不在允许值中")
        elif spec["type"] == "bool" and not isinstance(value, bool):
            errors.append(f"参数 {key} 必须是布尔值")
        elif spec["type"] == "text" and not isinstance(value, str):
            errors.append(f"参数 {key} 必须是字符串")
        elif spec["type"] == "pairs":
            import tcad_simulator as tcad
            db = material_db or tcad.MaterialDatabase()
            if not isinstance(value, list):
                errors.append(f"参数 {key} 必须是材料/选择比数组")
            else:
                for pair in value:
                    if not isinstance(pair, dict) or not tcad._resolve_material_name_any(db, pair.get("material")):
                        errors.append(f"参数 {key} 包含未知材料")
                        continue
                    ratio = pair.get("ratio")
                    if isinstance(ratio, bool) or not isinstance(ratio, Real) or not math.isfinite(ratio) or ratio < 0:
                        errors.append(f"参数 {key} 的 ratio 必须是有限非负数")
    return errors


def validate_import(blob, material_db):
    """Preflight before autosave/reset; no replacement with a default recipe."""
    for domain_key in ("domain", "model"):
        domain = blob.get(domain_key, {})
        if not isinstance(domain, dict):
            raise ValueError(f"{domain_key} 必须是对象")
        if "grid_shape" in domain:
            shape = domain["grid_shape"]
            if not isinstance(shape, (list, tuple)) or len(shape) != 3 or any(isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in shape):
                raise ValueError("domain.grid_shape 必须是三个正整数")
        if "voxel_size_nm" in domain:
            voxel = domain["voxel_size_nm"]
            if isinstance(voxel, bool) or not isinstance(voxel, Real) or not math.isfinite(voxel) or voxel <= 0:
                raise ValueError("domain.voxel_size_nm 必须是有限正数")
    steps = next((blob[k] for k in ("steps_full", "steps", "recipe") if isinstance(blob.get(k), list)), None)
    if not steps:
        raise ValueError("导入配方必须包含非空步骤列表")
    schema = step_schema(material_db)
    domain = blob.get("domain") or blob.get("model") or {}
    if isinstance(domain, dict) and isinstance(domain.get("grid_shape"), (list, tuple)) and isinstance(domain.get("voxel_size_nm"), Real):
        capacity_nm = domain["grid_shape"][2] * domain["voxel_size_nm"]
        for step in steps:
            if isinstance(step, dict) and step.get("name") == "Initialize Wafer":
                thickness = (step.get("params_raw") or step.get("params") or {}).get("thickness_nm", 200.0)
                if isinstance(thickness, Real) and math.isfinite(thickness) and thickness > capacity_nm:
                    raise ValueError("Initialize Wafer 厚度超出配方 domain 的 Z 高度")
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"步骤 {i+1} 必须是对象")
        name = step.get("name")
        if name == "Mask Exposure" and "custom_mask" in step:
            import numpy as np
            try:
                mask = np.asarray(step["custom_mask"])
                valid = mask.ndim == 2 and mask.size > 0 and mask.dtype.kind in "biuf" and np.isfinite(mask).all() and np.isin(mask, [0, 1]).all()
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError(f"步骤 {i+1}: custom_mask 必须是非空二维 0/1 掩膜")
        params = step.get("params_raw") or step.get("params", {})
        # Files and mask labels are existing serialized exposure metadata.
        checked = {k: v for k, v in params.items() if not (name == "Mask Exposure" and k in ("mask_file", "mask_name"))} if isinstance(params, dict) else params
        errors = parameter_errors(name, checked, schema, material_db)
        if errors:
            raise ValueError(f"步骤 {i+1} ({name}): {'; '.join(errors)}")
