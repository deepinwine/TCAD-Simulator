import json
import math
import unittest
from dataclasses import FrozenInstanceError

import tcad_simulator as tcad


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
