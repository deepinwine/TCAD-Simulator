"""Check the commands CI actually executes without a YAML dependency."""
from __future__ import annotations

from pathlib import Path
import re
import shlex
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def run_script(workflow: str, step_name: str) -> str:
    """Read a named step's run scalar in this workflow's simple YAML format."""
    lines = workflow.splitlines()
    for index, line in enumerate(lines):
        step = re.fullmatch(r"(\s*)- name:\s*(.+)", line)
        if step is None or step[2].strip() != step_name:
            continue
        step_indent = len(step[1])
        for position in range(index + 1, len(lines)):
            current = lines[position]
            if current.strip() and len(current) - len(current.lstrip()) <= step_indent:
                break
            run = re.fullmatch(r"(\s*)run:\s*(.+)", current)
            if run is None:
                continue
            if run[2] != "|":
                raise AssertionError("CI run commands must use a literal block")
            run_indent = len(run[1])
            body = []
            for command_line in lines[position + 1:]:
                if command_line.strip() and len(command_line) - len(command_line.lstrip()) <= run_indent:
                    break
                body.append(command_line)
            return "\n".join(body)
        raise AssertionError(f"Missing run block in {step_name!r}")
    raise AssertionError(f"Missing CI step {step_name!r}")


def command_tokens(script: str) -> list[list[str]]:
    """Join shell continuations and discard full-line and inline comments."""
    return [tokens for line in script.replace("\\\n", " ").splitlines()
            if (tokens := shlex.split(line, comments=True))]


class CIContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_minimal_install_includes_structure_dependencies(self):
        commands = command_tokens(run_script(self.workflow, "Install minimal deps"))
        packages = set()
        for command in commands:
            if command[:2] == ["pip", "install"]:
                packages.update(command[2:])
            elif command[:4] == ["python", "-m", "pip", "install"]:
                packages.update(command[4:])
        self.assertTrue({"numpy", "matplotlib", "scipy", "cryptography"} <= packages, packages)
        self.assertTrue(packages.isdisjoint({"gdstk", "viennaps", "PyQt5", "PySide6"}), packages)

    def test_core_suite_keeps_existing_and_structure_regressions(self):
        commands = command_tokens(run_script(self.workflow, "Core backend tests"))
        modules = {token for command in commands
                   if command[:3] == ["python", "-m", "unittest"]
                   for token in command[3:]}
        required = {
            "tests.test_process_cad_foundation", "tests.test_process_cad_primitives",
            "tests.test_process_cad_demos", "tests.test_webui_viewer_contract",
            "tests.test_webui_cad_shell", "tests.test_process_backend",
            "tests.test_hybrid_backend", "tests.test_geometry_scene",
            "tests.test_geometry_bridge", "tests.test_m18_hybrid_truth",
            "tests.test_backend_reliability", "tests.test_calibration",
            "tests.test_recipe_planner", "tests.test_recipe_reliability",
            "tests.test_process_api_facade", "tests.test_m34_demos",
            "tests.test_dram_reliability", "tests.test_ci_contract",
            "tests.test_structure_cad", "tests.test_structure_cad_http",
            "tests.test_structure_display_geometry", "tests.test_structure_display_provenance",
            "tests.test_structure_display_http", "tests.test_structure_editor_http",
            "tests.test_tcad_studio_launcher",
        }
        self.assertFalse(required - modules, f"Missing core modules: {sorted(required - modules)}")

    def test_compile_includes_structure_and_launcher(self):
        commands = command_tokens(run_script(self.workflow, "Compile check"))
        targets = {token for command in commands
                   if command[:3] == ["python", "-m", "py_compile"]
                   for token in command[3:]}
        required = {"tcad_simulator.py", "tools/*.py", "process_api/*.py",
                    "process_backend/*.py", "geometry_scene/*.py", "layout/*.py",
                    "calibration/*.py", "recipe_planner/*.py", "structure_cad/*.py",
                    "tcad_studio.py"}
        self.assertFalse(required - targets, f"Missing compile targets: {sorted(required - targets)}")

    def test_comments_and_other_steps_do_not_count_as_commands(self):
        workflow = """
      - name: Core backend tests
        # run: python -m unittest tests.test_structure_cad
        run: |
          # python -m unittest tests.test_structure_cad
          python -m unittest \\
            tests.test_recipe_planner # tests.test_structure_cad
      - name: Unrelated
        run: |
          python -m unittest tests.test_structure_cad
"""
        self.assertEqual(command_tokens(run_script(workflow, "Core backend tests")),
                         [["python", "-m", "unittest", "tests.test_recipe_planner"]])


if __name__ == "__main__":
    unittest.main()
