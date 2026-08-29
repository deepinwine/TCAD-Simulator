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
    def _request(base, cookie, method, path, body=None, raw_body=None, content_type=None):
        import http.client
        import json as _json
        from urllib.parse import urlparse

        parsed = urlparse(base)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=90)
        headers = {"Cookie": cookie.split(";", 1)[0]}
        payload = None
        if raw_body is not None:
            payload = raw_body
            headers["Content-Type"] = content_type or "application/octet-stream"
        elif body is not None:
            payload = _json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        resp_headers = {k.lower(): v for k, v in response.getheaders()}
        status = response.status
        conn.close()
        return status, resp_headers, raw

    @staticmethod
    def _first_string_ending(obj, suffixes):
        """递归查找 JSON 中第一个以指定后缀结尾的字符串（用于文件名提取）。"""
        import json as _json

        if isinstance(obj, str):
            return obj if any(obj.endswith(s) for s in suffixes) else None
        if isinstance(obj, dict):
            for value in obj.values():
                found = M2ApiContractTests._first_string_ending(value, suffixes)
                if found:
                    return found
        if isinstance(obj, list):
            for value in obj:
                found = M2ApiContractTests._first_string_ending(value, suffixes)
                if found:
                    return found
        return None

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


    def test_full_endpoint_lifecycle_walk(self):
        """行为证据：契约表中每个端点都以声明的 method 调用并断言响应类别。"""
        import io
        import json

        import numpy as np

        def check_json(raw, ctx):
            payload = json.loads(raw)
            self.assertIn("ok", payload, ctx)

        def check_binary(headers, raw, ctx):
            ctype = headers.get("content-type", "")
            self.assertFalse(raw[:1] == b"{", f"{ctx}: expected binary, got JSON")
            self.assertNotIn("json", ctype.lower(), f"{ctx}: binary endpoint returned JSON content-type {ctype!r}")

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = self._start_manager(temp_dir)
            try:
                session, cookie = manager.create_session()
                base = manager.url

                # --- bootstrap ---
                for path in ("/api/health", "/api/status", "/api/log", "/api/history", "/api/process_config", "/api/init"):
                    status, headers, raw = self._request(base, cookie, "GET", path)
                    self.assertEqual(status, 200, path)
                    check_json(raw, path)

                # --- recipe editing lifecycle ---
                steps = [
                    ("POST", "/api/recipe/new", {"name": "M2 walk"}, "json"),
                    ("POST", "/api/recipe/add", {"name": "Spin Resist"}, "json"),
                    ("POST", "/api/recipe/add", {"name": "Mask Exposure"}, "json"),
                    ("POST", "/api/recipe/duplicate", {"index": 2}, "json"),
                    ("POST", "/api/recipe/remove", {"index": 3}, "json"),
                    ("POST", "/api/recipe/move", {"index": 0, "to": 1}, "json"),
                    ("POST", "/api/recipe/rename-step", {"index": 1, "instance_name": "契约行走"}, "json"),
                    ("POST", "/api/step/set", {"index": 1, "params": {}, "no_autosave": True}, "json"),
                    ("POST", "/api/recipe/save", {"name": "M2 walk"}, "json"),
                ]
                for method, path, body, kind in steps:
                    status, headers, raw = self._request(base, cookie, method, path, body)
                    self.assertEqual(status, 200, f"{path}: {raw[:200]!r}")
                    check_json(raw, path)

                status, _h, raw = self._request(base, cookie, "GET", "/api/history")
                history_payload = json.loads(raw)
                # 取一个已保存 recipe 的 id（history 条目含 id 字段）
                recipe_id = None

                def _find_id(obj):
                    nonlocal recipe_id
                    if recipe_id is not None:
                        return
                    if isinstance(obj, dict):
                        if isinstance(obj.get("id"), str) and obj.get("name"):
                            recipe_id = obj["id"]
                            return
                        for v in obj.values():
                            _find_id(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            _find_id(v)

                _find_id(history_payload)
                self.assertIsNotNone(recipe_id, "history should expose a saved recipe id")
                # /api/recipe/export 返回裸 recipe blob（无 ok 封套），单独断言
                status, headers, raw = self._request(base, cookie, "GET", "/api/recipe/export?scope=current")
                self.assertEqual(status, 200, raw[:200])
                exported_blob = json.loads(raw)
                self.assertIsInstance(exported_blob, dict)
                self.assertIn("steps_full", exported_blob)

                for method, path, body in (
                    ("POST", "/api/history/load", {"id": recipe_id}),
                    ("POST", "/api/recipe/load", {"id": recipe_id}),
                ):
                    status, headers, raw = self._request(base, cookie, method, path, body)
                    self.assertEqual(status, 200, f"{path}: {raw[:200]!r}")
                    check_json(raw, path)

                # --- execution / timeline / history ---
                for method, path, body in (
                    ("POST", "/api/run/to", {"index": 2}),
                    ("POST", "/api/timeline/get", {}),
                    ("POST", "/api/timeline/restore", {"index": 0}),
                    ("POST", "/api/undo", {}),
                    ("POST", "/api/redo", {}),
                    ("POST", "/api/domain/apply", {"nx": 12, "ny": 12, "nz": 16, "voxel": 5.0, "threads": 1}),
                    ("POST", "/api/material_colors", {}),
                ):
                    status, headers, raw = self._request(base, cookie, method, path, body)
                    self.assertEqual(status, 200, f"{path}: {raw[:200]!r}")
                    check_json(raw, path)

                # --- multipart mask upload + binary mask previews ---
                buf = io.BytesIO()
                np.save(buf, np.zeros((8, 8), dtype=bool))
                npy_bytes = buf.getvalue()
                boundary = "tcadcontractboundary"
                multipart = (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="file"; filename="m2_mask.npy"\r\n'
                    "Content-Type: application/octet-stream\r\n\r\n"
                ).encode() + npy_bytes + f"\r\n--{boundary}--\r\n".encode()
                status, headers, raw = self._request(
                    base,
                    cookie,
                    "POST",
                    "/api/upload/mask?step_index=2",
                    raw_body=multipart,
                    content_type=f"multipart/form-data; boundary={boundary}",
                )
                self.assertEqual(status, 200, raw[:300])
                check_json(raw, "/api/upload/mask")
                upload_resp = json.loads(raw)
                uploaded = upload_resp.get("path") or self._first_string_ending(upload_resp, (".npy",))
                self.assertIsNotNone(uploaded, "upload/mask should echo the stored path")
                uploaded = uploaded.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]  # preview 只接受文件名

                status, headers, raw = self._request(base, cookie, "GET", f"/api/mask/preview?file={uploaded}")
                self.assertEqual(status, 200, raw[:200])
                check_binary(headers, raw, "/api/mask/preview")
                self.assertIn("image/png", headers.get("content-type", ""))

                status, headers, raw = self._request(base, cookie, "GET", "/api/mask/preview_step?step_index=2")
                self.assertEqual(status, 200, raw[:200])
                check_binary(headers, raw, "/api/mask/preview_step")

                # --- preview geometry: JSON manifest + binary payloads ---
                status, headers, raw = self._request(base, cookie, "GET", "/api/preview/manifest?mode=solid&face_limit=2000")
                self.assertEqual(status, 200, raw[:200])
                check_json(raw, "/api/preview/manifest")
                result = json.loads(raw)["result"]
                mat_id = int(result["meshes"][0]["mat_id"])
                rev = int(result["rev"])
                for path in (
                    f"/api/preview/geom?mat_id={mat_id}&rev={rev}&mode=solid",
                    f"/api/preview/stl?mat_id={mat_id}&rev={rev}&mode=solid",
                    "/api/preview/elements?max_points=64&channels=m",
                ):
                    status, headers, raw = self._request(base, cookie, "GET", path)
                    self.assertEqual(status, 200, f"{path}: {raw[:120]!r}")
                    check_binary(headers, raw, path)

                status, headers, raw = self._request(base, cookie, "GET", "/api/slice?axis=Z&index=0&kind=material")
                self.assertEqual(status, 200, raw[:200])
                check_json(raw, "/api/slice")
                self.assertIn("data_b64", json.loads(raw)["result"])

                status, headers, raw = self._request(
                    base, cookie, "POST", "/api/render/gbuffer", {"axis": "Z", "kind": "material", "index": 0}
                )
                self.assertEqual(status, 200, raw[:200])
                check_binary(headers, raw, "/api/render/gbuffer")

                # --- ui state / save / export / download ---
                for method, path, body in (
                    ("POST", "/api/ui_state", {"recipe_id": recipe_id, "ui_state": {}}),
                    ("POST", "/api/save", {}),
                    ("POST", "/api/export", {"sti": True}),
                ):
                    status, headers, raw = self._request(base, cookie, method, path, body)
                    self.assertEqual(status, 200, f"{path}: {raw[:200]!r}")
                    check_json(raw, path)
                exported = self._first_string_ending(json.loads(raw), (".zip", ".stl"))
                if exported:
                    status, headers, raw = self._request(base, cookie, "GET", f"/api/export/download?file={exported}")
                    self.assertEqual(status, 200, raw[:120])
                    check_binary(headers, raw, "/api/export/download")
                else:
                    status, headers, raw = self._request(base, cookie, "GET", "/api/export/download?file=__missing__")
                    self.assertEqual(status, 404)
                    check_json(raw, "/api/export/download (404 envelope)")

                # --- reset / autosave / single run / delete ---
                for method, path, body in (
                    ("POST", "/api/reset", {}),
                    ("POST", "/api/load_autosave", {}),
                    ("POST", "/api/run/step", {"index": 0}),
                    ("POST", "/api/recipe/set_name", {"name": "M2 walk renamed"}),
                    ("POST", "/api/recipe/delete", {"id": recipe_id}),
                ):
                    status, headers, raw = self._request(base, cookie, method, path, body)
                    self.assertEqual(status, 200, f"{path}: {raw[:200]!r}")
                    check_json(raw, path)

                status, headers, raw = self._request(base, cookie, "POST", "/api/run/all", {})
                self.assertEqual(status, 200, raw[:200])
                check_json(raw, "/api/run/all")
            finally:
                manager.stop()


class M2ApiDocConsistencyTests(unittest.TestCase):
    """静态一致性：契约表（ARCHITECTURE_TARGET.md）不得与 HTTP dispatcher 漂移。"""

    DOCS_REL = Path("docs") / "ARCHITECTURE_TARGET.md"

    @classmethod
    def _doc_entries(cls):
        import re

        repo_root = Path(__file__).resolve().parents[1]
        text = (repo_root / cls.DOCS_REL).read_text(encoding="utf-8")
        section = text.split("## M2 Compatibility API", 1)[1].split("## Frontend Structure", 1)[0]
        entries = {}
        for line in section.splitlines():
            stripped = line.strip()
            if not stripped.startswith("| `/api/"):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            match = re.match(r"`(/api/[a-z_/-]+)`", cells[0])
            if not match or len(cells) < 2:
                continue
            method = cells[1].strip().strip("`").upper()
            assert method in {"GET", "POST"}, f"bad method cell: {cells[:2]!r}"
            entries[match.group(1)] = method
        return entries

    @classmethod
    def _dispatcher_routes(cls):
        import re

        repo_root = Path(__file__).resolve().parents[1]
        lines = (repo_root / "tcad_simulator.py").read_text(encoding="utf-8").splitlines()

        def find(name, start=0):
            for i in range(start, len(lines)):
                if f"    def {name}(" in lines[i]:
                    return i
            raise AssertionError(f"method {name} not found")

        webui_get = find("do_GET")
        webui_post = find("do_POST", webui_get + 1)
        admin_get = find("do_GET", webui_post + 1)  # WebUI do_POST 区段的终点

        route_re = re.compile(r'path == "(/api/[a-z_/-]+)"')
        set_re = re.compile(r'path in \{"(/api/[a-z_/-]+)", "(/api/[a-z_/-]+)"\}')

        def collect(start, end):
            routes = set()
            for line in lines[start:end]:
                for m in route_re.finditer(line):
                    routes.add(m.group(1))
                for m in set_re.finditer(line):
                    routes.update(m.groups())
            return routes

        return collect(webui_get, webui_post), collect(webui_post, admin_get)

    def test_every_documented_endpoint_exists_with_declared_method(self):
        entries = self._doc_entries()
        self.assertGreaterEqual(len(entries), 40, "contract table looks truncated")
        get_routes, post_routes = self._dispatcher_routes()
        for path, method in sorted(entries.items()):
            in_get = path in get_routes
            in_post = path in post_routes
            self.assertTrue(in_get or in_post, f"{path} documented but missing from dispatchers")
            self.assertFalse(in_get and in_post, f"{path} routed in both GET and POST")
            self.assertEqual(
                ("GET" if in_get else "POST"),
                method,
                f"{path}: doc says {method} but dispatcher disagrees",
            )

    def test_documented_alias_matches_dispatcher(self):
        _get_routes, post_routes = self._dispatcher_routes()
        self.assertIn("/api/run/until", post_routes, "documented alias /api/run/until missing from POST dispatcher")


if __name__ == "__main__":
    unittest.main()
