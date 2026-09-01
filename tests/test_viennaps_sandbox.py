# -*- coding: utf-8 -*-
"""M8：ViennaPS 沙盒守护测试（ADR-014/021）。"""
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import unittest
from pathlib import Path

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = REPO_ROOT / "experiments" / "viennaps"

sys.path.insert(0, str(SANDBOX))

import probe as viennaps_probe  # noqa: E402


def _engine_available() -> bool:
    try:
        import viennaps  # noqa: F401

        return True
    except ImportError:
        return False


class SandboxStructureTests(unittest.TestCase):
    def test_probe_reports_cleanly_without_engine(self) -> None:
        report = viennaps_probe.probe()
        self.assertIn("python_bindings", report)
        self.assertIn("toolchain", report)
        self.assertIn("ready", report)
        if not _engine_available():
            self.assertFalse(report["ready"])
            self.assertFalse(report["python_bindings"]["viennaps"]["available"])
            # 工具链存在性也要如实报告（本机应为可用）
            self.assertTrue(report["toolchain"]["cmake"]["available"])

    def test_probe_json_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SANDBOX / "probe.py"), "--json"],
            capture_output=True, text=True, timeout=60, check=True,
        )
        import json

        payload = json.loads(result.stdout)
        self.assertIn("ready", payload)

    def test_reference_script_compiles(self) -> None:
        py_compile.compile(
            str(SANDBOX / "trench_reference.py"), doraise=True,
        )

    def test_reference_script_explains_when_engine_missing(self) -> None:
        if _engine_available():
            self.skipTest("viennaps 已安装")
        result = subprocess.run(
            [sys.executable, str(SANDBOX / "trench_reference.py")],
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertIn(result.returncode, {3, 4})
        self.assertIn("ViennaPS", result.stderr)

    def test_sandbox_is_not_registered_in_backend_registry(self) -> None:
        from process_backend import available_backends

        self.assertNotIn("viennaps", available_backends())


@unittest.skipUnless(_engine_available(), "viennaps 未安装（沙盒，ADR-021）")
class EngineReferenceTests(unittest.TestCase):
    """引擎可用后生效的参考实验守护。"""

    def test_trench_reference_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SANDBOX / "trench_reference.py")],
            capture_output=True, text=True, timeout=600, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
