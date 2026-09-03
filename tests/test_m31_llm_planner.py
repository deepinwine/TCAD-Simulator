"""M31: Schema-guided LLM Recipe Planner tests."""
import json, os, unittest
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

from recipe_planner.llm_planner import (
    build_llm_prompt, is_complex, parse_llm_response, plan_recipe,
)
from recipe_planner import RecipeDraft


class ComplexityDetectionTests(unittest.TestCase):
    def test_simple_is_not_complex(self):
        self.assertFalse(is_complex("在Si上沉积100 nm SiO2，刻蚀50 nm"))

    def test_sadp_is_complex(self):
        self.assertTrue(is_complex("SADP spacer formation with mandrel"))

    def test_chinese_sadp_is_complex(self):
        self.assertTrue(is_complex("形成侧墙后去除芯轴，以侧墙为掩膜刻蚀"))

    def test_bond_flip_is_complex(self):
        self.assertTrue(is_complex("bond the second wafer, flip and thin to stop layer"))


class LLMPromptTests(unittest.TestCase):
    def test_prompt_contains_schema(self):
        prompt = build_llm_prompt("test input")
        self.assertIn("available_step_types", prompt)
        self.assertIn("available_materials", prompt)
        self.assertIn("output_schema", prompt)
        self.assertIn("rules", prompt)
        # Should include real factory names
        self.assertIn("Deposition", prompt)
        self.assertIn("Etch", prompt)


class LLMResponseParsingTests(unittest.TestCase):
    def test_valid_json_response(self):
        response = json.dumps({
            "steps": [
                {"type": "Initialize Wafer", "params": {"material": "Silicon", "thickness_nm": 400}, "confidence": 0.99, "sourceSpan": "on Si"},
                {"type": "Deposition", "params": {"material": "SiO2", "thickness_nm": 100}, "confidence": 0.95, "sourceSpan": "deposit 100nm SiO2"},
            ],
            "ambiguities": [],
            "warnings": [],
        })
        draft = parse_llm_response(response)
        self.assertEqual(len(draft.steps), 2)
        self.assertEqual(draft.steps[0].type, "Initialize Wafer")
        self.assertEqual(draft.steps[1].params["material"], "Silicon Dioxide")  # Normalized

    def test_markdown_wrapped_response(self):
        response = '```json\n{"steps": [{"type": "Etch", "params": {"depth_nm": 50}, "confidence": 0.9}], "ambiguities": []}\n```'
        draft = parse_llm_response(response)
        self.assertEqual(len(draft.steps), 1)
        self.assertEqual(draft.steps[0].type, "Etch")

    def test_invalid_json_produces_warning(self):
        draft = parse_llm_response("this is not json at all")
        self.assertGreater(len(draft.warnings), 0)
        self.assertIn("JSON", draft.warnings[0])

    def test_material_normalization(self):
        response = json.dumps({
            "steps": [{"type": "Deposition", "params": {"material": "二氧化硅", "thickness_nm": 50}}],
        })
        draft = parse_llm_response(response)
        self.assertEqual(draft.steps[0].params["material"], "Silicon Dioxide")

    def test_ambiguities_preserved(self):
        response = json.dumps({
            "steps": [],
            "ambiguities": ["pitch not specified", "mask polarity unclear"],
        })
        draft = parse_llm_response(response)
        self.assertEqual(len(draft.ambiguities), 2)

    def test_validation_errors_appended(self):
        response = json.dumps({
            "steps": [{"type": "NonExistentStep", "params": {}}],
        })
        draft = parse_llm_response(response)
        # Should have validation warnings
        self.assertTrue(
            any("未知" in w or "unknown" in w.lower() for w in draft.warnings),
            f"Expected validation warning, got: {draft.warnings}",
        )


class DualModePlanTests(unittest.TestCase):
    def test_simple_uses_rule_parser(self):
        draft = plan_recipe("在Si上沉积100 nm SiO2")
        self.assertGreater(len(draft.steps), 0)
        self.assertEqual(draft.steps[0].type, "Initialize Wafer")

    def test_complex_without_llm_falls_back_with_warning(self):
        draft = plan_recipe("SADP spacer process with mandrel removal")
        self.assertGreater(len(draft.warnings), 0)
        self.assertIn("规则", "".join(draft.warnings))

    def test_complex_with_mock_llm(self):
        def mock_llm(prompt):
            return json.dumps({
                "steps": [
                    {"type": "Initialize Wafer", "params": {"material": "Silicon", "thickness_nm": 400}},
                    {"type": "Deposition", "params": {"material": "Polysilicon", "thickness_nm": 100}},
                    {"type": "Etch", "params": {"depth_nm": 80}},
                ],
                "ambiguities": ["spacer thickness not specified"],
            })
        draft = plan_recipe("SADP spacer with mandrel", llm_fn=mock_llm)
        self.assertGreaterEqual(len(draft.steps), 2)
        self.assertEqual(len(draft.ambiguities), 1)


class SafetyBoundaryTests(unittest.TestCase):
    """LLM 绝不直接调用 ProcessModel——只产出 RecipeDraft。"""

    def test_llm_output_is_draft_not_model(self):
        def mock_llm(prompt):
            return json.dumps({"steps": [{"type": "Etch", "params": {"depth_nm": 50}}]})
        draft = plan_recipe("SADP test", llm_fn=mock_llm)
        self.assertIsInstance(draft, RecipeDraft)
        # Draft has no reference to ProcessModel
        self.assertFalse(hasattr(draft, "execute"))
        self.assertFalse(hasattr(draft, "model"))

    def test_no_auto_run(self):
        """plan_recipe 不会自动执行任何步骤。"""
        from recipe_planner.llm_planner import plan_recipe
        draft = plan_recipe("在Si上沉积100 nm SiO2")
        # Verify no simulation was triggered (no error, no model state)
        self.assertIsInstance(draft, RecipeDraft)


if __name__ == "__main__":
    unittest.main()
