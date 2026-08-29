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

    def test_set_step_response_reports_dirty_statuses(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = self._start_manager(temp_dir)
                session, _cookie = manager.create_session()
                session.rpc("recipe_new", {"name": "Dirty statuses"}, timeout_s=30.0)
                session.rpc(
                    "recipe_insert_steps",
                    {"steps": [{"name": "Spin Resist"}, {"name": "Etch"}]},
                    timeout_s=30.0,
                )
                first = session.rpc("run_all", {}, timeout_s=30.0)
                self.assertTrue(first["ok"])
                edited = session.rpc(
                    "set_step",
                    {"index": 1, "params": {}, "no_autosave": True},
                    timeout_s=30.0,
                )
                self.assertTrue(edited["ok"])
                statuses = edited.get("statuses")
                self.assertIsInstance(statuses, list)
                self.assertEqual(statuses[0], "done")
                for status in statuses[1:]:
                    self.assertEqual(status, "dirty")
            finally:
                if manager is not None:
                    manager.stop()

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
    @staticmethod
    def _load_runner_module():
        import importlib.util
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "tcad_baseline_runner", repo_root / "tools" / "run_process_cad_baseline.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_rss_helpers_fall_back_when_resource_is_missing(self):
        import sys
        from unittest import mock

        runner = self._load_runner_module()
        # Unix 正常路径：返回 float，且 scope 标注为累计峰值
        self.assertIsInstance(runner._peak_rss_mb(), float)
        self.assertEqual(runner._rss_scope(), "ru_maxrss_cumulative_process")
        # 模拟 Windows：resource 与 psutil 均缺失 -> 不抛异常，返回 None
        with mock.patch.object(runner, "resource", None), mock.patch.dict(sys.modules, {"psutil": None}):
            self.assertIsNone(runner._peak_rss_mb())
            self.assertEqual(runner._rss_scope(), "unavailable")

    def test_baseline_runner_survives_without_resource_module(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        code = (
            "import sys; sys.modules['resource'] = None; sys.modules['psutil'] = None; "
            "import runpy; out, script = sys.argv[1], sys.argv[2]; "
            "sys.argv = ['run_process_cad_baseline.py', '--grid', '32', '--output', out]; "
            "runpy.run_path(script, run_name='__main__')"
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.json"
            completed = subprocess.run(
                [sys.executable, "-c", code, str(output), str(repo_root / "tools" / "run_process_cad_baseline.py")],
                text=True,
                capture_output=True,
                timeout=240,
                cwd=str(repo_root),
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["peak_rss_scope"], "unavailable")
            for demo in payload["demos"].values():
                self.assertIn("peak_rss_mb", demo)
                self.assertIsNone(demo["peak_rss_mb"])

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
            self.assertIn("grid_shape", payload)
            self.assertEqual(payload["grid_shape"], [32, 32, 32])
            self.assertAlmostEqual(payload["physical_extent_nm"], 640.0)
            self.assertAlmostEqual(payload["voxel_nm"], 20.0)
            self.assertEqual(set(payload["demos"]), {"Basic Trench", "Spacer Formation", "Bonding + Thinning"})
            required_materials = {
                "Basic Trench": {"Silicon", "Silicon Dioxide"},
                "Spacer Formation": {"Silicon", "Silicon Nitride"},
                "Bonding + Thinning": {"Silicon", "Silicon Dioxide"},
            }
            for name, demo in payload["demos"].items():
                self.assertTrue(demo["ok"], f"{name}: {demo}")
                self.assertIn("elapsed_s", demo)
                self.assertIn("peak_rss_mb", demo)
                self.assertIn("material_count", demo)
                self.assertIn("occupied_voxels", demo)
                self.assertIn("triangle_count", demo)
                self.assertIn("mesh_elapsed_s", demo)
                self.assertGreaterEqual(demo["material_count"], 2)
                self.assertGreater(demo["occupied_voxels"], 0)
                self.assertGreater(demo["triangle_count"], 0)
                self.assertTrue(required_materials[name].issubset(set(demo["materials"])))
                self.assertTrue(all(demo["checks"].values()), f"{name}: {demo['checks']}")


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


class M2ApiContractTests(unittest.TestCase):
    """Executable contract for the frozen M2 Compatibility API.

    Mirrors the table in docs/ARCHITECTURE_TARGET.md: HTTP methods, minimal request
    payloads, and JSON/binary response classification. Every endpoint React consumes
    must be covered here (ADR-019).
    """

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

    @staticmethod
    def _request(base, cookie, method, path, body=None):
        import http.client
        import json as _json
        from urllib.parse import urlparse

        parsed = urlparse(base)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=90)
        headers = {"Cookie": cookie.split(";", 1)[0]}
        payload = None
        if body is not None:
            payload = _json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        resp_headers = {k.lower(): v for k, v in response.getheaders()}
        status = response.status
        conn.close()
        return status, resp_headers, raw

    def test_get_bootstrap_endpoints_return_json_envelopes(self):
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._start_manager(temp_dir)
            try:
                session, cookie = manager.create_session()
                base = manager.url
                for path in ("/api/health", "/api/status", "/api/log", "/api/history", "/api/process_config"):
                    status, headers, raw = self._request(base, cookie, "GET", path)
                    self.assertEqual(status, 200, f"{path}: {raw[:200]!r}")
                    self.assertIn("application/json", headers.get("content-type", ""))
                    payload = json.loads(raw)
                    self.assertIn("ok", payload)
                status, _headers, raw = self._request(base, cookie, "GET", "/api/init")
                self.assertEqual(status, 200)
                result = json.loads(raw)["result"]
                for key in ("recipe", "model", "recipe_factories", "materials"):
                    self.assertIn(key, result, f"/api/init missing {key}")
                self.assertIsInstance(result["recipe"], list)
                self.assertIsInstance(result["model"], dict)
            finally:
                manager.stop()

    def test_recipe_and_step_editing_contract(self):
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._start_manager(temp_dir)
            try:
                session, cookie = manager.create_session()
                base = manager.url
                status, _h, raw = self._request(base, cookie, "POST", "/api/recipe/new", {"name": "M2 contract"})
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(raw)["ok"], raw[:300])
                status, _h, raw = self._request(
                    base, cookie, "POST", "/api/recipe/insert_steps", {"steps": [{"name": "Spin Resist"}]}
                )
                self.assertTrue(json.loads(raw)["ok"], raw[:300])

                status, _h, raw = self._request(
                    base, cookie, "POST", "/api/step/set", {"index": 1, "params": {}, "no_autosave": True}
                )
                payload = json.loads(raw)
                self.assertTrue(payload["ok"], raw[:300])
                self.assertIn(payload["result"]["runtime_status"], {"ready", "dirty", "running", "done", "error"})
                self.assertIsInstance(payload.get("statuses"), list)
                self.assertEqual(len(payload["statuses"]), 2)

                status, _h, raw = self._request(
                    base, cookie, "POST", "/api/recipe/rename-step", {"index": 1, "instance_name": "契约步骤"}
                )
                payload = json.loads(raw)
                self.assertTrue(payload["ok"], raw[:300])
                self.assertEqual(payload["result"]["instance_name"], "契约步骤")

                status, _h, raw = self._request(base, cookie, "POST", "/api/recipe/move", {"index": 0, "to": 1})
                payload = json.loads(raw)
                self.assertTrue(payload["ok"], raw[:300])
                self.assertIsInstance(payload["result"], list)
                self.assertEqual(len(payload["result"]), 2)
            finally:
                manager.stop()

    def test_execution_timeline_undo_redo_contract(self):
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._start_manager(temp_dir)
            try:
                session, cookie = manager.create_session()
                base = manager.url
                self._request(base, cookie, "POST", "/api/recipe/new", {"name": "M2 exec"})
                status, _h, raw = self._request(base, cookie, "POST", "/api/run/to", {"index": 0})
                self.assertTrue(json.loads(raw)["ok"], raw[:300])

                status, _h, raw = self._request(base, cookie, "POST", "/api/timeline/get", {})
                result = json.loads(raw)["result"]
                self.assertEqual(result["current"], 0)
                self.assertTrue(result["items"])
                for item in result["items"]:
                    self.assertEqual(set(item), {"index", "state", "runtime_status", "snapshot_valid"})

                status, _h, raw = self._request(base, cookie, "POST", "/api/timeline/restore", {"index": 0})
                payload = json.loads(raw)
                self.assertTrue(payload["ok"], raw[:300])
                self.assertEqual(payload["result"]["timeline"]["current"], 0)

                # 拒绝无效快照：HTTP 200 + 结构化错误，不隐式重算
                status, _h, raw = self._request(base, cookie, "POST", "/api/timeline/restore", {"index": 5})
                payload = json.loads(raw)
                self.assertEqual(status, 200)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["code"], "no_valid_snapshot")

                status, _h, raw = self._request(base, cookie, "POST", "/api/undo", {})
                self.assertTrue(json.loads(raw)["result"]["undone"])
                status, _h, raw = self._request(base, cookie, "POST", "/api/redo", {})
                self.assertTrue(json.loads(raw)["result"]["redone"])
            finally:
                manager.stop()

    def test_preview_binary_and_json_contract(self):
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._start_manager(temp_dir)
            try:
                session, cookie = manager.create_session()
                base = manager.url
                self._request(base, cookie, "POST", "/api/recipe/new", {"name": "M2 preview"})
                self._request(base, cookie, "POST", "/api/run/to", {"index": 0})

                status, headers, raw = self._request(
                    base, cookie, "GET", "/api/preview/manifest?mode=solid&face_limit=2000"
                )
                self.assertEqual(status, 200, raw[:200])
                self.assertIn("application/json", headers.get("content-type", ""))
                result = json.loads(raw)["result"]
                self.assertIsInstance(result["rev"], int)
                self.assertTrue(result["meshes"])
                mat_id = int(result["meshes"][0]["mat_id"])
                rev = int(result["rev"])

                status, headers, raw = self._request(
                    base, cookie, "GET", f"/api/preview/geom?mat_id={mat_id}&rev={rev}&mode=solid"
                )
                self.assertEqual(status, 200, raw[:200])
                self.assertIn("application/octet-stream", headers.get("content-type", ""))
                self.assertTrue(raw)
                self.assertFalse(raw[:1] == b"{", "geom must be binary, not a JSON envelope")

                status, _h, raw = self._request(base, cookie, "GET", "/api/slice?axis=Z&index=0&kind=material")
                self.assertEqual(status, 200, raw[:200])
                result = json.loads(raw)["result"]
                self.assertIn("data_b64", result)

                # 方法是契约的一部分：GET 打 POST-only 端点必须 404
                status, _h, raw = self._request(base, cookie, "GET", "/api/timeline/get")
                self.assertEqual(status, 404)
            finally:
                manager.stop()


if __name__ == "__main__":
    unittest.main()
