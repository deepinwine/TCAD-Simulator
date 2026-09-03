# -*- coding: utf-8 -*-
"""M32: Material System 2.0 — canonical MaterialDefinition registry.

每个材料有唯一的 MaterialDefinition（canonical name、aliases、category、
visual、process properties、accurate backend mapping、approximation status）。
所有模块引用此注册表，禁止各自维护材料映射。
"""
from .registry import MaterialDefinition, MaterialRegistry, get_registry

__all__ = ["MaterialDefinition", "MaterialRegistry", "get_registry"]
