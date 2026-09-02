# -*- coding: utf-8 -*-
"""M16：自然语言 → 可审核 Recipe。

架构：NL → 规则式解析 → 结构化候选 → 校验/歧义 → 用户审核 → Apply → Simulation。
LLM 是可选增强，不是必需——离线时规则式解析器完整工作。
"""
from .normalizer import MaterialNormalizer, UnitNormalizer
from .parser import RecipeDraft, RecipePlanner, parse_natural_language
from .validator import RecipeValidator

__all__ = [
    "MaterialNormalizer",
    "RecipeDraft",
    "RecipePlanner",
    "RecipeValidator",
    "UnitNormalizer",
    "parse_natural_language",
]
