"""M35: .tcad project format tests."""
import json, os, tempfile, unittest
from pathlib import Path
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

from project import ProjectFormat, ProjectMetadata, SimulationModeConfig, load_project, save_project


class ProjectFormatTests(unittest.TestCase):
    def _make_project(self):
        return ProjectFormat(
            metadata=ProjectMetadata(
                name="test_moscap",
                description="Test MOSCAP project",
                author="test",
                tags=["moscap", "test"],
            ),
            recipe={
                "name": "moscap_flow",
                "steps": [
                    {"name": "Initialize Wafer", "params": {"material": 1, "thickness_nm": 400}, "enabled": True},
                    {"name": "Deposition", "params": {"material": 2, "thickness_nm": 100}, "enabled": True},
                ],
            },
            simulation_modes=[
                SimulationModeConfig(step_index=0, mode="fast"),
                SimulationModeConfig(step_index=1, mode="auto"),
            ],
            calibration_profile="si_sf6o2_trench_v1",
        )

    def test_round_trip(self):
        project = self._make_project()
        with tempfile.TemporaryDirectory() as tmp:
            path = save_project(project, Path(tmp) / "test.tcad")
            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".tcad")

            loaded = load_project(path)
            self.assertEqual(loaded.metadata.name, "test_moscap")
            self.assertEqual(loaded.metadata.author, "test")
            self.assertEqual(len(loaded.recipe["steps"]), 2)
            self.assertEqual(len(loaded.simulation_modes), 2)
            self.assertEqual(loaded.simulation_modes[0].mode, "fast")
            self.assertEqual(loaded.calibration_profile, "si_sf6o2_trench_v1")

    def test_extra_files(self):
        project = self._make_project()
        project.extra_files["geometry/snapshot.vtu"] = b"<VTKFile>test</VTKFile>"
        project.extra_files["layout/mask.gds"] = b"\x00\x01GDSII"

        with tempfile.TemporaryDirectory() as tmp:
            path = save_project(project, Path(tmp) / "with_files.tcad")
            loaded = load_project(path)
            self.assertIn("geometry/snapshot.vtu", loaded.extra_files)
            self.assertEqual(loaded.extra_files["geometry/snapshot.vtu"], b"<VTKFile>test</VTKFile>")
            self.assertIn("layout/mask.gds", loaded.extra_files)

    def test_suffix_auto_added(self):
        project = self._make_project()
        with tempfile.TemporaryDirectory() as tmp:
            path = save_project(project, Path(tmp) / "no_suffix")
            self.assertEqual(path.suffix, ".tcad")

    def test_invalid_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.tcad"
            bad.write_bytes(b"not a zip")
            with self.assertRaises(Exception):
                load_project(bad)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_project(Path("/nonexistent/file.tcad"))

    def test_version_preserved(self):
        project = self._make_project()
        project.version = 42  # future version
        with tempfile.TemporaryDirectory() as tmp:
            path = save_project(project, Path(tmp) / "v42.tcad")
            loaded = load_project(path)
            self.assertEqual(loaded.version, 42)

    def test_to_dict_structure(self):
        project = self._make_project()
        d = project.to_dict()
        self.assertIn("version", d)
        self.assertIn("metadata", d)
        self.assertIn("recipe", d)
        self.assertIn("simulation_modes", d)
        self.assertIn("calibration_profile", d)
        self.assertIn("metrology_definitions", d)


class ProjectWithDemosTests(unittest.TestCase):
    """从 demo flow 创建 .tcad 并 round-trip。"""

    def test_demo_flow_round_trip(self):
        from demos import DEMO_FLOWS

        flow = DEMO_FLOWS["STI (Shallow Trench Isolation)"]
        project = ProjectFormat(
            metadata=ProjectMetadata(name="sti_demo", description=flow["description"]),
            recipe={"name": flow["name"], "steps": flow["steps"]},
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = save_project(project, Path(tmp) / "sti.tcad")
            loaded = load_project(path)
            self.assertEqual(loaded.metadata.name, "sti_demo")
            self.assertEqual(len(loaded.recipe["steps"]), len(flow["steps"]))
            # Verify step names match
            original_names = [s["name"] for s in flow["steps"]]
            loaded_names = [s["name"] for s in loaded.recipe["steps"]]
            self.assertEqual(original_names, loaded_names)


if __name__ == "__main__":
    unittest.main()
