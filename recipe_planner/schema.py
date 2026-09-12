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


def validate_wafer_stack(params, *, capacity_nm=None):
    """Validate coupled Initialize Wafer thicknesses before any model reset."""
    if not isinstance(params, dict):
        raise ValueError("Initialize Wafer params 必须是对象")

    def finite_nonnegative(key, default):
        value = params.get(key, default)
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"Initialize Wafer 参数 {key} 必须是数值")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Initialize Wafer 参数 {key} 必须是有限非负数")
        return float(value)

    total_nm = finite_nonnegative("thickness_nm", 200.0)
    if capacity_nm is not None and total_nm > float(capacity_nm):
        raise ValueError("Initialize Wafer 厚度超出配方 domain 的 Z 高度")

    box_nm = finite_nonnegative("box_thickness_nm", 0.0)
    device_nm = finite_nonnegative("device_thickness_nm", 0.0)
    wafer_type = str(params.get("wafer_type", "Bulk") or "Bulk").strip()
    if wafer_type == "SOI" and (box_nm > 0.0 or device_nm > 0.0):
        if box_nm + device_nm >= total_nm:
            raise ValueError("SOI 的 BOX 与 device 厚度之和必须小于总厚度，以保留 handle 层")
    return total_nm, box_nm, device_nm


def _import_steps(blob):
    """Use the first non-empty legacy/current recipe list, in wire priority order."""
    for key in ("steps_full", "steps", "recipe"):
        value = blob.get(key)
        if isinstance(value, list) and value:
            return value
    raise ValueError("导入配方必须包含非空步骤列表")


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
    steps = _import_steps(blob)
    schema = step_schema(material_db)
    domain = blob.get("domain") or blob.get("model") or {}
    capacity_nm = None
    if (isinstance(domain, dict)
            and isinstance(domain.get("grid_shape"), (list, tuple))
            and isinstance(domain.get("voxel_size_nm"), Real)):
        capacity_nm = domain["grid_shape"][2] * domain["voxel_size_nm"]
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"步骤 {i+1} 必须是对象")
        name = step.get("name")
        if name == "Mask Exposure":
            for key in ("mask_file", "mask_name"):
                if key in step and not isinstance(step[key], str):
                    raise ValueError(f"步骤 {i+1}: {key} 必须是字符串")
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
        checked = params
        if name == "Initialize Wafer":
            validate_wafer_stack(checked, capacity_nm=capacity_nm)
        errors = parameter_errors(name, checked, schema, material_db)
        if errors:
            raise ValueError(f"步骤 {i+1} ({name}): {'; '.join(errors)}")


def prepare_import(blob, material_db, *, grid_shape, voxel_size_nm, threads=1, runtime=None):
    """Build a fully validated candidate without changing the active session."""
    from copy import deepcopy
    from pathlib import Path
    import tcad_simulator as tcad
    tcad = runtime or tcad
    candidate_blob = deepcopy(blob)
    validate_import(candidate_blob, material_db)
    domain = candidate_blob.get("domain") or {}
    legacy_model = candidate_blob.get("model") or {}
    effective = {
        "grid_shape": domain.get("grid_shape") or legacy_model.get("grid_shape") or list(grid_shape),
        "voxel_size_nm": domain.get("voxel_size_nm") or legacy_model.get("voxel_size_nm") or voxel_size_nm,
        "threads": domain.get("threads") or legacy_model.get("threads") or threads,
    }
    candidate_blob["domain"] = effective
    validate_import(candidate_blob, material_db)
    count = effective["threads"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("domain.threads 必须是正整数")
    blobs = _import_steps(candidate_blob)
    rebuilt = []
    for data in blobs:
        step = tcad._webui_deserialize_step(data, material_db)
        if step is None:
            raise ValueError("Unknown process step")
        if isinstance(step, tcad.ExposureStep):
            path = step.params.get("mask_file")
            if path:
                source = Path(path).expanduser()
                if not source.is_file():
                    raise ValueError(f"Mask file not found: {path}")
                step.image_mask = tcad.load_mask_from_file(str(source))
            elif step.params.get("mask_mode") in ("Custom", "Designer", "Image") and step.custom_mask is None:
                raise ValueError("Custom Mask Exposure requires a mask file or embedded mask")
        rebuilt.append(step)
    candidate = tcad.ProcessModel(material_db, grid_shape=tuple(effective["grid_shape"]),
                                  voxel_size_nm=effective["voxel_size_nm"], max_workers=count)
    return candidate, rebuilt
