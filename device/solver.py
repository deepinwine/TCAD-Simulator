# -*- coding: utf-8 -*-
"""M33: Device Solver Backend interface — stub for DEVSIM/FEniCSx adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SolverResult:
    """求解器输出。"""
    ok: bool
    solver_name: str
    quantity: str = ""       # "potential", "electron_density", etc.
    units: str = ""
    data: Optional[Any] = None  # solver-specific
    error: str = ""
    elapsed_s: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok,
            "solver": self.solver_name,
            "quantity": self.quantity,
            "units": self.units,
            "error": self.error,
            "elapsed_s": self.elapsed_s,
        }


@dataclass
class BiasCondition:
    """单个偏置条件。"""
    electrode_name: str
    voltage_v: float


@dataclass
class SimulationSetup:
    """一次器件仿真的完整配置。"""
    device_name: str = "device"
    mesh_path: str = ""
    mesh_format: str = "vtu"  # "vtu" | "msh"
    bias: List[BiasCondition] = field(default_factory=list)
    temperature_k: float = 300.0
    models: List[str] = field(default_factory=lambda: ["drift_diffusion"])
    output_quantities: List[str] = field(default_factory=lambda: ["potential"])

    def to_dict(self) -> Dict:
        return {
            "device": self.device_name,
            "mesh": self.mesh_path,
            "format": self.mesh_format,
            "bias": [{"electrode": b.electrode_name, "voltage_v": b.voltage_v} for b in self.bias],
            "temperature_k": self.temperature_k,
            "models": self.models,
            "output": self.output_quantities,
        }


class DeviceSolverBackend(ABC):
    """器件求解器接口——DEVSIM/FEniCSx 适配器实现此接口。"""

    @abstractmethod
    def name(self) -> str:
        """求解器名称。"""

    @abstractmethod
    def available(self) -> bool:
        """求解器是否已安装且可用。"""

    @abstractmethod
    def supported_quantities(self) -> List[str]:
        """支持的输出物理量列表。"""

    @abstractmethod
    def solve(self, setup: SimulationSetup) -> SolverResult:
        """执行一次器件仿真。"""


class StubSolver(DeviceSolverBackend):
    """空实现——当无真实求解器时使用。"""

    def name(self) -> str:
        return "stub"

    def available(self) -> bool:
        return True

    def supported_quantities(self) -> List[str]:
        return []

    def solve(self, setup: SimulationSetup) -> SolverResult:
        return SolverResult(
            ok=False,
            solver_name="stub",
            error="No device solver installed. Install DEVSIM or FEniCSx.",
        )


def get_solver() -> DeviceSolverBackend:
    """获取最佳可用求解器。"""
    # 尝试 DEVSIM
    try:
        import devsim  # noqa: F401
        from .devsim_adapter import DEVSIMSolver
        return DEVSIMSolver()
    except ImportError:
        pass

    # 尝试 FEniCSx
    try:
        import dolfinx  # noqa: F401
        from .fenicsx_adapter import FEniCSxSolver
        return FEniCSxSolver()
    except ImportError:
        pass

    return StubSolver()
