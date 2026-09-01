# -*- coding: utf-8 -*-
"""ViennaPS 沙盒能力探测（ADR-014 / ADR-021）。

输出 JSON：python 绑定、构建工具链、后端注册表视角。仅探测、不安装、
不改动主仓库任何运行路径。用法：

    python experiments/viennaps/probe.py            # 人读输出
    python experiments/viennaps/probe.py --json     # 机读输出
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys


def _module_available(name: str) -> dict:
    try:
        module = __import__(name)
        return {
            "available": True,
            "version": str(getattr(module, "__version__", "unknown")),
        }
    except ImportError as exc:
        return {"available": False, "reason": f"ImportError: {exc}"}


def _tool_version(command: list[str]) -> dict:
    path = shutil.which(command[0])
    if path is None:
        return {"available": False}
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=False,
        )
        first_line = (result.stdout or result.stderr).strip().splitlines()
        return {
            "available": True,
            "path": path,
            "version": first_line[0] if first_line else "unknown",
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


def probe() -> dict:
    report = {
        "python_bindings": {
            "viennaps": _module_available("viennaps"),
            "viennals": _module_available("viennals"),
        },
        "toolchain": {
            "cmake": _tool_version(["cmake", "--version"]),
            "cxx": _tool_version([_default_cxx(), "--version"]),
        },
        "registry_view": {},
        "notes": [
            "ADR-014: 本沙盒不接入 process_backend 注册表；M9 才提供 ViennaPSBackend。",
        ],
    }
    try:
        sys.path.insert(0, _repo_root())
        from process_backend import available_backends

        report["registry_view"]["backends"] = available_backends()
    except Exception as exc:  # noqa: BLE001
        report["registry_view"]["error"] = str(exc)
    report["ready"] = (
        report["python_bindings"]["viennaps"]["available"]
        or report["python_bindings"]["viennals"]["available"]
    )
    return report


def _default_cxx() -> str:
    for candidate in ("c++", "clang++", "g++"):
        if shutil.which(candidate):
            return candidate
    return "c++"


def _repo_root() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parents[2])


def main() -> int:
    report = probe()
    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        bindings = report["python_bindings"]
        print(f"viennaps 绑定: {bindings['viennaps']['available']}")
        print(f"viennals 绑定: {bindings['viennals']['available']}")
        print(f"cmake: {report['toolchain']['cmake']['available']}")
        print(f"C++ 编译器: {report['toolchain']['cxx']['available']}")
        print(f"沙盒就绪（引擎可用）: {report['ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
