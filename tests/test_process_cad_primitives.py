import unittest

import numpy as np
import tcad_simulator as tcad


def make_model(shape=(10, 10, 16)):
    db = tcad.MaterialDatabase()
    model = tcad.ProcessModel(
        db,
        grid_shape=shape,
        voxel_size_nm=10.0,
        max_workers=1,
    )
    model.grid.fill(np.uint16(0))
    model._rebuild_height_map()
    return db, model


class PrimitiveFixtureTests(unittest.TestCase):
    def test_make_model_builds_empty_default_grid(self):
        db, model = make_model()
        self.addCleanup(model.parallel.shutdown)

        self.assertIsInstance(db, tcad.MaterialDatabase)
        self.assertEqual(model.grid.shape, (10, 10, 16))
        self.assertEqual(model.voxel_size_nm, 10.0)
        self.assertFalse(np.any(model.grid))
        self.assertFalse(np.any(model.height_map))
