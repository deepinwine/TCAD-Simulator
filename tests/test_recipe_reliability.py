import os
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault('TCAD_SKIP_QT', '1')
os.environ.setdefault('MPLBACKEND', 'Agg')

import tcad_simulator as tcad
from recipe_planner import RecipePlanner, RecipeValidator
from recipe_planner.parser import PlannedStep, RecipeDraft


class RecipeReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.db = tcad.MaterialDatabase()
        self.validator = RecipeValidator()
        self.validator._accurate_support = {}

    def test_substrate_context_does_not_swallow_deposition(self):
        draft = RecipePlanner().parse('在硅衬底上沉积100nm氧化硅')
        self.assertEqual([s.type for s in draft.steps], ['Initialize Wafer', 'Deposition'])
        self.assertEqual(draft.steps[1].params['thickness'], 100)
        self.assertEqual(draft.steps[1].params['material'], 'Silicon Dioxide')

    def test_decimal_and_micro_symbol_survive(self):
        for unit in ('um', 'µm', 'μm'):
            with self.subTest(unit=unit):
                draft = RecipePlanner().parse('初始化硅衬底200nm，沉积0.1 '+unit+' SiO2')
                self.assertEqual(draft.steps[1].params['thickness'], 100)

    def test_multiple_actions_in_same_clause_preserved(self):
        draft = RecipePlanner().parse('填W并CMP')
        self.assertEqual([s.type for s in draft.steps], ['Initialize Wafer', 'Fill', 'CMP'])
        self.assertEqual(draft.steps[1].params['material'], 'Tungsten')

    def test_sequential_actions_keep_their_own_parameters(self):
        for text in ('刻蚀100nm硅再沉积50nm氧化硅',
                     '刻蚀100nm硅之后沉积50nm氧化硅',
                     'etch 100nm silicon followed by deposit 50nm SiO2'):
            with self.subTest(text=text):
                draft = RecipePlanner().parse(text)
                self.assertEqual([s.type for s in draft.steps], ['Initialize Wafer', 'Etch', 'Deposition'])
                self.assertEqual(draft.steps[1].params['depth_nm'], 100)
                self.assertEqual(draft.steps[2].params['thickness'], 50)
                self.assertFalse(self.validator.validate(draft)['ok'])

    def test_unsplittable_multiple_actions_are_rejected(self):
        draft = RecipePlanner().parse('刻蚀100nm硅沉积50nm氧化硅')
        self.assertFalse(self.validator.validate(draft)['ok'])
        self.assertTrue(draft.ambiguities)

    def test_overlapping_action_synonyms_resolve_to_longest_match(self):
        for text in ('选择生长50nm SiGe', 'selective epitaxy 50nm SiGe'):
            with self.subTest(text=text):
                draft = RecipePlanner().parse(text)
                self.assertEqual(
                    [step.type for step in draft.steps],
                    ['Initialize Wafer', 'Selective Epitaxy'],
                )
                self.assertEqual(draft.steps[1].params['thickness'], 50)
                self.assertFalse(draft.ambiguities)

    def test_assistant_placeholder_is_executable(self):
        from pathlib import Path
        import ast
        import re
        frontend = Path(__file__).parents[1] / 'frontend/src'
        source = (frontend / 'components/RecipeAssistant.tsx').read_text(encoding='utf-8')
        self.assertIn("placeholder={t('recipeAssistant.placeholder')}", source)
        catalogs = (frontend / 'i18n/catalogs.ts').read_text(encoding='utf-8')
        chinese = catalogs.split('export const zhCN = {', 1)[1].split('} as const', 1)[0]
        match = re.search(r"'recipeAssistant\.placeholder':\s*('(?:\\.|[^'\\])*')", chinese)
        self.assertIsNotNone(match, 'Chinese UI must retain a real executable recipe example')
        placeholder = ast.literal_eval(match.group(1))
        self.assertIn('\n例：', placeholder)
        text = placeholder.split('\n例：', 1)[1]
        draft = RecipePlanner().parse(text)
        result = self.validator.validate(draft)
        self.assertTrue(result['ok'], result)
        model = tcad.ProcessModel(self.db, grid_shape=(32, 32, 64), voxel_size_nm=10, max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        for step in draft.steps:
            tcad._webui_deserialize_step({'name': step.type, 'params': step.params}, self.db).execute(model)
        self.assertGreater(np.unique(model.grid[model.grid != 0]).size, 1)

    def test_empty_or_unknown_recipe_cannot_be_applied(self):
        for text in ('', '生成DRAM结构，窄埋入式Bitline和宽Active Si'):
            self.assertFalse(self.validator.validate(RecipePlanner().parse(text))['ok'])

    def test_unparsed_clause_is_not_silently_dropped(self):
        draft = RecipePlanner().parse('沉积100nm SiO2，然后执行神奇工艺')
        self.assertFalse(self.validator.validate(draft)['ok'])
        self.assertTrue(draft.ambiguities)

    def test_runtime_rejects_invalid_params_before_execution(self):
        for params in ({'time': 'not-a-number'}, {'time': float('nan')}, {'nonsense': 50}, {'material': 'NotARealMaterial'}):
            draft = RecipeDraft(steps=[PlannedStep('Initialize Wafer'), PlannedStep('Etch', params)])
            self.assertFalse(self.validator.validate(draft)['ok'], params)

    def test_depth_without_rate_is_not_treated_as_time(self):
        draft = RecipePlanner().parse('初始化硅衬底200nm，刻蚀50nm硅')
        result = self.validator.validate(draft)
        self.assertFalse(result['ok'])
        self.assertTrue(any('深度' in e or 'depth' in e for e in result['errors']))

    def test_deposition_alias_reaches_real_executor(self):
        for thickness in (5, 100, 500):
            step = tcad._webui_deserialize_step({'name': 'Deposition', 'params': {'thickness_nm': thickness}}, self.db)
            model = tcad.ProcessModel(self.db, grid_shape=(16, 16, 16), voxel_size_nm=20, max_workers=1)
            try:
                with patch.object(model, 'deposit_material') as deposit:
                    step.execute(model)
                self.assertEqual(deposit.call_args.args[1], thickness)
            finally:
                model.parallel.shutdown()

    def test_exposure_alias_and_hole_pattern(self):
        draft = RecipePlanner().parse('光刻100nm孔')
        exposure = next(s for s in draft.steps if s.type == 'Mask Exposure')
        self.assertEqual(exposure.params['critical_dimension'], 100)
        self.assertEqual(exposure.params['pattern'], 'Contacts')
        self.assertFalse(self.validator.validate(draft)['ok'])  # no resist/develop

    def test_llm_prompt_contains_actual_parameter_contract(self):
        from recipe_planner.llm_planner import build_llm_prompt
        prompt = build_llm_prompt('沉积')
        self.assertIn('critical_dimension', prompt)
        self.assertIn('thickness', prompt)
        self.assertIn('rate_override', prompt)

    def test_english_words_do_not_match_element_substrings(self):
        from recipe_planner import MaterialNormalizer
        self.assertIsNone(MaterialNormalizer().normalize('grow new layer')[0])

    def test_reports_actual_webui_execution_mode(self):
        result = self.validator.validate(RecipePlanner().parse('沉积100nm SiO2'))
        self.assertEqual(result['execution_backend'], 'voxel')
        self.assertTrue(any('Fast' in warning for warning in result['warnings']))

    def test_thickness_conflicting_alias_rejected(self):
        draft = RecipeDraft(steps=[PlannedStep('Initialize Wafer'), PlannedStep('Deposition', {'thickness': 10, 'thickness_nm': 20})])
        self.assertFalse(self.validator.validate(draft)['ok'])

    def test_import_preflight_rejects_bad_recipe_without_mutation(self):
        from recipe_planner.schema import validate_import
        for blob in ({'steps': []}, {'steps': [{'name': 'Made Up'}]},
                     {'steps': [{'name': 'Etch', 'params': {'time': 'oops'}}]}):
            with self.subTest(blob=blob), self.assertRaises(ValueError):
                validate_import(blob, self.db)

    def test_import_rejects_invalid_domain_and_mask(self):
        from recipe_planner.schema import validate_import
        for domain in ({'grid_shape': [16, 16, 0], 'voxel_size_nm': 10},
                       {'grid_shape': [16, 16, 16], 'voxel_size_nm': float('nan')}):
            with self.assertRaises(ValueError):
                validate_import({'domain': domain, 'steps': [{'name': 'Initialize Wafer'}]}, self.db)
        with self.assertRaises(ValueError):
            validate_import({'steps': [{'name': 'Mask Exposure', 'custom_mask': [['oops']]}]}, self.db)

    def test_soi_layers_cannot_exceed_total_thickness_or_mutate_model(self):
        from recipe_planner.schema import validate_import
        params = {
            'wafer_type': 'SOI',
            'thickness_nm': 200,
            'box_thickness_nm': 500,
            'device_thickness_nm': 500,
        }
        blob = {
            'domain': {'grid_shape': [16, 16, 64], 'voxel_size_nm': 10},
            'steps': [{'name': 'Initialize Wafer', 'params': params}],
        }
        with self.assertRaisesRegex(ValueError, 'SOI|BOX|厚度'):
            validate_import(blob, self.db)

        step = tcad._webui_deserialize_step(blob['steps'][0], self.db)
        model = tcad.ProcessModel(
            self.db, grid_shape=(16, 16, 64), voxel_size_nm=10, max_workers=1,
        )
        self.addCleanup(model.parallel.shutdown)
        before_grid = model.grid.copy()
        before_height = model.height_map.copy()
        before_thickness = model.substrate_thickness_nm
        with self.assertRaisesRegex(ValueError, 'SOI|BOX|厚度'):
            step.execute(model)
        np.testing.assert_array_equal(model.grid, before_grid)
        np.testing.assert_array_equal(model.height_map, before_height)
        self.assertEqual(model.substrate_thickness_nm, before_thickness)

    def test_prepare_import_preserves_legacy_domain_and_step_fallbacks(self):
        from recipe_planner.schema import prepare_import
        cases = (
            {
                'model': {'grid_shape': [12, 13, 40], 'voxel_size_nm': 7},
                'steps': [{'name': 'Initialize Wafer', 'params': {'thickness_nm': 200}}],
            },
            {
                'domain': {'threads': 1},
                'model': {'grid_shape': [12, 13, 40], 'voxel_size_nm': 7},
                'steps_full': [],
                'steps': [{'name': 'Initialize Wafer', 'params': {'thickness_nm': 200}}],
            },
        )
        for blob in cases:
            with self.subTest(blob=blob):
                candidate, rebuilt = prepare_import(
                    blob,
                    self.db,
                    grid_shape=(32, 32, 32),
                    voxel_size_nm=10,
                    threads=2,
                )
                self.addCleanup(candidate.parallel.shutdown)
                self.assertEqual(candidate.grid.shape, (12, 13, 40))
                self.assertEqual(candidate.voxel_size_nm, 7)
                self.assertEqual(len(rebuilt), 1)

    def test_custom_exposure_does_not_fall_back_when_mask_file_is_missing(self):
        step = tcad._webui_deserialize_step({
            'name': 'Mask Exposure',
            'params': {'mask_mode': 'Custom', 'mask_file': '/definitely/missing/mask.pgm'},
        }, self.db)
        model = tcad.ProcessModel(self.db, grid_shape=(8, 8, 8), voxel_size_nm=20, max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        before = model.open_mask.copy()
        with self.assertRaisesRegex(ValueError, 'mask|Mask'):
            step.execute(model)
        np.testing.assert_array_equal(model.open_mask, before)

    def test_strip_is_not_development(self):
        draft = RecipePlanner().parse('去胶')
        self.assertEqual(draft.steps[-1].type, 'Strip')
        self.assertEqual(draft.steps[-1].params['materials'], 'Photoresist')

    def test_real_worker_import_rejects_without_replacing_recipe(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            manager = tcad.WebUIServerManager(host='127.0.0.1', port=0, max_users=1,
                storage_root=Path(folder), enable_ai_agent=False,
                default_domain={'grid_shape': [16, 16, 80], 'voxel_size_nm': 10, 'threads': 1})
            manager.start()
            try:
                session, _ = manager.create_session()
                draft = RecipePlanner().parse('在硅衬底上沉积100nm氧化硅')
                recipe = {'steps': [{'name': s.type, 'params': s.params} for s in draft.steps]}
                self.assertTrue(session.rpc('recipe_import', {'recipe': recipe})['ok'])
                self.assertTrue(session.rpc('run_all', {}, timeout_s=60)['ok'])
                before = session.rpc('get_recipe', {})['result']
                failed = session.rpc('recipe_import', {'recipe': {'steps': [{'name': 'Made Up'}]}})
                self.assertFalse(failed['ok'])
                self.assertEqual(session.rpc('get_recipe', {})['result'], before)

                baseline = session.rpc('init', {})['result']
                malformed = {
                    'name': 'After',
                    'domain': {'grid_shape': [8, 8, 20], 'voxel_size_nm': 5.0},
                    'steps': [{'name': 'Mask Exposure', 'mask_file': {'not': 'a path'}}],
                }
                for command in ('recipe_import', 'load_recipe_ephemeral'):
                    with self.subTest(command=command):
                        rejected = session.rpc(command, {'recipe': malformed})
                        self.assertFalse(rejected['ok'])
                        after = session.rpc('init', {})['result']
                        self.assertEqual(after['current_recipe'], baseline['current_recipe'])
                        self.assertEqual(after['model'], baseline['model'])
                        self.assertEqual(after['recipe'], baseline['recipe'])
                malformed['steps'] = [{'name': 'Mask Exposure', 'params': {
                    'mask_mode': 'Custom', 'mask_file': '/definitely/missing/specific-chip-mask.pgm'}}]
                for command in ('recipe_import', 'load_recipe_ephemeral'):
                    with self.subTest(command=command, missing_mask=True):
                        rejected = session.rpc(command, {'recipe': malformed})
                        self.assertFalse(rejected['ok'])
                        self.assertIn('Mask file not found', rejected['error'])
                        after = session.rpc('init', {})['result']
                        self.assertEqual(after['current_recipe'], baseline['current_recipe'])
                        self.assertEqual(after['model'], baseline['model'])
                        self.assertEqual(after['recipe'], baseline['recipe'])
            finally:
                manager.stop()

    def test_oversize_substrate_rejected_before_reset(self):
        model = tcad.ProcessModel(self.db, grid_shape=(16, 16, 16), voxel_size_nm=20, max_workers=1)
        try:
            model.grid[0, 0, 0] = 2
            step = tcad.InitializeWaferStep(self.db)
            step.params['thickness_nm'] = 1000
            with self.assertRaisesRegex(ValueError, 'domain|域'):
                step.execute(model)
            self.assertEqual(model.grid[0, 0, 0], 2)
        finally:
            model.parallel.shutdown()
