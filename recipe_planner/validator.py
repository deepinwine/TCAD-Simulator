# -*- coding: utf-8 -*-
"""M16：候选 Recipe 校验器——步骤类型/参数/材料/单位/顺序/后端能力。"""
from __future__ import annotations

from typing import Any, Dict, List

from .parser import RecipeDraft


class RecipeValidator:
    """校验候选 Recipe 的合法性。"""

    # 已知合法步骤类型（来自 PROCESS_STEP_FACTORIES）
    KNOWN_STEPS = {
        "Initialize Wafer", "Spin Resist", "Mask Exposure",
        "Post-Exposure Bake", "Resist Develop", "Etch",
        "Selective Epitaxy", "Deposition", "CMP", "Anneal",
        "Oxidation", "Ion Implantation", "Wet Etch",
        "Wafer Flip", "Bonding", "Thinning",
    }

    # 参数约束
    PARAM_CONSTRAINTS: Dict[str, Dict[str, tuple]] = {
        "Initialize Wafer": {
            "thickness_nm": (1, 10000),
        },
        "Deposition": {
            "thickness_nm": (0.1, 10000),
        },
        "Etch": {
            "depth_nm": (0.1, 10000),
        },
        "CMP": {
            "target": (1, 10000),
        },
    }

    # ViennaPS 后端能力（简化版——完整版见 ViennaPSBackend.capabilities()）
    ACCURATE_SUPPORT = {
        "Initialize Wafer": True,
        "Etch": True,  # Dry + Wet
        "Wet Etch": True,
        "Resist Develop": True,
        "Deposition": True,  # conformal
        "Selective Epitaxy": "experimental",
        "CMP": False,
        "Anneal": False,
        "Ion Implantation": False,
        "Wafer Flip": False,
        "Bonding": False,
        "Thinning": False,
        "Spin Resist": False,
        "Mask Exposure": False,
        "Post-Exposure Bake": False,
    }

    def validate(self, draft: RecipeDraft) -> Dict[str, Any]:
        """返回 {ok, errors, warnings, mode_recommendations}。"""
        errors: List[str] = []
        warnings: List[str] = []
        recommendations: List[Dict[str, str]] = []

        for i, step in enumerate(draft.steps):
            prefix = f"步骤 {i+1} ({step.type})"

            # 1. 步骤类型合法
            if step.type not in self.KNOWN_STEPS:
                errors.append(f"{prefix}: 未知步骤类型 '{step.type}'")
                continue

            # 2. 参数范围
            constraints = self.PARAM_CONSTRAINTS.get(step.type, {})
            for param, (lo, hi) in constraints.items():
                if param in step.params:
                    value = step.params[param]
                    if isinstance(value, (int, float)):
                        if not (lo <= value <= hi):
                            errors.append(
                                f"{prefix}: 参数 {param}={value} 超出范围 [{lo}, {hi}]"
                            )

            # 3. 步骤内在 warnings
            for w in step.warnings:
                warnings.append(f"{prefix}: {w}")

            # 4. 后端能力建议
            if step.type in self.ACCURATE_SUPPORT:
                support = self.ACCURATE_SUPPORT[step.type]
                if support is False:
                    recommendations.append({
                        "step": step.type,
                        "recommended_mode": "fast",
                        "reason": "ViennaPS 不支持此工艺",
                    })
                elif support == "experimental":
                    recommendations.append({
                        "step": step.type,
                        "recommended_mode": "auto",
                        "reason": "ViennaPS 实验性支持，可能回退 Fast",
                    })
                elif support is True:
                    recommendations.append({
                        "step": step.type,
                        "recommended_mode": "accurate",
                        "reason": "ViennaPS 支持",
                    })

        # 5. 顺序逻辑
        step_types = [s.type for s in draft.steps]
        if "CMP" in step_types:
            cmp_idx = step_types.index("CMP")
            if cmp_idx == 0:
                errors.append("CMP 不能是第一个步骤")
            else:
                prior_types = step_types[:cmp_idx]
                if not any(t in ("Deposition", "Oxidation", "Selective Epitaxy") for t in prior_types):
                    warnings.append("CMP 前面没有沉积步骤——可能没有可平坦化的材料")

        if "Etch" in step_types:
            etch_idx = step_types.index("Etch")
            if etch_idx == 0:
                errors.append("Etch 不能是第一个步骤（需要先有 Initialize）")

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "mode_recommendations": recommendations,
        }
