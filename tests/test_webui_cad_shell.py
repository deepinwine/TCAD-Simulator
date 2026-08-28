import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import tcad_simulator as tcad


class CadShellMarkupTests(unittest.TestCase):
    def test_three_columns_are_present(self):
        html = tcad._WEBUI_INDEX_HTML
        for element_id in ("process-flow-panel", "parameters-panel", "viewer-panel"):
            self.assertIn(f'id="{element_id}"', html)

    def test_desktop_grid_has_three_columns(self):
        css = tcad._WEBUI_STYLE_CSS
        expected = "grid-template-columns: minmax(260px, 300px) minmax(300px, 360px) minmax(420px, 1fr)"
        self.assertIn(expected, css)

    def test_primary_three_columns_are_not_hidden_behind_the_tool_drawer(self):
        html = tcad._WEBUI_INDEX_HTML
        self.assertIn('class="main-container drawer-collapsed"', html)
        self.assertIn('id="cad-drawer-toggle" title="展开工具面板">»', html)

    def test_viewer_backend_status_is_accessible_and_has_non_overlapping_remote_layout(self):
        html = tcad._WEBUI_INDEX_HTML
        css = tcad._WEBUI_STYLE_CSS
        self.assertIn('id="viewer-backend-status" role="status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('aria-atomic="true"', html)
        remote_rule = css.split('#viewer-backend-status[data-backend="remote"]', 1)[1].split('}', 1)[0]
        self.assertIn("top: auto", remote_rule)
        self.assertIn("bottom:", remote_rule)


class TimelineStateTests(unittest.TestCase):
    def test_snapshot_manifest_marks_valid_dirty_and_current(self):
        result = tcad._snapshot_timeline_manifest(
            recipe_length=4,
            valid_snapshot_indices={0, 1},
            statuses=["done", "done", "dirty", "dirty"],
            current_index=1,
        )
        self.assertEqual([item["state"] for item in result], ["done", "current", "dirty", "dirty"])

    def test_snapshot_manifest_reports_validity_and_normalized_statuses(self):
        result = tcad._snapshot_timeline_manifest(
            recipe_length=3,
            valid_snapshot_indices=[2],
            statuses=["weird", None, "DONE"],
            current_index=-1,
        )
        self.assertEqual([item["runtime_status"] for item in result], ["ready", "ready", "done"])
        self.assertEqual([item["snapshot_valid"] for item in result], [False, False, True])
        self.assertEqual([item["index"] for item in result], [0, 1, 2])


class HistoryStackTests(unittest.TestCase):
    def test_new_edit_clears_redo_stack(self):
        undo = ["s0"]
        redo = ["s2"]
        tcad._record_history_edit(undo, redo, "s1", max_items=20)
        self.assertEqual(undo, ["s0", "s1"])
        self.assertEqual(redo, [])

    def test_undo_moves_current_to_redo(self):
        undo = ["s0", "s1"]
        redo = []
        restored = tcad._history_undo(undo, redo, current="s2")
        self.assertEqual(restored, "s1")
        self.assertEqual(redo, ["s2"])

    def test_redo_moves_current_to_undo(self):
        undo = []
        redo = ["s2"]
        restored = tcad._history_redo(undo, redo, current="s1")
        self.assertEqual(restored, "s2")
        self.assertEqual(undo, ["s1"])
        self.assertEqual(redo, [])

    def test_undo_without_entries_returns_none(self):
        undo = []
        redo = []
        restored = tcad._history_undo(undo, redo, current="s9")
        self.assertIsNone(restored)
        self.assertEqual(redo, [])


class CadShellWorkerHistoryTests(unittest.TestCase):
    def _start_manager(self, temp_dir):
        manager = tcad.WebUIServerManager(
            host="127.0.0.1",
            port=0,
            max_users=1,
            storage_root=Path(temp_dir),
            enable_ai_agent=False,
            default_domain={"grid_shape": [12, 12, 16], "voxel_size_nm": 5.0, "threads": 1},
        )
        manager.start()
        return manager

    def test_single_step_replaces_stale_timeline_snapshot(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = self._start_manager(temp_dir)
                session, _cookie = manager.create_session()
                session.rpc("recipe_new", {"name": "Timeline single step"}, timeout_s=30.0)
                first = session.rpc("run_all", {}, timeout_s=30.0)
                self.assertTrue(first["ok"])
                session.rpc(
                    "set_step",
                    {"index": 0, "params": {"material": "Germanium"}, "no_autosave": True},
                    timeout_s=30.0,
                )
                single = session.rpc("run_step", {"index": 0}, timeout_s=30.0)
                self.assertTrue(single["ok"])
                self.assertEqual(single["result"]["model"]["substrate_material"], "Germanium")
                timeline = session.rpc("timeline_get", {}, timeout_s=30.0)
                self.assertTrue(timeline["result"]["items"][0]["snapshot_valid"])
                restored = session.rpc("timeline_restore", {"index": 0}, timeout_s=30.0)
                self.assertTrue(restored["ok"])
                self.assertEqual(restored["result"]["model"]["substrate_material"], "Germanium")
            finally:
                if manager is not None:
                    manager.stop()

    def test_undo_restores_runtime_status_and_recipe_edit_invalidates_redo(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = self._start_manager(temp_dir)
                session, _cookie = manager.create_session()
                session.rpc("recipe_new", {"name": "History status"}, timeout_s=30.0)
                session.rpc(
                    "set_step",
                    {"index": 0, "params": {"material": "Germanium"}, "no_autosave": True},
                    timeout_s=30.0,
                )
                self.assertTrue(session.rpc("run_step", {"index": 0}, timeout_s=30.0)["ok"])
                self.assertEqual(
                    session.rpc("get_recipe", {}, timeout_s=30.0)["result"][0]["runtime_status"],
                    "done",
                )
                undone = session.rpc("undo", {}, timeout_s=30.0)
                self.assertTrue(undone["result"]["undone"])
                self.assertNotEqual(
                    session.rpc("get_recipe", {}, timeout_s=30.0)["result"][0]["runtime_status"],
                    "done",
                )
                redone_once = session.rpc("redo", {}, timeout_s=30.0)
                self.assertTrue(redone_once["result"]["redone"])
                self.assertEqual(redone_once["result"]["model"]["substrate_material"], "Germanium")
                self.assertEqual(redone_once["result"]["recipe"][0]["runtime_status"], "done")
                self.assertTrue(session.rpc("undo", {}, timeout_s=30.0)["result"]["undone"])
                session.rpc(
                    "set_step",
                    {"index": 0, "params": {"material": "Silicon"}, "no_autosave": True},
                    timeout_s=30.0,
                )
                redone = session.rpc("redo", {}, timeout_s=30.0)
                self.assertFalse(redone["result"]["redone"])
            finally:
                if manager is not None:
                    manager.stop()

    def test_undo_and_redo_restore_the_recipe_parameters_from_the_same_snapshot(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = self._start_manager(temp_dir)
                session, _cookie = manager.create_session()
                session.rpc("recipe_new", {"name": "History recipe"}, timeout_s=30.0)
                session.rpc(
                    "set_step",
                    {"index": 0, "params": {"material": "Germanium"}, "no_autosave": True},
                    timeout_s=30.0,
                )
                germanium_param = session.rpc("get_recipe", {}, timeout_s=30.0)["result"][0]["params"]["material"]
                self.assertTrue(session.rpc("run_step", {"index": 0}, timeout_s=30.0)["ok"])
                session.rpc(
                    "set_step",
                    {"index": 0, "params": {"material": "Silicon"}, "no_autosave": True},
                    timeout_s=30.0,
                )
                silicon_param = session.rpc("get_recipe", {}, timeout_s=30.0)["result"][0]["params"]["material"]
                self.assertNotEqual(germanium_param, silicon_param)

                undone = session.rpc("undo", {}, timeout_s=30.0)
                self.assertTrue(undone["result"]["undone"])
                self.assertEqual(undone["result"]["recipe"][0]["params"]["material"], germanium_param)

                redone = session.rpc("redo", {}, timeout_s=30.0)
                self.assertTrue(redone["result"]["redone"])
                self.assertEqual(redone["result"]["recipe"][0]["params"]["material"], silicon_param)
            finally:
                if manager is not None:
                    manager.stop()

    def test_structured_step_error_survives_init_refresh(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = self._start_manager(temp_dir)
                session, _cookie = manager.create_session()
                session.rpc("recipe_new", {"name": "Persistent error"}, timeout_s=30.0)
                session.rpc(
                    "set_step",
                    {"index": 0, "params": {"thickness_nm": {"invalid": True}}, "no_autosave": True},
                    timeout_s=30.0,
                )
                failure = session.rpc("run_step", {"index": 0}, timeout_s=30.0)
                self.assertFalse(failure["ok"])
                refreshed = session.rpc("init", {}, timeout_s=30.0)["result"]["recipe"][0]
                self.assertEqual(refreshed["runtime_status"], "error")
                self.assertEqual(refreshed["runtime_error"]["error"], failure["error"])
                self.assertEqual(refreshed["runtime_error"]["error_type"], failure["error_type"])
                self.assertEqual(refreshed["runtime_error"]["rolled_back"], failure["rolled_back"])
                self.assertTrue(refreshed["runtime_error"]["suggestion"])
            finally:
                if manager is not None:
                    manager.stop()

    def test_new_recipe_cannot_redo_a_model_from_the_previous_recipe(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = self._start_manager(temp_dir)
                session, _cookie = manager.create_session()
                session.rpc("recipe_new", {"name": "Old recipe"}, timeout_s=30.0)
                session.rpc(
                    "set_step",
                    {"index": 0, "params": {"material": "Germanium"}, "no_autosave": True},
                    timeout_s=30.0,
                )
                self.assertTrue(session.rpc("run_step", {"index": 0}, timeout_s=30.0)["ok"])
                self.assertTrue(session.rpc("undo", {}, timeout_s=30.0)["result"]["undone"])
                created = session.rpc("recipe_new", {"name": "New recipe"}, timeout_s=30.0)
                self.assertEqual(created["result"]["model"]["substrate_material"], "Silicon")
                redone = session.rpc("redo", {}, timeout_s=30.0)
                self.assertFalse(redone["result"]["redone"])
                current = session.rpc("init", {}, timeout_s=30.0)["result"]
                self.assertEqual(current["model"]["substrate_material"], "Silicon")
                self.assertEqual(current["recipe"][0]["params"]["material"], "Silicon")
            finally:
                if manager is not None:
                    manager.stop()


class BaselineRunnerTests(unittest.TestCase):
    def test_baseline_runner_writes_success_json(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "tools" / "run_process_cad_baseline.py"),
                    "--grid",
                    "32",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                timeout=240,
                cwd=str(repo_root),
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["grid"], 32)
            self.assertEqual(set(payload["demos"]), {"Basic Trench", "Spacer Formation", "Bonding + Thinning"})
            for demo in payload["demos"].values():
                self.assertIn("elapsed_s", demo)
                self.assertIn("peak_rss_mb", demo)
                self.assertIn("material_count", demo)
                self.assertIn("occupied_voxels", demo)
                self.assertIn("triangle_count", demo)
                self.assertIn("mesh_elapsed_s", demo)


class CadShellInteractionContractTests(unittest.TestCase):
    def test_recipe_items_support_drag_and_rename(self):
        source = tcad._WEBUI_SCRIPT_JS
        self.assertIn("item.draggable = true", source)
        self.assertIn("dragstart", source)
        self.assertIn("drop", source)
        self.assertIn("renameStep", source)

    def test_timeline_controls_exist(self):
        html = tcad._WEBUI_INDEX_HTML
        for element_id in ("timeline-prev", "timeline-next", "timeline-range"):
            self.assertIn(f'id="{element_id}"', html)

    def test_non_adjacent_drag_move_shifts_both_slice_override_maps(self):
        source = tcad._WEBUI_SCRIPT_JS
        start = source.index("function _sliceOverridesMove(")
        end = source.index("\n}", start) + 2
        helper = source[start:end]
        script = helper + """
const first = {'0':'A','1':'B','2':'C','3':'D'};
const second = {'0':'a','1':'b','2':'c','3':'d'};
const result = [_sliceOverridesMove(first, 0, 3), _sliceOverridesMove(second, 3, 1)];
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", script], text=True, capture_output=True, timeout=30
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            [
                {"0": "B", "1": "C", "2": "D", "3": "A"},
                {"0": "a", "1": "d", "2": "b", "3": "c"},
            ],
        )

    def test_failed_run_refreshes_server_status_before_rendering_error_details(self):
        source = tcad._WEBUI_SCRIPT_JS
        self.assertIn("async function handleStructuredRunFailure", source)
        self.assertIn("await refreshAll(false)", source)
        self.assertIn("state.stepErrors[stepIndex] = failure", source)


if __name__ == "__main__":
    unittest.main()
