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
