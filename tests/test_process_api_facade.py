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
        self.assertEqual(payload["model"]["gridShape"], [GRID, GRID, GRID])

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
            grid_shape=(GRID, GRID, GRID),
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
