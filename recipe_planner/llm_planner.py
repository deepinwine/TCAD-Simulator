# -*- coding: utf-8 -*-
"""M31: Schema-guided LLM Recipe Planner.

双模式：简单工艺走规则 parser，复杂工艺走 LLM planner。
LLM 只输出 RecipeDraft JSON——绝不直接调用 ProcessModel。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .normalizer import MaterialNormalizer, UnitNormalizer
from .parser import PlannedStep, RecipeDraft, RecipePlanner
from .validator import RecipeValidator


def build_llm_prompt(text: str) -> str:
    """构建基于真实 schema 的 LLM prompt（不维护静态步骤表）。"""
    import tcad_simulator as tcad

    factories = sorted(tcad.PROCESS_STEP_FACTORIES.keys())
    db = tcad.MaterialDatabase()
    materials = sorted(m.name for m in db.materials_all()) if hasattr(db, 'materials_all') else sorted(set(m.name for _, m in db.items()))

    schema = {
        "available_step_types": factories,
        "available_materials": materials,
        "units": "All lengths in nm, times in seconds, temperatures in °C",
        "output_schema": {
            "steps": [
                {
                    "type": "string (must be one of available_step_types)",
                    "params": "dict of parameter name → value",
                    "confidence": "float 0-1",
                    "sourceSpan": "source text fragment",
                    "assumptions": ["list of assumptions made"],
                }
            ],
            "ambiguities": ["list of unclear/missing information"],
            "warnings": ["list of potential issues"],
        },
        "rules": [
            "Every step type MUST be from available_step_types",
            "Every material MUST be from available_materials or a valid alias",
            "All lengths MUST be in nm",
            "All times MUST be in seconds",
            "Do NOT invent steps not mentioned in the input",
            "Flag missing information as ambiguities, do NOT hallucinate defaults silently",
            "Output ONLY valid JSON matching output_schema, no markdown",
        ],
    }

    return (
        f"You are a semiconductor process recipe planner. "
        f"Convert the user's process description into a structured recipe.\n\n"
        f"Schema:\n{json.dumps(schema, indent=2)}\n\n"
        f"User input:\n{text}\n\n"
        f"Output ONLY the JSON, no other text:"
    )


def parse_llm_response(response_text: str) -> RecipeDraft:
    """解析 LLM 输出的 JSON → RecipeDraft。失败返回带 error 的 draft。"""
    # 尝试提取 JSON（LLM 可能包裹 markdown）
    text = response_text.strip()
    if text.startswith("```"):
        # Remove markdown code fences
        lines = text.split("\n")
        json_lines = []
        in_json = False
        for line in lines:
            if line.strip() == "```json" or line.strip() == "```":
                if in_json:
                    break
                in_json = True
                continue
            if in_json:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        draft = RecipeDraft(source_text=response_text[:200])
        draft.warnings.append(f"LLM 输出不是有效 JSON: {exc}")
        return draft

    draft = RecipeDraft(source_text=data.get("sourceText", ""))
    normalizer = MaterialNormalizer()
    units = UnitNormalizer()

    for step_data in data.get("steps", []):
        step_type = str(step_data.get("type", ""))
        params = step_data.get("params", {})

        # Normalize material names
        if "material" in params:
            canonical, ambiguous = normalizer.normalize(str(params["material"]))
            if canonical:
                params["material"] = canonical
            if ambiguous:
                step_data.setdefault("warnings", []).append(
                    f"Material '{params['material']}' is ambiguous"
                )

        # Normalize length units to nm
        for key in ("thickness_nm", "depth_nm", "cd_nm", "width_nm"):
            if key in params and isinstance(params[key], (int, float)):
                params[key] = float(params[key])

        planned = PlannedStep(
            type=step_type,
            params=params,
            confidence=float(step_data.get("confidence", 0.5)),
            source_span=str(step_data.get("sourceSpan", "")),
            warnings=step_data.get("warnings", []),
            is_default=bool(step_data.get("assumptions")),
        )
        draft.steps.append(planned)

    draft.ambiguities = data.get("ambiguities", [])
    draft.warnings.extend(data.get("warnings", []))

    # Validate
    validator = RecipeValidator()
    validation = validator.validate(draft)
    if not validation["ok"]:
        draft.warnings.extend(validation["errors"])

    return draft


def is_complex(text: str) -> bool:
    """判断是否需要 LLM（vs 规则 parser 足够）。"""
    complex_keywords = [
        "SADP", "spacer", "侧墙", "芯轴", "自对准", "self-aligned",
        "键合", "翻转", "减薄", "bond", "flip", "thin",
        "嵌套", "nested", "多重", "multi",
        "dual damascene", "双大马士革",
        "selective", "选择性", "外延", "epitaxy",
    ]
    lower = text.lower()
    if any(kw.lower() in lower for kw in complex_keywords):
        return True
    # More than 8 steps → complex
    rule_result = RecipePlanner().parse(text)
    return len(rule_result.steps) > 8


def plan_recipe(
    text: str,
    llm_fn: Optional[Any] = None,
) -> RecipeDraft:
    """双模式入口：简单→规则，复杂→LLM（如果有）。"""
    if not is_complex(text):
        return RecipePlanner().parse(text)

    if llm_fn is None:
        # 无 LLM 时 fallback 到规则 parser + 复杂警告
        draft = RecipePlanner().parse(text)
        draft.warnings.append(
            "检测到复杂工艺描述，但无 LLM 可用——使用规则解析器（可能遗漏细节）"
        )
        return draft

    # LLM path
    prompt = build_llm_prompt(text)
    response = llm_fn(prompt)
    return parse_llm_response(response)
