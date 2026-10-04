# -*- coding: utf-8 -*-
"""M4 ProcessCadFacade：类型化 schema 与核心行为（T1）。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

from process_api import (  # noqa: E402
    InitView,
    MaterialView,
    ModelSummaryView,
    ParameterSpecView,
    ProcessCadError,
    ProcessCadFacade,
    RunView,
    StepView,
    to_json,
)

GRID = 48
DEMO = "Basic Trench"


def make_facade() -> ProcessCadFacade:
    facade = ProcessCadFacade(grid=GRID)
    facade.load_demo(DEMO)
    return facade


class SchemaShapeTests(unittest.TestCase):
    """序列化键名必须与冻结契约（frontend/src/api/types.ts）逐字段一致。"""

    def test_optional_numeric_defaults_remain_explicit_null_in_typed_view(self):
        facade = make_facade()
        etch = next(s for s in facade.recipe() if s.name == "Etch")
        for key in ("target_depth_nm", "nominal_rate_nm_s"):
            spec = next(s for s in etch.parameterSpecs if s.key == key).to_json()
            self.assertIn("defaultValue", spec)
            self.assertIsNone(spec["defaultValue"])


    def test_unit_metadata_and_capabilities(self):
        import tcad_simulator as tcad
        spec = tcad.ParameterSpec("depth", "Depth", "float", None, dimension="length", canonical_unit="nm", display_units=("nm", "µm"), capability_key="etch.target_depth")
        legacy = tcad._webui_serialize_parameter_spec(spec)
        self.assertEqual([legacy[k] for k in ("dimension", "canonical_unit", "display_units", "capability_key")], ["length", "nm", ["nm", "µm"], "etch.target_depth"])
        view = ParameterSpecView(key=spec.key, label=spec.label, type=spec.type, dimension=spec.dimension, canonical_unit=spec.canonical_unit, display_units=spec.display_units, capability_key=spec.capability_key)
        self.assertEqual(view.to_json()["displayUnits"], ["nm", "µm"])
        facade = make_facade()
        self.assertEqual(facade.init().to_json()["backendCapabilities"]["etch.incidence_angle"], "unsupported")
        etch = next(s for s in facade.recipe() if s.name == "Etch")
        depth = next(s for s in etch.parameterSpecs if s.key == "target_depth_nm")
        self.assertEqual(depth.to_json()["canonicalUnit"], "nm")

    def test_unsupported_incidence_is_stable_error_without_model_mutation(self):
        import numpy as np
        facade = make_facade()
        index = next(s.index for s in facade.recipe() if s.name == "Etch")
        before = facade._model.grid.copy()
        with self.assertRaises(ProcessCadError) as error:
            facade.set_step(index, params={"incidence_angle_deg": 5})
        self.assertEqual(error.exception.code, "unsupported_parameter")
        np.testing.assert_array_equal(before, facade._model.grid)

    def test_import_unsupported_incidence_preserves_code_and_session(self):
        import numpy as np
        facade = make_facade()
        self.addCleanup(facade._model.parallel.shutdown)
        before = facade._model.grid.copy()
        recipe = [step.to_json() for step in facade.recipe()]
        with self.assertRaises(ProcessCadError) as error:
            facade.load_recipe_blob({"steps": [{"name": "Etch", "params": {"incidence_angle_deg": 5}}]})
        self.assertEqual(error.exception.code, "unsupported_parameter")
        self.assertEqual(error.exception.parameter_path, "incidence_angle_deg")
        np.testing.assert_array_equal(before, facade._model.grid)
        self.assertEqual(recipe, [step.to_json() for step in facade.recipe()])

    def test_import_invalid_rate_override_preserves_path_and_session(self):
        facade = make_facade()
        self.addCleanup(facade._model.parallel.shutdown)
        recipe = [step.to_json() for step in facade.recipe()]
        for rate in (True, float("nan"), float("inf"), -1, 5e-324, 20001):
            with self.subTest(rate=rate):
                with self.assertRaises(ProcessCadError) as error:
                    facade.load_recipe_blob({"steps": [{"name": "Etch", "params": {"rate_override": rate}}]})
                self.assertEqual(error.exception.code, "invalid_parameter")
                self.assertEqual(error.exception.parameter_path, "rate_override")
                self.assertEqual(recipe, [step.to_json() for step in facade.recipe()])

        for rate in (5e-324, 1e308):
            with self.subTest(parameter="nominal_rate_nm_s", rate=rate):
                with self.assertRaises(ProcessCadError) as error:
                    facade.load_recipe_blob({"steps": [{"name": "Etch", "params": {
                        "target_depth_nm": 120,
                        "nominal_rate_nm_s": rate,
                    }}]})
                self.assertEqual(error.exception.code, "invalid_parameter")
                self.assertEqual(error.exception.parameter_path, "nominal_rate_nm_s")
                self.assertEqual(recipe, [step.to_json() for step in facade.recipe()])

    def test_set_step_invalid_rate_override_preserves_path_and_session(self):
        facade = make_facade()
        self.addCleanup(facade._model.parallel.shutdown)
        index = next(step.index for step in facade.recipe() if step.name == "Etch")
        recipe = [step.to_json() for step in facade.recipe()]
        statuses = [step.runtimeStatus for step in facade.recipe()]
        for rate in (True, float("nan"), float("inf"), -1, 5e-324, 20001):
            with self.subTest(rate=rate):
                with self.assertRaises(ProcessCadError) as error:
                    facade.set_step(index, params={"rate_override": rate})
                self.assertEqual(error.exception.code, "invalid_parameter")
                self.assertEqual(error.exception.parameter_path, "rate_override")
                self.assertEqual(recipe, [step.to_json() for step in facade.recipe()])
                self.assertEqual(statuses, [step.runtimeStatus for step in facade.recipe()])

        for rate in (5e-324, 1e308):
            with self.subTest(parameter="nominal_rate_nm_s", rate=rate):
                with self.assertRaises(ProcessCadError) as error:
                    facade.set_step(index, params={"target_depth_nm": 120, "nominal_rate_nm_s": rate})
                self.assertEqual(error.exception.code, "invalid_parameter")
                self.assertEqual(error.exception.parameter_path, "nominal_rate_nm_s")
                self.assertEqual(recipe, [step.to_json() for step in facade.recipe()])
                self.assertEqual(statuses, [step.runtimeStatus for step in facade.recipe()])

    def test_step_view_json_keys(self) -> None:
        step = StepView(
            index=0,
            name="Initialize Wafer",
            instanceName="Initialize Wafer",
            group="",
            loop="",
            enabled=True,
            params={"wafer_type": "Bulk"},
            parameterSpecs=[
                ParameterSpecView(key="wafer_type", label="Wafer type", type="choice"),
            ],
            runtimeStatus="ready",
        )
        payload = to_json(step)
        self.assertEqual(
            set(payload.keys()),
            {
                "index", "name", "instanceName", "group", "loop", "enabled",
                "params", "parameterSpecs", "runtimeStatus",
            },
        )
        spec = payload["parameterSpecs"][0]
        self.assertEqual(spec["key"], "wafer_type")
        self.assertEqual(spec["label"], "Wafer type")
        self.assertEqual(spec["type"], "choice")

    def test_init_view_json_keys(self) -> None:
        view = InitView(
            recipe=[],
            model=ModelSummaryView(gridShape=(8, 8, 8), voxelSizeNm=10.0),
            factories=["Initialize Wafer"],
            materials=[MaterialView(id=1, name="Silicon", color=(0.6, 0.6, 0.65), enabled=True)],
            uiState={},
        )
        payload = to_json(view)
        self.assertEqual(
            set(payload.keys()), {"recipe", "model", "factories", "materials", "uiState"},
        )
        self.assertEqual(set(payload["model"].keys()), {"gridShape", "voxelSizeNm"})
        self.assertEqual(
            set(payload["materials"][0].keys()), {"id", "name", "color", "enabled"},
        )

    def test_run_view_json_keys(self) -> None:
        payload = to_json(RunView(index=0, runtimeStatus="done", modelRevision=3))
        self.assertEqual(
            set(payload.keys()),
            {"index", "runtimeStatus", "modelRevision"},
        )


class FacadeCoreTests(unittest.TestCase):
    def test_requires_recipe_before_use(self) -> None:
        facade = ProcessCadFacade(grid=GRID)
        with self.assertRaises(ProcessCadError) as ctx:
            facade.init()
        self.assertEqual(ctx.exception.code, "no_recipe")
        self.assertIn("recipe", str(ctx.exception))

    def test_load_demo_init_view(self) -> None:
        facade = make_facade()
        view = facade.init()
        self.assertGreater(len(view.recipe), 0)
        self.assertTrue(
            all(step.runtimeStatus == "ready" for step in view.recipe),
            [s.runtimeStatus for s in view.recipe],
        )
        self.assertGreater(len(view.factories), 0)
        self.assertTrue(all(isinstance(name, str) for name in view.factories))
        material_names = [material.name for material in view.materials]
        self.assertIn("Silicon", material_names)
        payload = to_json(view)
        self.assertEqual(payload["model"]["gridShape"], [GRID, GRID, 72])
        self.assertAlmostEqual(payload["model"]["voxelSizeNm"], 640.0 / GRID)

    def test_run_all_marks_done_and_increments_revision(self) -> None:
        facade = make_facade()
        revision_before = facade.model_revision()
        result = facade.run_all()
        self.assertEqual(result.runtimeStatus, "done")
        self.assertEqual(result.index, facade.recipe()[-1].index)
        self.assertGreater(facade.model_revision(), revision_before)
        statuses = [step.runtimeStatus for step in facade.recipe()]
        self.assertTrue(all(status == "done" for status in statuses), statuses)

    def test_run_step_marks_later_steps_dirty(self) -> None:
        facade = make_facade()
        first = facade.recipe()[0].index
        result = facade.run_step(first)
        self.assertEqual(result.index, first)
        statuses = {step.index: step.runtimeStatus for step in facade.recipe()}
        self.assertEqual(statuses[first], "done")
        later = [status for index, status in statuses.items() if index > first]
        self.assertTrue(later, "demo recipe should have later steps")
        self.assertTrue(all(status == "dirty" for status in later), later)

    def test_parity_with_direct_runtime(self) -> None:
        import numpy as np

        import tcad_simulator as tcad

        facade = make_facade()
        facade.run_all()

        database = tcad.MaterialDatabase()
        recipe = tcad.load_demo_flows(database)[DEMO]
        model = tcad.ProcessModel(
            database,
            grid_shape=(GRID, GRID, 72),
            voxel_size_nm=640.0 / GRID,
            max_workers=1,
        )
        try:
            for blob in recipe["steps"]:
                if not blob.get("enabled", True):
                    continue
                step = tcad._webui_deserialize_step(blob, database)
                self.assertIsNotNone(step)
                step.execute(model)
            void_id = next(
                mid for mid, material in database.items() if material.name == "Void"
            )
            direct_occupied = int(np.count_nonzero(model.grid != void_id))
            direct_materials = sorted(
                material.name
                for mid, material in database.items()
                if mid != void_id and bool(np.any(model.grid == mid))
            )
        finally:
            model.parallel.shutdown()

        self.assertEqual(facade.occupied_voxels(), direct_occupied)
        self.assertEqual(facade.present_material_names(), direct_materials)


class FacadeRecipeLoadingTests(unittest.TestCase):
    def make_facade(self):
        facade = make_facade()
        self.addCleanup(lambda: facade._model.parallel.shutdown())
        return facade

    def test_har_demo_keeps_declared_extent_at_requested_resolution(self):
        import numpy as np
        facade = self.make_facade()
        facade.load_demo("HAR Trench (DRIE)")
        summary = facade.model_summary()
        self.assertEqual(summary.gridShape, (48, 48, 72))
        self.assertAlmostEqual(summary.voxelSizeNm, 640.0 / 48)
        facade.run_all()
        self.assertTrue(all(step.runtimeStatus == "done" for step in facade.recipe()))
        grid = facade._model.grid
        silicon = grid == facade._database.id_for("Silicon")
        field_top = np.flatnonzero(silicon[4, 24])[-1]
        trench_top = np.flatnonzero(silicon[24, 24])[-1]
        self.assertGreater((field_top - trench_top) * summary.voxelSizeNm, 300)
        self.assertTrue(np.all(grid[24, 24, trench_top + 1:] == 0))
        self.assertTrue(np.any(grid == facade._database.id_for("Silicon Dioxide")))

    def test_explicit_recipe_domain_is_used_exactly_and_input_is_copied(self):
        facade = self.make_facade()
        blob = {"domain": {"grid_shape": [40, 32, 80], "voxel_size_nm": 7.5},
                "steps": [{"name": "Initialize Wafer", "params": {"thickness_nm": 300.0}}]}
        facade.load_recipe_blob(blob)
        self.assertEqual(facade.model_summary().gridShape, (40, 32, 80))
        self.assertEqual(facade.model_summary().voxelSizeNm, 7.5)
        self.assertEqual(facade._model.grid.shape, (40, 32, 80))
        blob["steps"][0]["params"]["thickness_nm"] = -1
        blob["domain"]["grid_shape"][2] = 1
        self.assertEqual(facade.recipe()[0].params["thickness_nm"], 300.0)
        facade.run_all()
        self.assertEqual(facade.occupied_voxels(), 40 * 32 * 40)
        facade.load_demo(DEMO)
        self.assertEqual(facade.model_summary().gridShape, (48, 48, 72))
        self.assertAlmostEqual(facade.model_summary().voxelSizeNm, 640.0 / 48)

    def test_invalid_recipe_preserves_geometry_recipe_revision_and_timeline(self):
        import numpy as np
        facade = self.make_facade()
        facade.run_to(1)
        before = to_json(facade.init())
        timeline = to_json(facade.get_timeline())
        revision = facade.model_revision()
        old_model = facade._model
        grid = old_model.grid.copy()
        invalid = [
            {"steps": [{"name": "Unknown process", "params": {}}]},
            {"steps": [{"name": "Deposition", "params": {"thickness": -1}}]},
            {"steps": [{"name": "Etch", "params": {"depth_nm": 100}}]},
            {"steps_full": [{"name": "Initialize Wafer"}],
             "steps": [{"name": "Unknown process", "params": {}}]},
            {"domain": {"grid_shape": [32, 32, 32], "voxel_size_nm": 5.0},
             "steps": [{"name": "Initialize Wafer", "params": {"thickness_nm": 300.0}}]},
            {"domain": {"grid_shape": [32, 32, 0]}, "steps": [{"name": "Initialize Wafer"}]},
            {"domain": {"voxel_size_nm": float("nan")}, "steps": [{"name": "Initialize Wafer"}]},
            {"domain": {"grid_shape": [8, 8, 20], "voxel_size_nm": 5.0},
             "steps": [{"name": "Mask Exposure", "mask_file": {"not": "a path"}}]},
            {"steps": [None]},
            {"steps": []},
        ]
        for blob in invalid:
            with self.subTest(blob=blob):
                with self.assertRaises(ProcessCadError) as ctx:
                    facade.load_recipe_blob(blob)
                self.assertEqual(ctx.exception.code, "invalid_recipe")
                self.assertIs(facade._model, old_model)
                np.testing.assert_array_equal(facade._model.grid, grid)
                self.assertEqual(to_json(facade.init()), before)
                self.assertEqual(to_json(facade.get_timeline()), timeline)
                self.assertEqual(facade.model_revision(), revision)
        self.assertEqual(facade.run_step(2).runtimeStatus, "done")

    def test_invalid_material_rate_preserves_domain_error_and_loaded_state(self):
        import numpy as np
        facade = self.make_facade()
        facade.run_to(1)
        old_model = facade._model
        recipe = [step.to_json() for step in facade.recipe()]
        timeline = to_json(facade.get_timeline())
        revision = facade.model_revision()
        grid = old_model.grid.copy()
        silicon = facade._database.material(facade._database.id_for("Silicon"))

        for chemistry, rate in (("Underflow", 5e-324), ("Overflow", 1e308)):
            silicon.etch_rates_nm_min[chemistry] = (rate, 1.0)
            with self.subTest(chemistry=chemistry, rate=rate):
                with self.assertRaises(ProcessCadError) as error:
                    facade.load_recipe_blob({"steps": [{"name": "Etch", "params": {
                        "material": "Silicon",
                        "chemistry": chemistry,
                        "target_depth_nm": 120,
                    }}]})
                self.assertEqual(error.exception.code, "invalid_parameter")
                self.assertEqual(error.exception.parameter_path, "material_rate_nm_min")
                self.assertIs(facade._model, old_model)
                np.testing.assert_array_equal(facade._model.grid, grid)
                self.assertEqual([step.to_json() for step in facade.recipe()], recipe)
                self.assertEqual(to_json(facade.get_timeline()), timeline)
                self.assertEqual(facade.model_revision(), revision)

    def test_model_allocation_failure_preserves_loaded_state(self):
        from unittest import mock
        facade = self.make_facade()
        facade.run_step(0)
        old_model = facade._model
        before = to_json(facade.init())
        timeline = to_json(facade.get_timeline())
        with mock.patch.object(facade._tcad, "ProcessModel", side_effect=MemoryError("allocation failed")):
            with self.assertRaises(ProcessCadError) as ctx:
                facade.load_recipe_blob({"domain": {"grid_shape": [32, 32, 80], "voxel_size_nm": 5.0},
                                         "steps": [{"name": "Initialize Wafer"}]})
        self.assertEqual(ctx.exception.code, "invalid_recipe")
        self.assertIs(facade._model, old_model)
        self.assertEqual(to_json(facade.init()), before)
        self.assertEqual(to_json(facade.get_timeline()), timeline)
        self.assertEqual(facade.run_step(1).runtimeStatus, "done")

    def test_inherited_partial_domain_is_validated_before_state_swap(self):
        facade = self.make_facade()
        facade.load_recipe_blob({"domain": {"grid_shape": [32, 32, 32], "voxel_size_nm": 5.0},
                                 "steps": [{"name": "Initialize Wafer", "params": {"thickness_nm": 100.0}}]})
        facade.run_all()
        old_model = facade._model
        before = to_json(facade.init())
        revision = facade.model_revision()
        for blob in (
            {"steps": [{"name": "Initialize Wafer", "params": {"thickness_nm": 300.0}}]},
            {"domain": {"grid_shape": [32, 32, 32]},
             "steps": [{"name": "Initialize Wafer", "params": {"thickness_nm": 300.0}}]},
            {"domain": {"voxel_size_nm": 5.0},
             "steps": [{"name": "Initialize Wafer", "params": {"thickness_nm": 300.0}}]},
        ):
            with self.subTest(blob=blob), self.assertRaises(ProcessCadError):
                facade.load_recipe_blob(blob)
            self.assertIs(facade._model, old_model)
            self.assertEqual(to_json(facade.init()), before)
            self.assertEqual(facade.model_revision(), revision)


def _find_numeric_spec(step: StepView):
    for spec in step.parameterSpecs:
        if spec.minimum is not None and isinstance(spec.default_value, (int, float)):
            return spec
    return None


def _find_choice_spec(step: StepView):
    for spec in step.parameterSpecs:
        if spec.choices:
            return spec
    return None


class FacadeSetStepTests(unittest.TestCase):
    def test_effective_raw_parameters_stay_consistent_through_edit_execute_and_export(self):
        from copy import deepcopy
        import tcad_simulator as tcad
        facade = ProcessCadFacade(grid=8)
        self.addCleanup(lambda: facade._model.parallel.shutdown())
        facade.load_recipe_blob({"steps": [{"name": "Etch", "params": {"sidewall": 74, "time": 9000},
            "params_raw": {"sidewall": 74, "rf_bias": 321.0, "time": 17.0}}]})
        for patch, expected_angle, expected_depth, expected_rate in [
            ({"sidewall_angle_deg": 80, "target_depth_nm": 120, "nominal_rate_nm_s": 4}, 80, 120, 4),
            ({"sidewall": 76}, 76, 120, 4),
            ({"target_depth_nm": None, "nominal_rate_nm_s": None}, 76, None, None),
        ]:
            edited = facade.set_step(0, params=patch)
            self.assertEqual(edited.step.params["sidewall_angle_deg"], expected_angle)
            self.assertEqual(edited.step.params["target_depth_nm"], expected_depth)
            self.assertEqual(edited.step.params["nominal_rate_nm_s"], expected_rate)
            self.assertEqual(edited.step.params["rf_bias"], 321)
            self.assertEqual(edited.step.params["time"], 17)
            self.assertEqual(edited.step.params, facade.recipe()[0].params)
            executed = facade._deserialize(0)
            executed.execute(facade._model)
            self.assertEqual(executed.last_metrics["target_depth_nm"], expected_depth)
            self.assertEqual(executed.last_metrics["duration_mode"], "time" if expected_depth is None else "estimated")
            self.assertEqual(executed.last_metrics["time_s"], 17 if expected_depth is None else 30)
            self.assertEqual(executed.last_metrics["rate_nm_s"], expected_rate)
            exported = tcad._webui_export_step_blob_compat(deepcopy(facade._blobs[0]), facade._database)
            restored = ProcessCadFacade(grid=8)
            try:
                restored.load_recipe_blob({"steps": [exported]})
                self.assertEqual(restored.recipe()[0].params, facade.recipe()[0].params)
                replay = restored._deserialize(0)
                replay.execute(restored._model)
                self.assertEqual(replay.last_metrics, executed.last_metrics)
            finally:
                restored._model.parallel.shutdown()
        before = deepcopy(facade._blobs)
        statuses = [step.runtimeStatus for step in facade.recipe()]
        with self.assertRaises(ProcessCadError):
            facade.set_step(0, params={"sidewall": 74, "sidewall_angle_deg": 80})
        self.assertEqual(facade._blobs, before)
        self.assertEqual([step.runtimeStatus for step in facade.recipe()], statuses)

    def test_set_step_updates_params_and_cascades_dirty(self) -> None:
        facade = make_facade()
        target = facade.recipe()[1]
        numeric = _find_numeric_spec(target)
        self.assertIsNotNone(numeric)
        revision_before = facade.model_revision()

        result = facade.set_step(1, params={numeric.key: numeric.default_value})

        self.assertEqual(result.step.index, 1)
        self.assertEqual(result.step.params[numeric.key], numeric.default_value)
        statuses = {step.index: step.runtimeStatus for step in facade.recipe()}
        self.assertEqual(statuses[0], "ready")
        self.assertEqual(statuses[1], "dirty")
        self.assertTrue(
            all(status == "dirty" for index, status in statuses.items() if index > 1),
            statuses,
        )
        self.assertEqual(facade.model_revision(), revision_before)
        payload = to_json(result)
        self.assertEqual(
            set(payload.keys()), {"step", "statuses", "warnings"},
        )
        self.assertEqual(len(payload["statuses"]), len(facade.recipe()))

    def test_set_step_unknown_key_raises_without_side_effects(self) -> None:
        facade = make_facade()
        statuses_before = [step.runtimeStatus for step in facade.recipe()]
        with self.assertRaises(ProcessCadError) as ctx:
            facade.set_step(0, params={"__no_such_key__": 1})
        self.assertEqual(ctx.exception.code, "unknown_parameter")
        self.assertEqual(ctx.exception.parameter_path, "__no_such_key__")
        self.assertEqual(
            [step.runtimeStatus for step in facade.recipe()], statuses_before,
        )

    def test_set_step_out_of_range_raises_with_parameter_path(self) -> None:
        facade = make_facade()
        numeric = _find_numeric_spec(facade.recipe()[0])
        self.assertIsNotNone(numeric)
        bad = float(numeric.minimum) - 1.0
        with self.assertRaises(ProcessCadError) as ctx:
            facade.set_step(0, params={numeric.key: bad})
        self.assertEqual(ctx.exception.code, "invalid_parameter")
        self.assertEqual(ctx.exception.parameter_path, numeric.key)

    def test_set_step_choice_value_enforced(self) -> None:
        facade = make_facade()
        for step in facade.recipe():
            choice = _find_choice_spec(step)
            if choice is None:
                continue
            with self.assertRaises(ProcessCadError) as ctx:
                facade.set_step(step.index, params={choice.key: "__bogus_choice__"})
            self.assertEqual(ctx.exception.code, "invalid_parameter")
            self.assertEqual(ctx.exception.parameter_path, choice.key)
            return
        self.skipTest("demo recipe has no choice parameter")

    def test_set_step_enabled_toggle_and_run_all_skips(self) -> None:
        facade = make_facade()
        result = facade.set_step(1, enabled=False)
        self.assertFalse(result.step.enabled)
        run = facade.run_all()
        self.assertEqual(run.runtimeStatus, "done")
        statuses = {step.index: step.runtimeStatus for step in facade.recipe()}
        self.assertEqual(statuses[1], "done")


class FacadeTimelineTests(unittest.TestCase):
    def test_run_to_executes_prefix_and_timeline_shape(self) -> None:
        facade = make_facade()
        facade.run_to(2)
        statuses = {step.index: step.runtimeStatus for step in facade.recipe()}
        for index in range(0, 3):
            self.assertEqual(statuses[index], "done", statuses)
        self.assertTrue(all(status == "dirty" for i, status in statuses.items() if i > 2))

        timeline = facade.get_timeline()
        payload = to_json(timeline)
        self.assertEqual(set(payload.keys()), {"items", "current"})
        self.assertEqual(payload["current"], 2)
        self.assertEqual(len(payload["items"]), len(facade.recipe()))
        item = payload["items"][2]
        self.assertEqual(
            set(item.keys()), {"index", "state", "runtimeStatus", "snapshotValid"},
        )
        self.assertEqual(item["state"], "current")
        self.assertEqual(item["runtimeStatus"], "done")
        self.assertTrue(item["snapshotValid"])
        later = payload["items"][4]
        self.assertFalse(later["snapshotValid"])

    def test_run_to_after_edit_reruns_only_dirty_prefix(self) -> None:
        facade = make_facade()
        facade.run_to(2)
        numeric = _find_numeric_spec(facade.recipe()[1])
        self.assertIsNotNone(numeric)
        facade.set_step(1, params={numeric.key: numeric.default_value})
        revision_after_edit = facade.model_revision()
        result = facade.run_to(2)
        self.assertEqual(result.index, 2)
        statuses = {step.index: step.runtimeStatus for step in facade.recipe()}
        self.assertTrue(
            all(statuses[i] == "done" for i in range(0, 3)), statuses,
        )
        self.assertGreater(facade.model_revision(), revision_after_edit)

    def test_restore_timeline_invalid_snapshot_raises(self) -> None:
        facade = make_facade()
        with self.assertRaises(ProcessCadError) as ctx:
            facade.restore_timeline(3)
        self.assertEqual(ctx.exception.code, "invalid_snapshot")

    def test_restore_timeline_restores_model_state(self) -> None:
        facade = make_facade()
        facade.run_all()
        full_voxels = facade.occupied_voxels()

        reference = make_facade()
        reference.run_step(0)
        step0_voxels = reference.occupied_voxels()
        self.assertNotEqual(full_voxels, step0_voxels)

        restored = facade.restore_timeline(0)
        payload = to_json(restored)
        self.assertEqual(
            set(payload.keys()), {"timeline", "model", "recipe", "log"},
        )
        self.assertEqual(payload["timeline"]["current"], 0)
        self.assertEqual(facade.occupied_voxels(), step0_voxels)

    def test_get_timeline_before_any_run_is_current_minus_one(self) -> None:
        facade = make_facade()
        timeline = facade.get_timeline()
        self.assertEqual(to_json(timeline)["current"], -1)
        self.assertFalse(all(item.snapshotValid for item in timeline.items))


import struct  # noqa: E402


class FacadeGeometryTests(unittest.TestCase):
    def test_manifest_shape_and_revision_semantics(self) -> None:
        facade = make_facade()
        before = facade.preview_manifest()
        self.assertEqual(before.revision, facade.model_revision())
        # 与服务端会话契约一致：新会话即含衬底（Initialized substrate）
        substrate = [m for m in before.meshes if m.name == "Silicon"]
        self.assertEqual(len(substrate), 1)

        facade.run_all()
        manifest = facade.preview_manifest()
        self.assertEqual(manifest.revision, facade.model_revision())
        self.assertGreaterEqual(len(manifest.meshes), 1)
        silicon = [m for m in manifest.meshes if m.name == "Silicon"]
        self.assertEqual(len(silicon), 1)
        mesh = silicon[0]
        self.assertGreater(mesh.materialId, 0)
        self.assertGreater(mesh.triangleCount, 0)
        for axis in range(3):
            self.assertLessEqual(mesh.boundingBox.min[axis], mesh.boundingBox.max[axis])
        visual = mesh.visual
        self.assertEqual(visual.displayName, "Silicon")
        self.assertEqual(len(visual.color), 3)
        self.assertTrue(0.0 <= visual.opacity <= 1.0)
        self.assertTrue(0.0 <= visual.metallic <= 1.0)
        self.assertTrue(0.0 <= visual.roughness <= 1.0)
        self.assertTrue(visual.visible)

        payload = to_json(manifest)
        self.assertEqual(set(payload.keys()), {"revision", "mode", "meshes"})
        mesh_payload = payload["meshes"][0]
        self.assertEqual(
            set(mesh_payload.keys()),
            {"materialId", "name", "triangleCount", "boundingBox", "visual"},
        )
        self.assertEqual(
            set(mesh_payload["boundingBox"].keys()), {"min", "max"},
        )
        self.assertEqual(
            set(mesh_payload["visual"].keys()),
            {
                "materialId", "displayName", "color", "opacity",
                "metallic", "roughness", "visible",
            },
        )

    def test_material_stl_binary_matches_manifest(self) -> None:
        facade = make_facade()
        facade.run_all()
        manifest = facade.preview_manifest()
        mesh = manifest.meshes[0]

        data = facade.material_stl(mesh.materialId, manifest.revision)
        self.assertGreater(len(data), 84)
        count = struct.unpack("<I", data[80:84])[0]
        self.assertEqual(count, mesh.triangleCount)
        self.assertEqual(len(data), 84 + 50 * count)

    def test_material_stl_stale_revision_rejected(self) -> None:
        facade = make_facade()
        facade.run_all()
        with self.assertRaises(ProcessCadError) as ctx:
            facade.material_stl(1, facade.model_revision() - 1)
        self.assertEqual(ctx.exception.code, "stale_revision")


if __name__ == "__main__":
    unittest.main()
