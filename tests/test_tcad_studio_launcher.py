"""M12：桌面启动器冒烟测试。"""
import os
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")


class LauncherTests(unittest.TestCase):
    def test_import_and_find_port(self):
        from tcad_studio import find_free_port
        port = find_free_port(18765)
        self.assertTrue(18765 <= port < 18865)

    def test_py_compile(self):
        import py_compile
        py_compile.compile("tcad_studio.py", doraise=True)
        py_compile.compile("tcad_studio.spec", doraise=True,
                           cfile="/tmp/_spec.pyc")  # spec 不是 .py，但语法兼容


class LauncherLifecycleTests(unittest.TestCase):
    def setUp(self):
        import tcad_studio
        self.studio = tcad_studio
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.manager = Mock(port=18767)
        self.timer = Mock()
        self.factory = self._patch("tcad_simulator.WebUIServerManager", return_value=self.manager)
        self._patch("tcad_studio.Path.home", return_value=Path(self.temp_dir.name))
        self.port = self._patch("tcad_studio.find_free_port", return_value=18765)
        self._patch("sys.argv", ["tcad_studio.py", "--no-browser"])
        self.sleep = self._patch("tcad_studio.time.sleep", side_effect=KeyboardInterrupt)
        self.timer_factory = self._patch("tcad_studio.threading.Timer", return_value=self.timer)
        self.browser = self._patch("tcad_studio.webbrowser.open")

    def _patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_ctrl_c_stops_manager_once_and_returns_zero_without_browser(self):
        self.assertEqual(self.studio.main(), 0)
        self.manager.start.assert_called_once_with()
        self.manager.stop.assert_called_once_with()
        self.factory.assert_called_once_with(
            storage_root=str(Path(self.temp_dir.name) / ".tcad-studio"),
            host="127.0.0.1", port=18765,
        )
        self.timer_factory.assert_not_called()
        self.browser.assert_not_called()

    def test_runtime_error_stops_manager_and_propagates_same_exception(self):
        error = RuntimeError("runtime failed")
        self.sleep.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.studio.main()
        self.assertIs(caught.exception, error)
        self.manager.stop.assert_called_once_with()

    def test_startup_error_stops_partially_started_manager(self):
        error = RuntimeError("startup failed")
        self.manager.start.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.studio.main()
        self.assertIs(caught.exception, error)
        self.manager.stop.assert_called_once_with()
        self.sleep.assert_not_called()

    def test_ctrl_c_during_startup_stops_manager_and_returns_zero(self):
        self.manager.start.side_effect = KeyboardInterrupt
        try:
            result = self.studio.main()
        except KeyboardInterrupt:
            self.fail("startup Ctrl+C escaped without managed cleanup")
        self.assertEqual(result, 0)
        self.manager.stop.assert_called_once_with()

    def test_browser_timer_uses_one_second_and_bound_studio_url(self):
        with patch("sys.argv", ["tcad_studio.py"]):
            self.assertEqual(self.studio.main(), 0)
        delay, callback = self.timer_factory.call_args.args
        self.assertEqual(delay, 1.0)
        self.timer.start.assert_called_once_with()
        self.timer.cancel.assert_called_once_with()
        self.manager.stop.assert_called_once_with()
        self.browser.assert_not_called()
        callback()
        self.browser.assert_called_once_with("http://127.0.0.1:18767/studio/")

    def test_timer_construction_error_stops_manager_and_propagates(self):
        error = RuntimeError("timer construction failed")
        self.timer_factory.side_effect = error
        with patch("sys.argv", ["tcad_studio.py"]), self.assertRaises(RuntimeError) as caught:
            self.studio.main()
        self.assertIs(caught.exception, error)
        self.manager.stop.assert_called_once_with()

    def test_timer_start_error_cancels_timer_and_stops_manager(self):
        error = RuntimeError("timer start failed")
        self.timer.start.side_effect = error
        with patch("sys.argv", ["tcad_studio.py"]), self.assertRaises(RuntimeError) as caught:
            self.studio.main()
        self.assertIs(caught.exception, error)
        self.timer.cancel.assert_called_once_with()
        self.manager.stop.assert_called_once_with()

    def test_timer_cancel_error_still_stops_manager(self):
        error = RuntimeError("timer cancel failed")
        self.timer.cancel.side_effect = error
        with patch("sys.argv", ["tcad_studio.py"]), self.assertRaises(RuntimeError) as caught:
            self.studio.main()
        self.assertIs(caught.exception, error)
        self.manager.stop.assert_called_once_with()

    def test_constructor_error_does_not_stop_unconstructed_manager(self):
        error = RuntimeError("constructor failed")
        self.factory.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.studio.main()
        self.assertIs(caught.exception, error)
        self.manager.stop.assert_not_called()

    def test_port_error_does_not_construct_manager(self):
        error = RuntimeError("no port")
        self.port.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.studio.main()
        self.assertIs(caught.exception, error)
        self.factory.assert_not_called()
        self.manager.stop.assert_not_called()


class LauncherShutdownPersistenceTests(unittest.TestCase):
    def test_ctrl_c_flushes_latest_edit_before_same_session_restart(self):
        import tcad_simulator as tcad
        import tcad_studio as studio
        from structure_cad.display_provenance import validate_source_bound_identities
        from tests.test_webui_cad_shell import CadShellWorkerHistoryTests

        fixture = CadShellWorkerHistoryTests()
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = fixture._start_manager(Path(temp_dir) / ".tcad-studio")
            resumed_manager = None
            captured = {}

            def rpc(session, command, payload=None):
                response = session.rpc(command, payload or {}, timeout_s=30.0)
                self.assertTrue(response["ok"], response)
                return response["result"]

            def edit_then_interrupt(_seconds):
                session, _cookie = manager.create_session()
                self.assertIsNotNone(session)
                rpc(session, "recipe_new", {"name": "Launcher shutdown"})
                rpc(session, "run_step", {"index": 0})
                rpc(session, "recipe_add", {
                    "name": "Structure Deposit",
                    "params": {"material": "Germanium", "thickness_nm": 20},
                })
                rpc(session, "run_step", {"index": 1})
                captured["before"] = rpc(session, "init")
                captured["manifest"] = rpc(session, "structure_display_manifest")
                captured["session_id"] = session.session_id
                captured["secret"] = session.secret
                captured["storage"] = session.storage_dir
                # Skip the edit autosave deliberately: shutdown must flush it without waiting.
                edited = rpc(session, "set_step", {
                    "index": 1, "params": {"thickness_nm": 35}, "no_autosave": True,
                })
                captured["edited"] = edited["params"]
                raise KeyboardInterrupt

            try:
                with patch("sys.argv", ["tcad_studio.py", "--no-browser"]), \
                        patch("tcad_studio.Path.home", return_value=Path(temp_dir)), \
                        patch("tcad_studio.find_free_port", return_value=manager.port), \
                        patch("tcad_simulator.WebUIServerManager", return_value=manager), \
                        patch.object(studio, "time", SimpleNamespace(sleep=edit_then_interrupt)), \
                        patch.object(manager._httpd, "shutdown", wraps=manager._httpd.shutdown) as shutdown, \
                        patch.object(manager._httpd, "server_close", wraps=manager._httpd.server_close) as close, \
                        patch("tcad_studio.webbrowser.open") as browser:
                    self.assertEqual(studio.main(), 0)
                    shutdown.assert_called_once_with()
                    close.assert_called_once_with()
                    browser.assert_not_called()
                self.assertFalse(manager.running)
                self.assertEqual(manager.sessions, {})
                self.assertIsNone(manager._httpd)
                self.assertIsNone(manager._thread)
                blob = tcad._webui_pickle_load(captured["storage"] / "autosave.pkl.gz")
                # Stored material names are normalized to IDs in the client response.
                self.assertEqual(blob["steps_full"][1]["params"]["thickness_nm"], 35)
                self.assertEqual(blob["steps_full"][1]["params"]["material"], "Germanium")
                self.assertIsNotNone(blob["model_state"]["display_owners"])
                validate_source_bound_identities(blob["steps_full"], blob["model_state"])

                resumed_manager = fixture._start_manager(Path(temp_dir) / ".tcad-studio")
                resumed, _cookie = resumed_manager.create_session(
                    session_id=captured["session_id"], secret=captured["secret"],
                )
                self.assertIsNotNone(resumed)
                current = rpc(resumed, "init")
                self.assertEqual(current["recipe"][1]["params"], captured["edited"])
                self.assertEqual(current["model"], captured["before"]["model"])
                manifest = rpc(resumed, "structure_display_manifest")
                self.assertTrue(manifest["owner_step_ids"])
                self.assertEqual(manifest["owner_step_ids"], captured["manifest"]["owner_step_ids"])
                self.assertTrue(set(manifest["owner_step_ids"].values()).issubset(
                    step["step_id"] for step in current["recipe"]))
            finally:
                manager.stop()
                if resumed_manager is not None:
                    resumed_manager.stop()


class LauncherPartialStartupTests(unittest.TestCase):
    def _assert_thread_start_failure_cleans_up(self, error):
        import tcad_simulator as tcad
        import tcad_studio as studio

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = tcad.WebUIServerManager(
                host="127.0.0.1", port=0, storage_root=Path(temp_dir) / ".tcad-studio",
                enable_ai_agent=False,
                default_domain={"grid_shape": [12, 12, 16], "voxel_size_nm": 5.0, "threads": 1},
            )
            # Real stdlib shutdown blocks forever if serve_forever never ran.
            server = socketserver.BaseServer(("127.0.0.1", 0), None)
            server.shutdown = Mock(wraps=server.shutdown)
            server.server_close = Mock(wraps=server.server_close)
            session = Mock()
            manager.sessions["existing"] = session
            stop = Mock(wraps=manager.stop)
            sleep = Mock(side_effect=AssertionError("failed startup reached runtime loop"))
            done = threading.Event()
            outcome = {}

            def launch():
                try:
                    with patch("sys.argv", ["tcad_studio.py", "--no-browser"]), \
                            patch("tcad_studio.Path.home", return_value=Path(temp_dir)), \
                            patch("tcad_studio.find_free_port", return_value=0), \
                            patch("tcad_simulator.WebUIServerManager", return_value=manager), \
                            patch("tcad_simulator._WebUIHTTPServer", return_value=server), \
                            patch.object(manager, "ensure_static_assets"), \
                            patch.object(manager, "stop", stop), \
                            patch.object(studio, "time", SimpleNamespace(sleep=sleep)), \
                            patch.object(threading.Thread, "start", side_effect=error):
                        outcome["result"] = studio.main()
                except BaseException as caught:
                    outcome["error"] = caught
                finally:
                    done.set()

            runner = threading.Thread(target=launch, daemon=True)
            runner.start()
            try:
                completed = done.wait(timeout=1.0)
            finally:
                # Release the original bug's shutdown wait before reporting RED.
                server._BaseServer__is_shut_down.set()
                runner.join(timeout=2.0)
            self.assertFalse(runner.is_alive(), "partial-start cleanup test leaked its runner")
            self.assertTrue(completed, "stop blocked on a server whose service thread never started")
            stop.assert_called_once_with()
            server.shutdown.assert_not_called()
            server.server_close.assert_called_once_with()
            session.rpc.assert_called_once_with("shutdown", {}, timeout_s=5.0)
            session.conn.close.assert_called_once_with()
            session.process.terminate.assert_called_once_with()
            self.assertEqual(manager.sessions, {})
            self.assertIsNone(manager._httpd)
            self.assertIsNone(manager._thread)
            sleep.assert_not_called()
            if isinstance(error, KeyboardInterrupt):
                self.assertEqual(outcome, {"result": 0})
            else:
                self.assertIs(outcome.get("error"), error)

    def test_service_thread_start_error_closes_server_and_propagates(self):
        self._assert_thread_start_failure_cleans_up(RuntimeError("thread start failed"))

    def test_service_thread_start_ctrl_c_closes_server_and_returns_zero(self):
        self._assert_thread_start_failure_cleans_up(KeyboardInterrupt())


if __name__ == "__main__":
    unittest.main()
