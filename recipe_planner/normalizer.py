# -*- coding: utf-8 -*-
"""M16：材料与单位归一化。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# ---- 材料 ----

MATERIAL_SYNONYMS: dict[str, list[str]] = {
    "Silicon": ["si", "silicon", "硅", "单晶硅", "晶体硅", "si衬底", "硅衬底"],
    "Silicon Dioxide": ["sio2", "silicon dioxide", "oxide", "二氧化硅", "氧化层", "氧化硅", "硅氧化物"],
    "Silicon Nitride": ["sin", "si3n4", "silicon nitride", "氮化硅", "氮化物"],
    "Photoresist": ["pr", "photoresist", "光刻胶", "抗蚀剂", "光阻"],
    "Polysilicon": ["poly", "polysilicon", "poly si", "多晶硅"],
    "SiGe": ["sige", "硅锗", "锗硅"],
    "Tungsten": ["w", "tungsten", "钨"],
    "Titanium Nitride": ["tin", "titanium nitride", "氮化钛"],
    "Copper": ["cu", "copper", "铜"],
    "Aluminum": ["al", "aluminum", "aluminium", "铝"],
    "HfO2": ["hfo2", "hafnium oxide", "氧化铪"],
}


class MaterialNormalizer:
    def normalize(self, text: str) -> Tuple[Optional[str], bool]:
        """返回 (canonical_name, is_ambiguous)。优先匹配最长的同义词。"""
        t = text.strip().lower()
        # 收集所有匹配 (match_length, canonical)
        candidates = []
        for canonical, synonyms in MATERIAL_SYNONYMS.items():
            if t == canonical.lower():
                return canonical, False
            for syn in synonyms:
                if syn in t:
                    candidates.append((len(syn), canonical))
        if candidates:
            # 最长匹配优先（"sio2" 优先于 "si"）
            candidates.sort(key=lambda c: -c[0])
            return candidates[0][1], False
        # "oxide" 可能指 SiO2 也可能是其他氧化物——歧义
        if "oxide" in t and "sio2" not in t and "silicon" not in t:
            return "Silicon Dioxide", True  # 默认 SiO2 但标注歧义
        return None, True


# ---- 单位 ----

UNIT_CONVERSIONS = {
    "nm": 1.0,
    "nanometer": 1.0,
    "纳米": 1.0,
    "um": 1000.0,
    "μm": 1000.0,
    "micron": 1000.0,
    "micrometer": 1000.0,
    "微米": 1000.0,
    "a": 0.1,  # Angstrom
    "å": 0.1,
    "angstrom": 0.1,
    "埃": 0.1,
    "mm": 1_000_000.0,
    "millimeter": 1_000_000.0,
    "毫米": 1_000_000.0,
}

TIME_CONVERSIONS = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "秒": 1.0,
    "min": 60.0,
    "minute": 60.0,
    "分": 60.0,
    "分钟": 60.0,
    "h": 3600.0,
    "hour": 3600.0,
    "小时": 3600.0,
}


class UnitNormalizer:
    def to_nm(self, value: float, unit: str) -> float:
        u = unit.strip().lower()
        if u not in UNIT_CONVERSIONS:
            raise ValueError(f"未知长度单位：{unit!r}")
        return value * UNIT_CONVERSIONS[u]

    def to_seconds(self, value: float, unit: str) -> float:
        u = unit.strip().lower()
        if u not in TIME_CONVERSIONS:
            raise ValueError(f"未知时间单位：{unit!r}")
        return value * TIME_CONVERSIONS[u]

    def extract_length_nm(self, text: str) -> Optional[float]:
        """从文本中提取第一个长度值并转换为 nm。"""
        pattern = r'(\d+(?:\.\d+)?)\s*(nm|纳米|μm|µm|um|微米|micron|Å|å|angstrom|埃|mm|毫米)'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            # 也匹配 "100nm"（无空格）
            pattern2 = r'(\d+(?:\.\d+)?)\s*(nm|um|μm|mm)'
            match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            return self.to_nm(value, unit)
        return None

    def extract_time_s(self, text: str) -> Optional[float]:
        """从文本中提取第一个时间值并转换为秒。"""
        pattern = r'(\d+(?:\.\d+)?)\s*(s|秒|min|分|分钟|h|小时)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            return self.to_seconds(value, unit)
        return None
