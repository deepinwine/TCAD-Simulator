import json
import math
import unittest

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
