# -*- coding: utf-8 -*-
"""M7 T1：ProcessBackend 接口与 VoxelBackend（行为不变包装）。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from process_backend import (
    ProcessBackendError,
    VoxelBackend,
    create_backend,
)

GRID = 48
DEMO = "Basic Trench"


class EtchPreparationTests(unittest.TestCase):
    def setUp(self):
        import tcad_simulator as tcad
        self.tcad = tcad
        self.db = tcad.MaterialDatabase()

    def prepare(self, **params):
        return self.tcad._prepare_etch_execution({"material": "Silicon", "chemistry": "Dry", "time": 17, **params}, self.db)

    def test_time_mode_and_sidewall_migration(self):
        plan = self.prepare(sidewall=76)
        self.assertEqual(plan.time_s, 17)
        self.assertEqual(plan.sidewall_angle_deg, 76)
        self.assertEqual(plan.duration_mode, "time")
        step = self.tcad._webui_deserialize_step({"name": "Etch", "params": {"sidewall": 76, "time": 17}}, self.db)
        self.assertEqual(step.params["sidewall_angle_deg"], 76)
        self.assertNotIn("sidewall", step.params)
        restored = self.tcad._webui_deserialize_step(self.tcad._webui_serialize_step(step), self.db)
        self.assertEqual(restored.params["sidewall_angle_deg"], 76)

        override_plan = self.prepare(rate_override=600)
        self.assertEqual(override_plan.rate_source, "rate_override")
        self.assertEqual(override_plan.effective_rate_nm_s, 1)
        self.assertEqual(override_plan.kernel_override_ang_min, 600)

    def test_alias_conflicts_fail(self):
        with self.assertRaisesRegex(ValueError, "冲突"):
            self.prepare(sidewall=76, sidewall_angle_deg=88)
        with self.assertRaisesRegex(ValueError, "冲突"):
            self.tcad._webui_deserialize_step({"name": "Etch", "params": {"sidewall": 76, "sidewall_angle_deg": 88}}, self.db)

    def test_desktop_and_headless_deserializers_migrate_before_controls(self):
        from types import SimpleNamespace
        controller = SimpleNamespace(material_db=self.db)
        deserialize = [lambda blob: self.tcad._headless_deserialize_step(blob, self.db),
                       lambda blob: self.tcad.SimulatorController._deserialize_step(controller, blob)]
        for load in deserialize:
            with self.subTest(load=load):
                step = load({"name": "Etch", "params": {"sidewall": 76, "target_depth_nm": None}})
                self.assertEqual(step.params.get("sidewall_angle_deg"), 76)
                self.assertNotIn("sidewall", step.params)
                self.assertIsNone(step.params["target_depth_nm"])
                with self.assertRaisesRegex(ValueError, "冲突"):
                    load({"name": "Etch", "params": {"sidewall": 76, "sidewall_angle_deg": 88}})

    def test_desktop_serialization_canonicalizes_direct_legacy_params(self):
        from types import SimpleNamespace
        step = self.tcad.EtchStep(self.db)
        step.params["sidewall"] = 76
        serialized = self.tcad.SimulatorController._serialize_step(SimpleNamespace(material_db=self.db), step)
        self.assertEqual(serialized["params"].get("sidewall_angle_deg"), 76)
        self.assertNotIn("sidewall", serialized["params"])
        self.assertEqual(step.params["sidewall"], 76)

    def test_time_mode_rejects_invalid_optional_nominal_rate_and_legacy_depth(self):
        for value in [0, -1, float("nan"), float("inf"), True]:
            with self.subTest(rate=value), self.assertRaises(ValueError):
                self.prepare(nominal_rate_nm_s=value)
        with self.assertRaisesRegex(ValueError, "depth_nm"):
            self.prepare(depth_nm=120)
        self.assertEqual(self.prepare(nominal_rate_nm_s=None).duration_mode, "time")

    def test_depth_mode_and_rate_fallbacks(self):
        plan = self.prepare(target_depth_nm=120, nominal_rate_nm_s=4, rate_override=600)
        self.assertEqual((plan.time_s, plan.rate_nm_s, plan.duration_mode), (30, 4, "estimated"))
        self.assertEqual(plan.effective_rate_nm_s, 4)
        self.assertEqual((plan.rate_source, plan.kernel_override_ang_min), ("nominal_rate_nm_s", 2400))
        self.assertEqual(self.prepare(target_depth_nm=120, rate_override=2400).time_s, 30)
        self.assertEqual(self.prepare(target_depth_nm=120, rate_override=2400).rate_source, "rate_override")
        material = self.db.material(self.db.id_for("Silicon"))
        expected = material.etch_rates_nm_min["Dry"][0] / 60
        database_plan = self.prepare(target_depth_nm=120)
        self.assertAlmostEqual(database_plan.rate_nm_s, expected)
        self.assertEqual(database_plan.rate_source, "material_database")
        self.assertAlmostEqual(database_plan.kernel_override_ang_min, expected * 600)

    def test_rate_override_is_strictly_validated_even_when_not_selected(self):
        for value in [True, float("nan"), float("inf"), -1, 5e-324, 20001]:
            with self.subTest(value=value):
                with self.assertRaises(self.tcad.EtchParameterError) as error:
                    self.prepare(target_depth_nm=120, nominal_rate_nm_s=4, rate_override=value)
                self.assertEqual(error.exception.code, "invalid_parameter")
                self.assertEqual(error.exception.parameter, "rate_override")
        with self.assertRaises(self.tcad.EtchParameterError) as error:
            self.prepare(target_depth_nm=120, nominal_rate_nm_s=1e308, rate_override=0)
        self.assertEqual(error.exception.parameter, "nominal_rate_nm_s")

    def test_selected_rate_conversion_rejects_underflow_and_overflow_with_source_path(self):
        for value in (5e-324, 1e308):
            with self.subTest(source="nominal", value=value):
                with self.assertRaises(self.tcad.EtchParameterError) as error:
                    self.prepare(target_depth_nm=120, nominal_rate_nm_s=value, rate_override=0)
                self.assertEqual(error.exception.parameter, "nominal_rate_nm_s")

        material = self.db.material(self.db.id_for("Silicon"))
        for chemistry, value in (("Underflow", 5e-324), ("Overflow", 1e308)):
            material.etch_rates_nm_min[chemistry] = (value, 1.0)
            with self.subTest(source="material_database", value=value):
                with self.assertRaises(self.tcad.EtchParameterError) as error:
                    self.prepare(target_depth_nm=120, chemistry=chemistry)
                self.assertEqual(error.exception.parameter, "material_rate_nm_min")

    def test_invalid_depth_rates_angles_and_unsupported_incidence(self):
        for value in [0, -1, float("nan"), float("inf")]:
            with self.subTest(depth=value), self.assertRaises(ValueError):
                self.prepare(target_depth_nm=value)
        for value in [0, -1, float("nan"), float("inf")]:
            with self.subTest(rate=value), self.assertRaises(ValueError):
                self.prepare(target_depth_nm=120, nominal_rate_nm_s=value, rate_override=value, chemistry="missing")
        for value in [0, -1, 91, float("nan"), float("inf")]:
            with self.subTest(sidewall=value), self.assertRaises(ValueError):
                self.prepare(sidewall_angle_deg=value)
        for value in [1, -1, 90, float("nan"), float("inf")]:
            with self.subTest(incidence=value), self.assertRaises(ValueError) as error:
                self.prepare(incidence_angle_deg=value)
            self.assertEqual(error.exception.code, "unsupported_parameter")

    def test_execution_metrics_and_failure_do_not_touch_grid(self):
        from unittest.mock import patch
        model = self.tcad.ProcessModel(self.db, grid_shape=(8, 8, 8), voxel_size_nm=10, max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        step = self.tcad.EtchStep(self.db)
        step.params.update(target_depth_nm=120, nominal_rate_nm_s=4, rate_override=600, sidewall_angle_deg=80)
        with patch.object(model, "etch_material") as etch:
            step.execute(model)
            self.assertEqual(etch.call_args.args[2], 30)
            self.assertEqual(etch.call_args.args[4], 2400)
            self.assertEqual(etch.call_args.args[6], 80)
        self.assertEqual(step.last_metrics, {"target_depth_nm": 120, "duration_mode": "estimated", "time_s": 30,
                                             "rate_nm_s": 4, "effective_rate_nm_s": 4,
                                             "rate_source": "nominal_rate_nm_s",
                                             "kernel_override_ang_min": 2400, "capability": "estimated"})
        before = model.grid.copy()
        step.params["incidence_angle_deg"] = 10
        with patch.object(model, "etch_material") as etch, self.assertRaises(ValueError):
            step.execute(model)
        etch.assert_not_called()
        np.testing.assert_array_equal(before, model.grid)

    def test_target_depth_effective_rate_reaches_every_wet_kernel(self):
        from unittest.mock import patch
        model = self.tcad.ProcessModel(self.db, grid_shape=(8, 8, 8), voxel_size_nm=10, max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        for chemistry in ("Wet", "VHF", "HotPhosphoric", "O2", "TMAH", "KOH"):
            with self.subTest(chemistry=chemistry):
                if chemistry in {"TMAH", "KOH"}:
                    with patch.object(model, "_wet_anisotropic_levelset", return_value=0.0) as wet:
                        model.etch_material("Silicon", chemistry, 30, 0, 2400, 4, 88)
                    rate_table = wet.call_args.args[1]
                    self.assertEqual(wet.call_args.args[2], 30)
                    self.assertAlmostEqual(rate_table["100"] / 60.0, 4)
                else:
                    with patch.object(model, "_wet_isotropic_diffusion", return_value=0.0) as wet:
                        model.etch_material("Silicon", chemistry, 30, 0, 2400, 4, 88)
                    self.assertEqual(wet.call_args.args[2], 30)
                    self.assertEqual(wet.call_args.args[4], 4)

    def test_worker_execution_error_preserves_unsupported_code(self):
        model = self.tcad.ProcessModel(self.db, grid_shape=(8, 8, 8), voxel_size_nm=10, max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        step = self.tcad.EtchStep(self.db)
        step.params["incidence_angle_deg"] = 1
        before = model.grid.copy()
        result = self.tcad._run_model_transaction(model, lambda: step.execute(model))
        error = self.tcad._webui_step_execution_error(step, 0, result)
        self.assertEqual(error["code"], "unsupported_parameter")
        self.assertEqual(error["parameter_path"], "incidence_angle_deg")
        np.testing.assert_array_equal(before, model.grid)

    def test_missing_depth_rate_fails_before_kernel_without_grid_mutation(self):
        from unittest.mock import patch
        model = self.tcad.ProcessModel(self.db, grid_shape=(8, 8, 8), voxel_size_nm=10, max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        step = self.tcad.EtchStep(self.db)
        step.params.update(target_depth_nm=120, nominal_rate_nm_s=None, rate_override=0, chemistry="missing")
        before = model.grid.copy()
        with patch.object(model, "etch_material") as etch, self.assertRaises(ValueError):
            step.execute(model)
        etch.assert_not_called()
        np.testing.assert_array_equal(before, model.grid)

    def test_serialization_canonicalizes_direct_legacy_params(self):
        step = self.tcad.EtchStep(self.db)
        step.params.update(sidewall=73)
        serialized = self.tcad._webui_serialize_step(step)
        self.assertEqual(serialized["params"]["sidewall_angle_deg"], 73)
        self.assertNotIn("sidewall", serialized["params"])
        self.assertEqual(step.params["sidewall"], 73)  # serialization is pure

    def test_optional_numeric_text_keeps_none_and_validates_canonical_bounds(self):
        spec = next(s for s in self.tcad.EtchStep(self.db).parameter_specs() if s.key == "target_depth_nm")
        self.assertEqual(self.tcad._format_optional_number(None), "")
        self.assertEqual(self.tcad._parse_optional_number("", spec), None)
        self.assertEqual(self.tcad._parse_optional_number("  ", spec), None)
        self.assertEqual(self.tcad._format_optional_number(120.5), "120.5")
        self.assertEqual(self.tcad._parse_optional_number("120.5", spec), 120.5)
        for text in ["0", "-1", "NaN", "Infinity", "invalid"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.tcad._parse_optional_number(text, spec)


class EtchSidewallCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ast
        from pathlib import Path
        import tcad_simulator as tcad
        cls.tcad = tcad
        tree = ast.parse(Path(tcad.__file__).read_text())
        names = {"_find_downstream_transfer", "_agent_autogen_step_meta", "_agent_variant_defaults_from_step", "_agent_variant_is_meaningful", "_agent_variant_match_score"}
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
        cls.namespace = vars(tcad).copy()
        # Execute the existing nested functions headlessly, not rewritten test proxies.
        exec(compile(ast.Module(body=functions, type_ignores=[]), tcad.__file__, "exec"), cls.namespace)
        # Exercise the actual M2 worker context-copy branch without launching AI.
        for node in ast.walk(tree):
            if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
                continue
            if node.lineno < 60000 or not node.test.comparators:
                continue
            value = node.test.comparators[0]
            if isinstance(value, ast.Constant) and value.value == "Etch" and ast.unparse(node.test.left) == "transfer_ctx['name']":
                cls.worker_context_branch = node
                break

    def test_physics_bias_legacy_and_canonical_angle_are_identical(self):
        db = self.tcad.MaterialDatabase()
        context = {"name": "Etch", "material": "Silicon", "chemistry": "Dry", "time": 17, "rate_override": 600}
        legacy = self.tcad.ProcessPhysicsDB.estimate_etch_bias_nm(transfer_ctx={**context, "sidewall": 74}, material_db=db, voxel_nm=5)
        canonical = self.tcad.ProcessPhysicsDB.estimate_etch_bias_nm(transfer_ctx={**context, "sidewall_angle_deg": 74}, material_db=db, voxel_nm=5)
        self.assertEqual(canonical, legacy)

    def test_existing_transfer_and_step_targets_keep_canonical_angle(self):
        from types import SimpleNamespace
        for key in ("sidewall", "sidewall_angle_deg"):
            step = self.tcad.EtchStep(self.tcad.MaterialDatabase())
            step.params[key] = 74
            context = self.namespace["_find_downstream_transfer"](SimpleNamespace(i=0, steps=[None, step]))
            self.assertEqual(context.get("sidewall_angle_deg", context.get("sidewall")), 74)
            metadata = self.namespace["_agent_autogen_step_meta"]([{"name": "Etch", "params": dict(step.params)}])
            self.assertEqual(metadata[0]["expected_sidewall_deg"], 74)

    def test_existing_variants_keep_and_recognize_canonical_sidewall(self):
        step = self.tcad.EtchStep(self.tcad.MaterialDatabase())
        step.params["sidewall_angle_deg"] = 74
        defaults = self.namespace["_agent_variant_defaults_from_step"](step, changed_keys=[])
        self.assertEqual(defaults.get("sidewall_angle_deg"), 74)
        self.assertTrue(self.namespace["_agent_variant_is_meaningful"]("Etch", ["sidewall_angle_deg"]))

    def test_variant_comparison_migrates_legacy_sidewall(self):
        compare = self.namespace["_agent_variant_match_score"]
        self.assertEqual(compare({"sidewall": 74}, {"sidewall_angle_deg": 74.5}), (1.0, 1))

    def test_worker_context_copy_preserves_new_and_old_angle(self):
        import ast
        for key in ("sidewall", "sidewall_angle_deg"):
            namespace = {**self.namespace, "transfer_ctx": {"name": "Etch"}, "tp": {key: 74}}
            exec(compile(ast.Module(body=[self.worker_context_branch], type_ignores=[]), self.tcad.__file__, "exec"), namespace)
            context = namespace["transfer_ctx"]
            self.assertEqual(context.get("sidewall_angle_deg", context.get("sidewall")), 74)

    def test_sidewall_consumer_rejects_conflicting_aliases(self):
        with self.assertRaisesRegex(ValueError, "冲突"):
            self.tcad.ProcessPhysicsDB.estimate_etch_bias_nm(transfer_ctx={"name": "Etch", "sidewall": 74, "sidewall_angle_deg": 80}, material_db=self.tcad.MaterialDatabase(), voxel_nm=5)


class EtchWorkerContractTests(unittest.TestCase):
    def test_legacy_webui_clears_optional_number_without_zero(self):
        import json
        import subprocess
        import tcad_simulator as tcad
        marker = "input.addEventListener('input', () => {\n        const raw = input.value;"
        body = "const raw = input.value;" + tcad._WEBUI_SCRIPT_JS.split(marker, 1)[1].split("\n      });", 1)[0]
        script = "const input={value:''}, spec={type:'float',key:'target_depth_nm',default:null}, step={params:{target_depth_nm:120}}; const scheduleApplyParams=()=>{};" + body + "; console.log(JSON.stringify(step.params));"
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), {"target_depth_nm": None})

    def test_m2_units_init_and_legacy_edit_preflight(self):
        import tempfile
        from pathlib import Path
        import tcad_simulator as tcad
        with tempfile.TemporaryDirectory() as directory:
            manager = tcad.WebUIServerManager(host="127.0.0.1", port=0, max_users=1,
                storage_root=Path(directory), enable_ai_agent=False,
                default_domain={"grid_shape": [12, 12, 16], "voxel_size_nm": 5.0, "threads": 1})
            manager.start()
            try:
                session, _ = manager.create_session()
                initial = session.rpc("init", {}, timeout_s=30)["result"]
                self.assertEqual(initial["backend_capabilities"], tcad.VOXEL_BACKEND_CAPABILITIES)
                session.rpc("recipe_new", {"name": "Etch units"}, timeout_s=30)
                session.rpc("recipe_insert_steps", {"steps": [{"name": "Etch"}]}, timeout_s=30)
                edited = session.rpc("set_step", {"index": 1, "params": {"sidewall": 76}, "no_autosave": True}, timeout_s=30)
                self.assertTrue(edited["ok"])
                self.assertEqual(edited["result"]["params"]["sidewall_angle_deg"], 76)
                self.assertNotIn("sidewall", edited["result"]["params"])
                invalid = session.rpc("set_step", {"index": 1, "params": {"incidence_angle_deg": 1}}, timeout_s=30)
                self.assertFalse(invalid["ok"])
                self.assertEqual(invalid["code"], "unsupported_parameter")
                after = session.rpc("get_recipe", {}, timeout_s=30)["result"][1]
                self.assertEqual(after["params"]["incidence_angle_deg"], 0)
                for invalid_params in ({"depth_nm": 120}, {"nominal_rate_nm_s": 0}):
                    invalid = session.rpc("set_step", {"index": 1, "params": invalid_params}, timeout_s=30)
                    self.assertFalse(invalid["ok"])
                    self.assertEqual(invalid["code"], "invalid_parameter")
                before_invalid_rates = session.rpc("get_recipe", {}, timeout_s=30)["result"]
                for rate in (True, float("nan"), float("inf"), -1, 5e-324, 20001):
                    with self.subTest(rate=rate):
                        invalid = session.rpc("set_step", {"index": 1, "params": {"rate_override": rate}}, timeout_s=30)
                        self.assertFalse(invalid["ok"], invalid)
                        self.assertEqual(invalid.get("code"), "invalid_parameter")
                        self.assertEqual(invalid.get("parameter_path"), "rate_override")
                        self.assertEqual(session.rpc("get_recipe", {}, timeout_s=30)["result"], before_invalid_rates)
                for rate in (5e-324, 1e308):
                    with self.subTest(parameter="nominal_rate_nm_s", rate=rate):
                        invalid = session.rpc("set_step", {"index": 1, "params": {
                            "target_depth_nm": 120,
                            "nominal_rate_nm_s": rate,
                        }}, timeout_s=30)
                        self.assertFalse(invalid["ok"], invalid)
                        self.assertEqual(invalid.get("code"), "invalid_parameter")
                        self.assertEqual(invalid.get("parameter_path"), "nominal_rate_nm_s")
                        self.assertEqual(session.rpc("get_recipe", {}, timeout_s=30)["result"], before_invalid_rates)
                imported = session.rpc("recipe_import", {"recipe": {"name": "Legacy Etch", "steps": [
                    {"name": "Etch", "params": {"sidewall": 74, "time": 17, "target_depth_nm": None, "nominal_rate_nm_s": None}}
                ]}}, timeout_s=30)
                self.assertTrue(imported["ok"], imported)
                imported_params = session.rpc("get_recipe", {}, timeout_s=30)["result"][0]["params"]
                self.assertEqual(imported_params["sidewall_angle_deg"], 74)
                self.assertNotIn("sidewall", imported_params)
                self.assertIsNone(imported_params["target_depth_nm"])
                self.assertIsNone(imported_params["nominal_rate_nm_s"])
                filled = session.rpc("set_step", {"index": 0, "params": {"target_depth_nm": 120, "nominal_rate_nm_s": 4}}, timeout_s=30)
                self.assertTrue(filled["ok"], filled)
                cleared = session.rpc("set_step", {"index": 0, "params": {"target_depth_nm": None, "nominal_rate_nm_s": None}}, timeout_s=30)
                self.assertTrue(cleared["ok"], cleared)
                self.assertIsNone(cleared["result"]["params"]["target_depth_nm"])
                self.assertIsNone(cleared["result"]["params"]["nominal_rate_nm_s"])
                before_import = session.rpc("get_recipe", {}, timeout_s=30)["result"]
                invalid_import = session.rpc("recipe_import", {"recipe": {"steps": [
                    {"name": "Etch", "params": {"incidence_angle_deg": 5}}
                ]}}, timeout_s=30)
                self.assertFalse(invalid_import["ok"])
                self.assertEqual(invalid_import.get("code"), "unsupported_parameter")
                self.assertEqual(invalid_import.get("parameter_path"), "incidence_angle_deg")
                self.assertEqual(session.rpc("get_recipe", {}, timeout_s=30)["result"], before_import)
                invalid_rate_imports = [
                    ({"rate_override": True}, "rate_override"),
                    ({"rate_override": 5e-324}, "rate_override"),
                    ({"target_depth_nm": 120, "nominal_rate_nm_s": 5e-324}, "nominal_rate_nm_s"),
                    ({"target_depth_nm": 120, "nominal_rate_nm_s": 1e308}, "nominal_rate_nm_s"),
                ]
                for params, expected_path in invalid_rate_imports:
                    with self.subTest(params=params):
                        invalid_rate_import = session.rpc("recipe_import", {"recipe": {"steps": [
                            {"name": "Etch", "params": params}
                        ]}}, timeout_s=30)
                        self.assertFalse(invalid_rate_import["ok"])
                        self.assertEqual(invalid_rate_import.get("code"), "invalid_parameter")
                        self.assertEqual(invalid_rate_import.get("parameter_path"), expected_path)
                        self.assertEqual(session.rpc("get_recipe", {}, timeout_s=30)["result"], before_import)
            finally:
                manager.stop()


def make_backend() -> VoxelBackend:
    return create_backend("voxel", grid=GRID)


class BackendInterfaceTests(unittest.TestCase):
    def test_info_and_registry(self) -> None:
        backend = make_backend()
        info = backend.info()
        self.assertEqual(info.name, "voxel")
        self.assertEqual(info.precision, "voxel")
        self.assertIsInstance(info.version, str)

    def test_registry_unknown_backend_raises(self) -> None:
        with self.assertRaises(ProcessBackendError) as ctx:
            create_backend("__no_such_backend__")
        self.assertEqual(ctx.exception.code, "unknown_backend")

    def test_summary_matches_model(self) -> None:
        backend = make_backend()
        summary = backend.summary()
        self.assertEqual(summary.grid_shape, (GRID, GRID, GRID))
        self.assertGreater(summary.voxel_size_nm, 0.0)

    def test_snapshot_restore_round_trip(self) -> None:
        import tcad_simulator as tcad

        backend = make_backend()
        database = tcad.MaterialDatabase()
        step = tcad._webui_deserialize_step(
            tcad.load_demo_flows(database)[DEMO]["steps"][0], database,
        )
        backend.execute_step(step)
        grid_before = backend.grid().copy()
        state = backend.snapshot()

        backend.execute_step(
            tcad._webui_deserialize_step(
                tcad.load_demo_flows(database)[DEMO]["steps"][1], database,
            )
        )
        self.assertFalse(np.array_equal(backend.grid(), grid_before))

        backend.restore(state)
        np.testing.assert_array_equal(backend.grid(), grid_before)


class VoxelParityTests(unittest.TestCase):
    def test_backend_matches_direct_execution(self) -> None:
        import tcad_simulator as tcad

        # 路径 A：VoxelBackend
        backend = make_backend()
        database_a = tcad.MaterialDatabase()
        for blob in tcad.load_demo_flows(database_a)[DEMO]["steps"]:
            step = tcad._webui_deserialize_step(blob, database_a)
            self.assertIsNotNone(step)
            outcome = backend.execute_step(step)
            self.assertTrue(str(outcome.message).strip())

        # 路径 B：直接 ProcessModel（既有契约）
        database_b = tcad.MaterialDatabase()
        model = tcad.ProcessModel(
            database_b,
            grid_shape=(GRID, GRID, GRID),
            voxel_size_nm=640.0 / GRID,
            max_workers=1,
        )
        try:
            for blob in tcad.load_demo_flows(database_b)[DEMO]["steps"]:
                step = tcad._webui_deserialize_step(blob, database_b)
                step.execute(model)

            np.testing.assert_array_equal(backend.grid(), model.grid)

            surfaces_backend = backend.material_surfaces(face_limit=20000)
            surfaces_direct = model.get_material_surfaces(face_limit=20000)
            self.assertEqual(
                [mat_id for mat_id, _ in surfaces_backend],
                [mat_id for mat_id, _ in surfaces_direct],
            )
            for (_, tri_a), (_, tri_b) in zip(surfaces_backend, surfaces_direct):
                np.testing.assert_allclose(tri_a, tri_b)
        finally:
            model.parallel.shutdown()
            backend.shutdown()


if __name__ == "__main__":
    unittest.main()


class ViennaPSBackendTests(unittest.TestCase):
    """M9：几何后端注册、能力回退与双引擎标定（引擎需已安装）。"""

    def _skip_if_no_engine(self) -> None:
        from process_backend import engine_available

        if not engine_available():
            self.skipTest("viennaps 未安装（见 experiments/viennaps/README.md）")

    def test_registered_with_geometry_precision(self) -> None:
        self._skip_if_no_engine()
        from process_backend import create_backend

        backend = create_backend("viennaps", grid_nm=16.0)
        info = backend.info()
        self.assertEqual(info.name, "viennaps")
        self.assertEqual(info.precision, "geometry")
        self.assertIn("viennaps", __import__("process_backend", fromlist=["available_backends"]).available_backends())

    def test_unsupported_step_falls_back_explicitly(self) -> None:
        self._skip_if_no_engine()
        from process_backend import create_backend

        backend = create_backend("viennaps")
        class FakeStep:
            name = "Spin Resist"
            params = {}
        with self.assertRaises(ProcessBackendError) as ctx:
            backend.execute_step(FakeStep())
        self.assertEqual(ctx.exception.code, "unsupported_step")
        self.assertIn("voxel", str(ctx.exception.suggestion))

    def test_initialize_etch_and_snapshot_round_trip(self) -> None:
        self._skip_if_no_engine()
        import tcad_simulator as tcad
        from process_backend import create_backend

        backend = create_backend("viennaps", grid_nm=16.0)
        class Step:
            def __init__(self, name, params):
                self.name, self.params = name, params
        backend.execute_step(Step("Initialize Wafer", {"thickness_nm": 200.0}))
        surfaces = backend.material_surfaces(20000)
        self.assertEqual(len(surfaces), 1)
        mat_id, triangles = surfaces[0]
        self.assertGreater(triangles.shape[0], 0)
        self.assertEqual(triangles.shape[1:], (3, 3))
        surface_z_max = float(triangles[:, :, 2].max())

        state = backend.snapshot()
        backend.execute_step(Step("Etch", {"time": 10.0, "chemistry": "Dry"}))
        tri_after = backend.material_surfaces(20000)[0][1]
        depth_after = float(tri_after[:, :, 2].max() - tri_after[:, :, 2].min())

        backend.restore(state)
        tri_restored = backend.material_surfaces(20000)[0][1]
        self.assertAlmostEqual(
            float(tri_restored[:, :, 2].max()), surface_z_max, places=9,
        )
        backend.shutdown()

    def test_grid_raises_geometry_error(self) -> None:
        self._skip_if_no_engine()
        from process_backend import create_backend

        backend = create_backend("viennaps")
        class Step:
            name, params = "Initialize Wafer", {"thickness_nm": 200.0}
        backend.execute_step(Step())
        with self.assertRaises(ProcessBackendError) as ctx:
            backend.grid()
        self.assertEqual(ctx.exception.code, "geometry_backend")

    def test_calibration_etch_depth_both_engines(self) -> None:
        """双引擎标定：同目标刻蚀，报告并宽限比较刻蚀深度量级。"""
        self._skip_if_no_engine()
        import tcad_simulator as tcad
        from process_backend import create_backend

        # 体素引擎：Initialize + Etch(Dry 30s)
        voxel = create_backend("voxel", grid=64)
        database = tcad.MaterialDatabase()
        flow = tcad.load_demo_flows(database)["Basic Trench"]["steps"]
        voxel.execute_step(tcad._webui_deserialize_step(flow[0], database))
        etch = next(
            tcad._webui_deserialize_step(blob, database)
            for blob in flow
            if blob.get("name") == "Etch"
        )
        voxel.execute_step(etch)
        void_id = next(
            mid for mid, material in database.items() if material.name == "Void"
        )
        grid = voxel.grid()
        import numpy as np
        silicon_id = next(
            mid for mid, material in database.items() if material.name == "Silicon"
        )
        heights = np.nonzero(grid == silicon_id)[2]
        voxel_depth_nm = float((heights.max() - heights.min()) + 1) * voxel.summary().voxel_size_nm
        voxel.shutdown()

        # 几何引擎：Initialize(200nm) + Etch(30s)
        geometry = create_backend("viennaps", grid_nm=16.0)
        class Step:
            def __init__(self, name, params):
                self.name, self.params = name, params
        geometry.execute_step(Step("Initialize Wafer", {"thickness_nm": 200.0}))
        top_before = float(geometry.material_surfaces(40000)[0][1][:, :, 2].max())
        geometry.execute_step(Step("Etch", {"time": 30.0, "chemistry": "Dry"}))
        top_after = float(geometry.material_surfaces(40000)[0][1][:, :, 2].max())
        geo_depth_nm = (top_before - top_after) * 1000.0
        geometry.shutdown()

        print(f"\n[calibration] voxel etch depth ≈ {voxel_depth_nm:.1f} nm | "
              f"viennaps ≈ {geo_depth_nm:.1f} nm | ratio ≈ {geo_depth_nm / max(voxel_depth_nm, 1e-9):.2f}")
        # 宽容量级断言：两个物理模型都应产生明显刻蚀
        self.assertGreater(voxel_depth_nm, 0.0)
        self.assertGreater(geo_depth_nm, 0.0)
        ratio = geo_depth_nm / max(voxel_depth_nm, 1e-9)
        self.assertTrue(0.2 <= ratio <= 3.0, f"标定漂移：ratio={ratio:.2f}")
