import json
import math
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import tcad_simulator as tcad


class StepRuntimeStatusTests(unittest.TestCase):
    def test_invalidate_from_preserves_earlier_done_steps(self):
        statuses = ["done", "done", "done", "ready"]
        actual = tcad._invalidate_step_statuses(statuses, start_index=2, recipe_length=4)
        self.assertEqual(actual, ["done", "done", "dirty", "dirty"])

    def test_statuses_are_resized_to_recipe_length(self):
        actual = tcad._normalize_step_statuses(["done"], recipe_length=3)
        self.assertEqual(actual, ["done", "ready", "ready"])

    def test_invalid_statuses_and_lengths_are_normalized_safely(self):
        self.assertEqual(
            tcad._normalize_step_statuses(["DONE", "unknown", None], recipe_length=3),
            ["done", "ready", "ready"],
        )
        self.assertEqual(tcad._normalize_step_statuses(["done"], recipe_length=-1), [])
        self.assertEqual(tcad._normalize_step_statuses(["done"], recipe_length="invalid"), [])

    def test_invalidate_clamps_start_index(self):
        self.assertEqual(
            tcad._invalidate_step_statuses(["done", "done"], start_index=-4, recipe_length=2),
            ["dirty", "dirty"],
        )
        self.assertEqual(
            tcad._invalidate_step_statuses(["done", "ready"], start_index=9, recipe_length=2),
            ["done", "ready"],
        )
        self.assertEqual(
            tcad._invalidate_step_statuses(["done", "ready"], start_index="invalid", recipe_length=2),
            ["dirty", "dirty"],
        )

    def test_helpers_do_not_mutate_list_or_tuple_inputs(self):
        values_list = ["done", "ready"]
        values_tuple = ("done", "ready")
        tcad._normalize_step_statuses(values_list, recipe_length=3)
        tcad._invalidate_step_statuses(values_tuple, start_index=1, recipe_length=2)
        self.assertEqual(values_list, ["done", "ready"])
        self.assertEqual(values_tuple, ("done", "ready"))

    def test_worker_recipe_payload_tracks_edit_invalidation_without_persisting_status(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = tcad.WebUIServerManager(
                    host="127.0.0.1",
                    port=0,
                    max_users=1,
                    storage_root=Path(temp_dir),
                    enable_ai_agent=False,
                    default_domain={"grid_shape": [32, 32, 32], "voxel_size_nm": 5.0, "threads": 1},
                )
                manager.start()
                session, _cookie = manager.create_session()
                self.assertIsNotNone(session)

                init_result = session.rpc("init", {}, timeout_s=30.0)["result"]
                recipe = init_result["recipe"]
                self.assertTrue(recipe)
                self.assertEqual([step["runtime_status"] for step in recipe], ["ready"] * len(recipe))

                fetched = session.rpc("get_recipe", {}, timeout_s=30.0)["result"]
                self.assertEqual([step["runtime_status"] for step in fetched], ["ready"] * len(fetched))

                edited = session.rpc(
                    "set_step",
                    {"index": 0, "enabled": not bool(fetched[0]["enabled"]), "no_autosave": True},
                    timeout_s=30.0,
                )["result"]
                self.assertEqual(edited["runtime_status"], "dirty")
                fetched = session.rpc("get_recipe", {}, timeout_s=30.0)["result"]
                self.assertEqual([step["runtime_status"] for step in fetched], ["dirty"] * len(fetched))

                new_recipe = session.rpc("recipe_new", {"name": "Runtime status test"}, timeout_s=30.0)["result"]["recipe"]
                self.assertEqual([step["runtime_status"] for step in new_recipe], ["ready"])

                added = session.rpc(
                    "recipe_add", {"name": "Anneal", "no_autosave": True}, timeout_s=30.0
                )["result"]
                self.assertEqual(len(added), 2)
                self.assertEqual([step["runtime_status"] for step in added], ["ready", "dirty"])

                inserted_response = session.rpc(
                    "recipe_insert_steps",
                    {"insert_index": 0, "steps": [{"name": "CMP"}], "no_autosave": True},
                    timeout_s=30.0,
                )
                inserted = inserted_response["result"]
                self.assertEqual(len(inserted), 3)
                self.assertEqual(inserted_response["meta"]["inserted_at"], 1)
                self.assertEqual([step["runtime_status"] for step in inserted], ["ready", "dirty", "dirty"])

                session.rpc("reset", {}, timeout_s=30.0)
                reset_recipe = session.rpc("get_recipe", {}, timeout_s=30.0)["result"]
                self.assertEqual([step["runtime_status"] for step in reset_recipe], ["ready", "ready", "ready"])

                moved = session.rpc("recipe_move", {"index": 2, "direction": "up"}, timeout_s=30.0)["result"]
                self.assertEqual([step["runtime_status"] for step in moved], ["ready", "dirty", "dirty"])
                no_op = session.rpc("recipe_move", {"index": 0, "direction": "up"}, timeout_s=30.0)["result"]
                self.assertEqual([step["runtime_status"] for step in no_op], ["ready", "dirty", "dirty"])

                duplicated = session.rpc("recipe_duplicate", {"index": 0}, timeout_s=30.0)["result"]
                self.assertEqual([step["runtime_status"] for step in duplicated], ["ready", "dirty", "dirty", "dirty"])
                removed_last = session.rpc("recipe_remove", {"index": 3}, timeout_s=30.0)["result"]
                self.assertEqual([step["runtime_status"] for step in removed_last], ["ready", "dirty", "dirty"])

                exported = session.rpc("recipe_export", {"scope": "current"}, timeout_s=30.0)["result"]
                self.assertTrue(exported["steps_full"])
                self.assertTrue(all("runtime_status" not in step for step in exported["steps_full"]))

                loaded = session.rpc(
                    "load_recipe_ephemeral", {"recipe": exported}, timeout_s=30.0
                )["result"]["recipe"]
                self.assertEqual([step["runtime_status"] for step in loaded], ["ready"] * len(loaded))

                factory_step = tcad.PROCESS_STEP_FACTORIES["Anneal"](tcad.MaterialDatabase())
                self.assertNotIn("runtime_status", tcad._webui_serialize_step(factory_step))
            finally:
                if manager is not None:
                    manager.stop()


class MaterialVisualTests(unittest.TestCase):
    def test_default_visual_inherits_physical_material(self):
        db = tcad.MaterialDatabase()
        silicon_id = db.id_for("Silicon")
        visual = db.material_visual(silicon_id)
        self.assertEqual(visual.material_id, silicon_id)
        self.assertEqual(visual.display_name, "Silicon")
        self.assertEqual(tuple(visual.color), tuple(db.material(silicon_id).color))
        self.assertEqual(visual.opacity, 1.0)
        self.assertTrue(visual.visible)

    def test_visual_override_is_clamped_without_mutating_material(self):
        db = tcad.MaterialDatabase()
        silicon_id = db.id_for("Silicon")
        original = tuple(db.material(silicon_id).color)
        visual = db.material_visual(
            silicon_id,
            {"display_name": "Device Si", "color": [2.0, -1.0, 0.5], "opacity": 1.4},
        )
        self.assertEqual(visual.display_name, "Device Si")
        self.assertEqual(visual.color, (1.0, 0.0, 0.5))
        self.assertEqual(visual.opacity, 1.0)
        self.assertEqual(tuple(db.material(silicon_id).color), original)

    def test_non_finite_visual_override_values_fall_back_to_defaults(self):
        db = tcad.MaterialDatabase()
        silicon_id = db.id_for("Silicon")
        original_color = tuple(db.material(silicon_id).color)
        visual = db.material_visual(
            silicon_id,
            {
                "color": [math.nan, math.inf, -math.inf],
                "opacity": math.nan,
                "metallic": math.inf,
                "roughness": -math.inf,
            },
        )
        self.assertEqual(visual.color, original_color)
        self.assertEqual(visual.opacity, 1.0)
        self.assertEqual(visual.metallic, 0.0)
        self.assertEqual(visual.roughness, 0.72)
        json.dumps(visual.as_dict(), allow_nan=False)

    def test_visual_value_object_rejects_non_finite_values_and_serializes_strict_json(self):
        with self.assertRaises(ValueError):
            tcad.MaterialVisual(1, "Silicon", (math.nan, 0.6, 0.65))
        with self.assertRaises(ValueError):
            tcad.MaterialVisual(1, "Silicon", (0.6, 0.6, 0.65), opacity=math.inf)

        visual = tcad.MaterialVisual(1, "Silicon", (0.6, 0.6, 0.65))
        json.dumps(visual.as_dict(), allow_nan=False)
        with self.assertRaises(FrozenInstanceError):
            visual.opacity = 0.5

    def test_visual_override_rejects_invalid_color_visibility_and_display_name(self):
        db = tcad.MaterialDatabase()
        silicon_id = db.id_for("Silicon")
        material = db.material(silicon_id)

        visual = db.material_visual(
            silicon_id,
            {"color": "123", "visible": "false", "display_name": "   "},
        )
        self.assertEqual(visual.color, material.color)
        self.assertTrue(visual.visible)
        self.assertEqual(visual.display_name, material.name)

        visual = db.material_visual(silicon_id, {"display_name": 123})
        self.assertEqual(visual.display_name, material.name)

    def test_visual_override_clamps_finite_scalars_and_preserves_false_visibility(self):
        db = tcad.MaterialDatabase()
        silicon_id = db.id_for("Silicon")
        visual = db.material_visual(
            silicon_id,
            {"metallic": -0.5, "roughness": 1.5, "visible": False},
        )
        self.assertEqual(visual.metallic, 0.0)
        self.assertEqual(visual.roughness, 1.0)
        self.assertFalse(visual.visible)


class RecipeCompatibilityTests(unittest.TestCase):
    def test_legacy_step_without_instance_name_keeps_factory_name(self):
        db = tcad.MaterialDatabase()
        step = tcad._webui_deserialize_step(
            {"name": "Deposition", "enabled": True, "params": {"material": "Silicon Dioxide"}},
            db,
        )
        self.assertIsNotNone(step)
        self.assertEqual(step.name, "Deposition")
        self.assertEqual(step.instance_name, "Deposition")

    def test_legacy_label_is_used_when_instance_name_is_missing(self):
        db = tcad.MaterialDatabase()
        step = tcad._webui_deserialize_step(
            {"name": "Deposition", "label": " Legacy label ", "params": {}},
            db,
        )
        self.assertIsNotNone(step)
        self.assertEqual(step.name, "Deposition")
        self.assertEqual(step.instance_name, "Legacy label")

    def test_instance_name_round_trip_does_not_change_factory_name(self):
        db = tcad.MaterialDatabase()
        step = tcad.PROCESS_STEP_FACTORIES["Etch"](db)
        step.instance_name = "Gate trench etch"
        restored = tcad._webui_deserialize_step(tcad._webui_serialize_step(step), db)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.name, "Etch")
        self.assertEqual(restored.instance_name, "Gate trench etch")

    def test_invalid_instance_names_fall_back_or_truncate_without_changing_factory_name(self):
        db = tcad.MaterialDatabase()
        for value, expected in (
            (123, "Etch"),
            ("   ", "Etch"),
            ("x" * 100, "x" * 80),
        ):
            with self.subTest(value=value):
                step = tcad._webui_deserialize_step(
                    {"name": "Etch", "instance_name": value, "params": {}},
                    db,
                )
                self.assertIsNotNone(step)
                self.assertEqual(step.name, "Etch")
                self.assertEqual(step.instance_name, expected)
