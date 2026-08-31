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


if __name__ == "__main__":
    unittest.main()
