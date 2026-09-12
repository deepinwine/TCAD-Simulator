import os
import unittest
from unittest.mock import patch

os.environ.setdefault('TCAD_SKIP_QT', '1')
os.environ.setdefault('MPLBACKEND', 'Agg')
import numpy as np
import tcad_simulator as tcad
from process_backend.hybrid import HybridBackend, FAST, ACCURATE
from process_backend.base import ProcessBackendError
from geometry_scene.scene import GeometryScene, MaterialMesh
from geometry_scene.bridge import scene_to_viennaps_layers, scene_to_voxel_grid
from tests.test_m18_review_fixes import _box


class BackendReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.backend = HybridBackend(grid=32)
        self.addCleanup(self.backend.shutdown)

    def test_height_rebuild_matches_native_and_invalidates_caches(self):
        model = self.backend._fast._model
        model.grid[:] = 0
        model.grid[1:3, 1:3, :10] = 1
        model._rebuild_height_map()
        expected = model.height_map.copy()
        self.backend._rebuild_voxel_derived(model)
        np.testing.assert_array_equal(model.height_map, expected)

    def test_extraction_failure_rolls_back_and_never_reexecutes(self):
        initial = self.backend._fast.grid().copy()
        step = tcad.InitializeWaferStep(self.backend._fast.database)
        with patch.object(step, 'execute', wraps=step.execute) as execute:
            with patch('geometry_scene.bridge.uniform_voxel_layers_to_scene', side_effect=ValueError('analytic extract')):
                with patch.object(self.backend._fast, 'material_surfaces', side_effect=ValueError('mesh extract')):
                    with self.assertRaises(ProcessBackendError):
                        self.backend.execute_step(step)
            self.assertEqual(execute.call_count, 1)
        np.testing.assert_array_equal(self.backend._fast.grid(), initial)

    def test_partial_execution_failure_restores_model(self):
        initial = self.backend._fast.grid().copy()
        class BadStep:
            name = 'Deposition'
            def execute(self, model):
                model.grid[:] = 2
                raise ValueError('failed after mutation')
        with self.assertRaises(ProcessBackendError):
            self.backend.execute_step(BadStep())
        np.testing.assert_array_equal(self.backend._fast.grid(), initial)

    def test_engine_constructor_failure_stays_fast(self):
        with patch.object(self.backend, '_get_accurate', side_effect=RuntimeError('missing engine')):
            self.assertEqual(self.backend._switch_backend(ACCURATE), FAST)

    def test_unknown_snapshot_version_rejected_atomically(self):
        snapshot = self.backend.snapshot()
        snapshot['version'] = 999
        with self.assertRaises(ProcessBackendError):
            self.backend.restore(snapshot)
        self.assertEqual(self.backend._active_name, FAST)

    def test_disconnected_merged_material_is_rejected(self):
        scene = GeometryScene()
        scene.add(1, _box(0, 0, 0, 100, 100, 20))
        scene.add(1, _box(0, 0, 40, 100, 100, 60))
        with self.assertRaises(ValueError):
            scene_to_viennaps_layers(scene)

    def test_patterned_layer_cannot_be_flattened(self):
        scene = GeometryScene()
        scene.add(1, _box(0, 0, 0, 100, 100, 20))
        scene.add(2, _box(20, 20, 20, 60, 60, 40))
        with self.assertRaises(ValueError):
            scene_to_viennaps_layers(scene)

    def test_box_voxelization_has_no_diagonal_holes(self):
        scene = GeometryScene()
        scene.add(1, _box(0, 0, 0, 100, 100, 100))
        grid = scene_to_voxel_grid(scene, (10, 10, 10), 10)
        self.assertTrue(np.all(grid == 1), np.count_nonzero(grid == 0))

    def test_planar_import_preserves_absolute_coordinates(self):
        from process_backend.viennaps_backend import engine_available, ViennaPSBackend
        if not engine_available():
            self.skipTest('ViennaPS not installed')
        backend = ViennaPSBackend(grid_nm=10)
        self.addCleanup(backend.shutdown)
        scene = GeometryScene()
        scene.add(1, _box(100, 100, 50, 300, 300, 150))
        backend.load_geometry_scene(scene)
        surfaces = backend.material_surfaces(20000)
        points = np.concatenate([tri.reshape(-1, 3) * 1000 for _, tri in surfaces])
        np.testing.assert_allclose(points.min(axis=0), [100, 100, 50], atol=11)
        np.testing.assert_allclose(points.max(axis=0), [300, 300, 150], atol=11)

    def test_imported_upper_material_does_not_enclose_substrate(self):
        from process_backend.viennaps_backend import engine_available, ViennaPSBackend
        if not engine_available():
            self.skipTest('ViennaPS not installed')
        backend = ViennaPSBackend(grid_nm=10)
        self.addCleanup(backend.shutdown)
        scene = GeometryScene()
        scene.add(1, _box(0, 0, 0, 200, 200, 100))
        scene.add(2, _box(0, 0, 100, 200, 200, 150))
        backend.load_geometry_scene(scene)
        surfaces = dict(backend.material_surfaces(20000))
        self.assertIn(2, surfaces)
        self.assertGreaterEqual(surfaces[2][:, :, 2].min() * 1000, 89)
