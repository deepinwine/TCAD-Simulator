# -*- coding: utf-8 -*-
"""M34: Advanced Semiconductor Demo Suite.

每个 demo 是纯数据（步骤序列），通过通用 ProcessStep 构造，
不硬编码进 process engine。
"""
from .flows import DEMO_FLOWS

__all__ = ["DEMO_FLOWS"]
