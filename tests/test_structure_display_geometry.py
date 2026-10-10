"""Exact, read-only remaining entities for local step visibility."""
import struct
import unittest
from collections import Counter
from unittest.mock import patch

import numpy as np
import tcad_simulator as tcad


def decode_mesh(data):
    magic, version, flags, vertices, indices = struct.unpack('<8sIIII', data[:24])
    assert (magic, version, flags) == (b'TCADGEOM', 1, 7)
    points = np.frombuffer(data, '<f4', vertices * 3, 24).reshape(-1, 3)
    faces = np.frombuffer(data, '<u4', indices, 24 + vertices * 24).reshape(-1, 3)
    return points[faces].astype(float)


class StructureDisplayGeometryTests(unittest.TestCase):
    def setUp(self):
        self.db = tcad.MaterialDatabase()
        self.model = tcad.ProcessModel(self.db, grid_shape=(4, 3, 12), voxel_size_nm=5, max_workers=1)
        self.addCleanup(self.model.parallel.shutdown)
        self.steps = []

    def step(self, name, **params):
        step = tcad.PROCESS_STEP_FACTORIES[name](self.db)
        step.params.update(params)
        step.execute(self.model)
        self.steps.append(step)
        return step

    def cache(self, **kwargs):
        from structure_cad.display_geometry import DisplayGeometry
        return DisplayGeometry(**kwargs)

    def fixture(self):
        self.step('Structure Wafer', thickness_nm=10)
        a = self.step('Structure Deposit', material='Silicon Dioxide', thickness_nm=10)
        b = self.step('Structure Deposit', material='Silicon Dioxide', thickness_nm=10)
        self.step('Structure Etch', material='Silicon Dioxide', depth_nm=5)
        return a, b

    def test_same_material_groups_closed_exact_and_shared_boundary(self):
        a, b = self.fixture()
        before = self.model.snapshot_state('dense')
        before_owners = self.model.display_provenance.owners.copy()
        cache = self.cache()
        manifest = cache.manifest(self.model, 7, self.steps)
        self.assertTrue(manifest['available'])
        self.assertEqual(len(manifest['groups']), 3)
        source = self.model.display_provenance
        all_tri = {}
        for group in manifest['groups']:
            tri = decode_mesh(cache.mesh(self.model, 7, group['owner_id'], group['mat_id']))
            edges = Counter(tuple(sorted((tuple(x), tuple(y)))) for t in tri
                            for x, y in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
            self.assertTrue(all(count == 2 for count in edges.values()))
            volume = np.einsum('ij,ij->i', tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
            self.assertAlmostEqual(volume, group['voxel_count'] * .005 ** 3, places=12)
            np.testing.assert_allclose(tri.min((0, 1))[:2], [-.0025, -.0025])
            np.testing.assert_allclose(tri.max((0, 1))[:2], [.0175, .0125])
            all_tri[group['owner_id']] = tri
        ta, tb = (all_tri[source.owner_for(s.step_id)] for s in (a, b))
        shared_a = ta[np.all(np.isclose(ta[:, :, 2], .0175), axis=1)]
        shared_b = tb[np.all(np.isclose(tb[:, :, 2], .0175), axis=1)]
        self.assertEqual(len(shared_a), 24)
        self.assertEqual({tuple(sorted(map(tuple, t))) for t in shared_a},
                         {tuple(sorted(map(tuple, t))) for t in shared_b})
        self.assertLessEqual(tb[:, :, 2].max(), .022500001)
        np.testing.assert_array_equal(before['grid'], self.model.grid)
        np.testing.assert_array_equal(before_owners, source.owners)

    def test_revision_cache_does_not_extract_again_and_rejects_old_requests(self):
        self.fixture()
        cache = self.cache()
        with patch.object(tcad, 'marching_cubes', wraps=tcad.marching_cubes) as extraction:
            first = cache.manifest(self.model, 3, self.steps)
            calls = extraction.call_count
            self.assertEqual(calls, 3)
            self.assertEqual(first, cache.manifest(self.model, 3, self.steps))
            g = first['groups'][0]
            cache.mesh(self.model, 3, g['owner_id'], g['mat_id'])
            self.assertEqual(calls, extraction.call_count)
            with self.assertRaisesRegex(ValueError, 'revision'):
                cache.mesh(self.model, 4, g['owner_id'], g['mat_id'], revision=3)

    def test_unknown_owner_visible_and_missing_steps_not_guessed(self):
        self.model.build_substrate('Silicon', 10, emit_log=False)
        self.step('Structure Deposit', thickness_nm=5)
        manifest = self.cache().manifest(self.model, 1, self.steps)
        unknown = next(g for g in manifest['groups'] if g['owner_id'] == 0)
        self.assertIsNone(unknown['step_id'])
        self.assertGreater(unknown['voxel_count'], 0)
        self.assertIn('unknown_provenance', manifest['unavailable_reasons'])

    def test_slices_three_axes_match_formal_directions_and_holes(self):
        self.fixture()
        cache = self.cache()
        for axis, index in (('X', 1), ('Y', 2), ('Z', 5)):
            result = cache.slice(self.model, 9, axis, index, revision=9)
            import base64
            mats = np.frombuffer(base64.b64decode(result['material']['data_b64']), '<u2').reshape(result['shape'])
            owners = np.frombuffer(base64.b64decode(result['owner']['data_b64']), '<u4').reshape(result['shape'])
            expected = self.model.get_cross_section(axis, index)
            if axis == 'Z':
                expected = expected.T
            np.testing.assert_array_equal(expected, mats)
            self.assertFalse(owners[mats == 0].any())
        with self.assertRaisesRegex(ValueError, 'index'):
            cache.slice(self.model, 9, 'X', 4, revision=9)

    def test_empty_and_budget_failures_are_explicit_not_partial(self):
        self.model.grid.fill(0)
        self.assertEqual(self.cache().manifest(self.model, 0, [])['groups'], [])
        self.fixture()
        for limits in ({'max_groups': 1}, {'max_triangles': 1}, {'max_cache_bytes': 1}, {'max_scan_voxels': 1}):
            with self.subTest(limits=limits):
                cache = self.cache(**limits)
                manifest = cache.manifest(self.model, 2, self.steps)
                self.assertFalse(manifest['available'])
                self.assertEqual(manifest['groups'], [])
                self.assertIn('display_budget_exceeded', manifest['unavailable_reasons'])
                with self.assertRaises(ValueError):
                    cache.mesh(self.model, 2, 1, 1)

    def test_strict_extractor_rejects_before_allocating_triangles(self):
        mask = np.ones((4, 3, 2), bool)
        with self.assertRaisesRegex(ValueError, 'triangle budget'):
            tcad.marching_cubes(mask, .5, strict_voxels=True, triangle_limit=1)
        verts, faces = tcad.marching_cubes(mask, .5, strict_voxels=True)
        np.testing.assert_array_equal(verts.min(0), [-.5, -.5, -.5])
        np.testing.assert_array_equal(verts.max(0), [3.5, 2.5, 1.5])

    def test_group_budget_rejects_before_python_group_materialization(self):
        self.fixture()
        original_unique = np.unique

        class NumericOnlyGroups(np.ndarray):
            def __iter__(self):
                raise AssertionError('Over-budget groups must not be materialized')

        def numeric_groups(*args, **kwargs):
            unique, counts = original_unique(*args, **kwargs)
            return unique.view(NumericOnlyGroups), counts

        cache = self.cache(max_groups=1)
        with patch.object(np, 'unique', side_effect=numeric_groups), \
             patch.object(tcad, 'marching_cubes', side_effect=AssertionError('Unexpected extraction')):
            manifest = cache.manifest(self.model, 2, self.steps)
        self.assertFalse(manifest['available'])
        self.assertEqual(manifest['groups'], [])
        self.assertIn('display_budget_exceeded', manifest['unavailable_reasons'])
        self.assertNotIn('materialized', manifest['error'])

    def test_patterned_etch_hole_is_not_reintroduced_in_mesh_or_slice(self):
        from geometry_scene.bridge import _voxelize_mesh
        self.model = tcad.ProcessModel(self.db, grid_shape=(13, 13, 12), voxel_size_nm=5, max_workers=1)
        self.addCleanup(self.model.parallel.shutdown)
        self.step('Structure Wafer', thickness_nm=10)
        self.step('Structure Deposit', material='Silicon Dioxide', thickness_nm=10)
        self.step('Structure Deposit', material='Silicon Dioxide', thickness_nm=10)
        self.step('Structure Pattern', pattern='Circular', critical_dimension=5, pitch=20)
        self.step('Structure Etch', material='Silicon Dioxide', depth_nm=20)
        self.assertEqual(self.model.grid[6, 6, 2], 0)
        cache = self.cache()
        manifest = cache.manifest(self.model, 10, self.steps)
        centers = [np.arange(n) * .005 for n in self.model.grid.shape]
        for group in manifest['groups']:
            tri = decode_mesh(cache.mesh(self.model, 10, group['owner_id'], group['mat_id']))
            occupancy = _voxelize_mesh(tri, *centers)
            expected = (self.model.grid == group['mat_id']) & (self.model.display_provenance.owners == group['owner_id'])
            np.testing.assert_array_equal(expected, occupancy)
        import base64
        result = cache.slice(self.model, 10, 'Z', 2, revision=10)
        material = np.frombuffer(base64.b64decode(result['material']['data_b64']), '<u2').reshape(result['shape'])
        owner = np.frombuffer(base64.b64decode(result['owner']['data_b64']), '<u4').reshape(result['shape'])
        self.assertEqual((material[6, 6], owner[6, 6]), (0, 0))

    def test_default_contour_extraction_does_not_use_strict_mode(self):
        field = np.pad(np.ones((2, 3, 4), bool), 1).astype(float)
        with patch.object(tcad, '_strict_voxel_boundary_mesh', side_effect=AssertionError('Unexpected strict mode')):
            verts, faces = tcad.marching_cubes(field, .5)
            self.assertGreater(len(verts), 0)
            self.assertGreater(len(faces), 0)

    def test_slice_budget_rejected_without_preparing_mesh_or_mutating_model(self):
        self.fixture()
        before = self.model.grid.copy()
        cache = self.cache(max_slice_bytes=1)
        with patch.object(tcad, 'marching_cubes', side_effect=AssertionError('Unexpected extraction')):
            with self.assertRaisesRegex(ValueError, 'slice budget'):
                cache.slice(self.model, 1, 'X', 0, revision=1)
        np.testing.assert_array_equal(before, self.model.grid)
