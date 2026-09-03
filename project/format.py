# -*- coding: utf-8 -*-
"""M35: .tcad project format — zip-based portable project package."""
from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

FORMAT_VERSION = 1


@dataclass
class SimulationModeConfig:
    """每个步骤的仿真模式偏好。"""
    step_index: int
    mode: str  # "auto" | "fast" | "accurate"


@dataclass
class ProjectMetadata:
    """项目元数据。"""
    name: str = "untitled"
    description: str = ""
    created: str = ""
    modified: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class ProjectFormat:
    """.tcad 项目完整内容（内存表示）。"""
    version: int = FORMAT_VERSION
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    recipe: Dict[str, Any] = field(default_factory=dict)  # recipe blob
    simulation_modes: List[SimulationModeConfig] = field(default_factory=list)
    calibration_profile: Optional[str] = None  # profile name reference
    metrology_definitions: List[Dict[str, Any]] = field(default_factory=list)
    extra_files: Dict[str, bytes] = field(default_factory=dict)  # binary attachments

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "metadata": asdict(self.metadata),
            "recipe": self.recipe,
            "simulation_modes": [asdict(m) for m in self.simulation_modes],
            "calibration_profile": self.calibration_profile,
            "metrology_definitions": self.metrology_definitions,
        }


def save_project(project: ProjectFormat, path) -> Path:
    """保存为 .tcad（zip 格式）。"""
    output = Path(path)
    if output.suffix != ".tcad":
        output = output.with_suffix(".tcad")

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        # project.json（主清单）
        manifest = project.to_dict()
        zf.writestr("project.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        # 附加文件（geometry/calibration/layout）
        for filename, data in project.extra_files.items():
            zf.writestr(filename, data)

    return output


def load_project(path) -> ProjectFormat:
    """从 .tcad 加载项目。"""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Project file not found: {source}")

    with zipfile.ZipFile(source, "r") as zf:
        names = zf.namelist()
        if "project.json" not in names:
            raise ValueError(f"Invalid .tcad file: missing project.json")

        manifest = json.loads(zf.read("project.json"))

        project = ProjectFormat(
            version=manifest.get("version", FORMAT_VERSION),
            recipe=manifest.get("recipe", {}),
            simulation_modes=[
                SimulationModeConfig(**m)
                for m in manifest.get("simulation_modes", [])
            ],
            calibration_profile=manifest.get("calibration_profile"),
            metrology_definitions=manifest.get("metrology_definitions", []),
        )

        meta = manifest.get("metadata", {})
        project.metadata = ProjectMetadata(
            name=meta.get("name", "untitled"),
            description=meta.get("description", ""),
            created=meta.get("created", ""),
            modified=meta.get("modified", ""),
            author=meta.get("author", ""),
            tags=meta.get("tags", []),
        )

        # Load binary attachments
        for name in names:
            if name == "project.json":
                continue
            project.extra_files[name] = zf.read(name)

    return project
