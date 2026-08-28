import unittest

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


if __name__ == "__main__":
    unittest.main()
