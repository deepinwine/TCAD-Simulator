# -*- coding: utf-8 -*-
"""M16：规则式自然语言工艺配方解析器。

中英文混合半导体术语 → 结构化候选 Recipe（含置信度/歧义/来源片段）。
LLM 为可选增强，不依赖。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .normalizer import MaterialNormalizer, UnitNormalizer

# ---- 工艺步骤同义词表 ----

PROCESS_SYNONYMS: dict[str, list[str]] = {
    "Initialize Wafer": ["initialize", "init", "初始", "衬底", "substrate", "wafer", "晶圆"],
    "Deposition": ["deposit", "deposition", "沉积", "淀积", "淀", "cvd", "ald", "沉积层", "生长"],
    "Etch": ["etch", "etching", "刻蚀", "蚀刻", "dry etch", "wet etch", "等离子体刻蚀"],
    "Mask Exposure": ["lithography", "exposure", "光刻", "曝光", "pattern", "图形", "掩膜", "photolithography"],
    "CMP": ["cmp", "化学机械抛光", "平坦化", "planarization", "polish", "抛光"],
    "Anneal": ["anneal", "annealing", "退火", "热处理"],
    "Oxidation": ["oxidation", "oxidize", "氧化", "thermal oxidation", "热氧化"],
    "Spin Resist": ["spin", "coat", "涂胶", "旋涂", "spin coat", "涂布光刻胶"],
    "Resist Develop": ["develop", "development", "显影", "去胶", "strip"],
    "Ion Implantation": ["implant", "implantation", "注入", "离子注入"],
    "Selective Epitaxy": ["epitaxy", "selective epitaxy", "外延", "选择生长"],
    "Fill": ["fill", "填充", "填满"],
}


@dataclass
class PlannedStep:
    """解析出的候选步骤。"""
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    source_span: str = ""
    warnings: List[str] = field(default_factory=list)
    is_default: bool = False  # 参数是自动填充的默认值


@dataclass
class RecipeDraft:
    """结构化候选 Recipe。"""
    source_text: str = ""
    steps: List[PlannedStep] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    normalization_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "sourceText": self.source_text,
            "steps": [
                {
                    "type": s.type,
                    "params": s.params,
                    "confidence": s.confidence,
                    "sourceSpan": s.source_span,
                    "warnings": s.warnings,
                    "isDefault": s.is_default,
                }
                for s in self.steps
            ],
            "warnings": self.warnings,
            "ambiguities": self.ambiguities,
            "normalizationNotes": self.normalization_notes,
        }


class RecipePlanner:
    """规则式 NL → Recipe 解析器。"""

    def __init__(self) -> None:
        self.materials = MaterialNormalizer()
        self.units = UnitNormalizer()

    def parse(self, text: str) -> RecipeDraft:
        draft = RecipeDraft(source_text=text)
        # 按句号/分号/逗号 分段
        segments = self._segment(text)

        for segment in segments:
            step = self._parse_segment(segment)
            if step is not None:
                draft.steps.append(step)

        # 如果没有任何 Initialize → 自动加默认
        if draft.steps and not any(s.type == "Initialize Wafer" for s in draft.steps):
            init = PlannedStep(
                type="Initialize Wafer",
                params={"material": "Silicon", "thickness_nm": 200.0},
                confidence=0.5,
                source_span="(auto-inferred)",
                is_default=True,
            )
            draft.steps.insert(0, init)
            draft.warnings.append("未检测到 Initialize 步骤——已自动添加 Si 衬底默认值")

        # 后置检查
        self._check_ambiguities(draft)

        return draft

    def _segment(self, text: str) -> List[str]:
        parts = re.split(r'[，。；,;.]\s*', text)
        return [p.strip() for p in parts if p.strip()]

    def _parse_segment(self, segment: str) -> Optional[PlannedStep]:
        lower = segment.lower()

        # 匹配工艺步骤类型
        step_type = None
        for canonical, synonyms in PROCESS_SYNONYMS.items():
            for syn in synonyms:
                if syn in lower:
                    step_type = canonical
                    break
            if step_type:
                break

        if step_type is None:
            return None

        params: Dict[str, Any] = {}
        warnings: List[str] = []
        confidence = 0.6
        is_default = False

        # 提取长度参数（thickness/depth/CD）
        length_nm = self.units.extract_length_nm(segment)
        if length_nm is not None:
            if step_type == "Etch":
                params["depth_nm"] = length_nm
            elif step_type in ("Deposition", "Selective Epitaxy", "Oxidation"):
                params["thickness_nm"] = length_nm
            elif step_type == "Initialize Wafer":
                params["thickness_nm"] = length_nm
            else:
                params["cd_nm"] = length_nm
            confidence = 0.85
        else:
            if step_type == "Etch":
                warnings.append("未检测到刻蚀深度——使用默认 100nm")
                params["depth_nm"] = 100.0
                is_default = True
            elif step_type in ("Deposition", "Selective Epitaxy"):
                warnings.append("未检测到沉积厚度——使用默认 50nm")
                params["thickness_nm"] = 50.0
                is_default = True
            confidence = 0.5

        # 提取材料
        material_name, is_ambiguous = self.materials.normalize(segment)
        if material_name:
            params["material"] = material_name
            if is_ambiguous:
                warnings.append(f"材料 '{segment}' 有歧义——默认解析为 {material_name}")
            confidence = min(confidence + 0.1, 0.95)
        elif step_type in ("Deposition", "Etch", "Oxidation", "Selective Epitaxy"):
            warnings.append("未检测到材料名——使用默认 SiO2")
            params["material"] = "Silicon Dioxide"
            is_default = True

        # 提取时间
        time_s = self.units.extract_time_s(segment)
        if time_s is not None:
            params["time"] = time_s
            confidence = min(confidence + 0.05, 0.95)

        # Etch 特有参数
        if step_type == "Etch":
            if "湿" in lower or "wet" in lower or "isotropic" in lower:
                params["chemistry"] = "Wet"
            elif "干" in lower or "dry" in lower or "plasma" in lower:
                params["chemistry"] = "Dry"
            else:
                params["chemistry"] = "Dry"
                warnings.append("未指定刻蚀类型——默认干法")

        return PlannedStep(
            type=step_type,
            params=params,
            confidence=confidence,
            source_span=segment,
            warnings=warnings,
            is_default=is_default,
        )

    def _check_ambiguities(self, draft: RecipeDraft) -> None:
        """后置歧义检查。"""
        has_deposition = any(s.type in ("Deposition", "Oxidation") for s in draft.steps)
        has_etch = any(s.type == "Etch" for s in draft.steps)
        has_litho = any(s.type == "Mask Exposure" for s in draft.steps)

        if has_etch and not has_litho:
            draft.ambiguities.append(
                "Etch 步骤前面没有光刻步骤——刻蚀将作用于全部表面。如需图形化，请添加 Mask Exposure。"
            )

        if has_litho:
            litho = next(s for s in draft.steps if s.type == "Mask Exposure")
            if "cd_nm" not in litho.params and "pattern" not in litho.params:
                draft.ambiguities.append(
                    "光刻参数不完整：未指定 CD 或图形类型。建议指定 hole/line 尺寸。"
                )

        # 检查 CMP 前面是否有可平坦化材料
        if any(s.type == "CMP" for s in draft.steps):
            if not has_deposition:
                draft.ambiguities.append(
                    "CMP 前面没有沉积步骤——可能没有可平坦化的材料。"
                )


def parse_natural_language(text: str) -> RecipeDraft:
    """便捷入口：NL → RecipeDraft。"""
    return RecipePlanner().parse(text)
