"""Atomic geometry operations on the existing ProcessModel storage."""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt


def top(model):
    if model.active_side != 'top':
        raise ValueError('Structure CAD only supports the top (+Z) side')


def number(value, label, *, zero=False):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f'{label} requires a finite number')
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} requires a finite number') from None
    if not math.isfinite(value) or value < 0 or (not zero and value == 0):
        raise ValueError(f'{label} requires a finite positive number')
    return value


def layers(model, value, label, *, zero=False):
    value = number(value, label, zero=zero)
    scaled = value / model.voxel_size_nm
    if not math.isfinite(scaled):
        raise ValueError(f'{label} exceeds the representable grid range')
    count = int(math.floor(scaled + .5))
    if value > 0 and count == 0:
        raise ValueError(f'{label} is below half the grid spacing')
    return count


def material_id(model, material):
    if isinstance(material, (bool, np.bool_)):
        raise ValueError('Structure requires a known non-Void material')
    try:
        mid = model.material_db.id_for(material) if isinstance(material, str) else int(material) if isinstance(material, (int, np.integer)) else 0
        if mid <= 0:
            raise ValueError()
        model.material_db.material(mid)
        return mid
    except (ValueError, KeyError):
        raise ValueError('Structure requires a known non-Void material') from None


def heights(grid):
    occupied = grid != 0
    return np.where(occupied.any(axis=2), grid.shape[2] - occupied[..., ::-1].argmax(axis=2), 0)


def commit(model, candidate, operation):
    changed = candidate != model.grid
    if not changed.any():
        raise ValueError(f'{operation}: no geometry changed (no exposed target material or effective opening)')
    arrays = model._require_writable_spatial_volumes(operation)
    mask = model.open_mask.copy()
    dirty = set(int(v) for v in np.unique(model.grid[changed])) | set(int(v) for v in np.unique(candidate[changed]))
    model._clear_spatial_volume_mask((slice(None),)*3, changed, arrays=arrays)
    model.grid[...] = candidate
    model._rebuild_height_map(dirty)
    model.open_mask = mask
    return int(changed.sum())


def construct(model, operation, **params):
    top(model)
    candidate = model.grid.copy()
    nz = candidate.shape[2]
    z = np.arange(nz)[None, None, :]
    if operation in ('Wafer', 'Deposit', 'Fill', 'Etch'):
        mid = material_id(model, params['material'])
    if operation == 'Wafer':
        n = layers(model, params['thickness_nm'], 'thickness_nm')
        if n > nz:
            raise ValueError('Structure Wafer exceeds domain height')
        candidate.fill(0)
        candidate[:, :, :n] = mid
    elif operation == 'Deposit':
        n = layers(model, params['thickness_nm'], 'thickness_nm')
        if n > nz:
            raise ValueError('Structure Deposit exceeds domain height')
        coverage = params.get('coverage', 'Full wafer')
        if coverage not in ('Full wafer', 'Open mask'):
            raise ValueError('Unknown Structure Deposit coverage')
        opened = np.ones(candidate.shape[:2], dtype=bool) if coverage == 'Full wafer' else model.open_mask
        h = heights(candidate)
        if np.any(h[opened] + n > nz):
            raise ValueError('Structure Deposit exceeds domain height')
        candidate[opened[..., None] & (z >= h[..., None]) & (z < (h+n)[..., None])] = mid
    elif operation in ('Fill', 'Planarize'):
        n = layers(model, params['height_nm'], 'height_nm', zero=True)
        if n > nz:
            raise ValueError(f'Structure {operation} exceeds domain height')
        if operation == 'Fill':
            candidate[(candidate == 0) & (z < n)] = mid
        else:
            candidate[:, :, n:] = 0
    elif operation == 'Etch':
        n = layers(model, params['depth_nm'], 'depth_nm')
        angle = number(params['sidewall_angle_deg'], 'sidewall_angle_deg')
        if angle > 90:
            raise ValueError('sidewall_angle_deg must be in (0, 90]')
        opened = np.asarray(model.open_mask, dtype=bool)
        if not opened.any():
            raise ValueError('Structure Etch: no effective opening')
        h = heights(candidate)
        active = opened.copy()
        distance = None if opened.all() or angle == 90 else distance_transform_edt(opened) * model.voxel_size_nm
        for depth in range(n):
            index = h - 1 - depth
            active &= index >= 0
            if not active.any():
                break
            valid = active & (index >= 0)
            xs, ys = np.nonzero(valid)
            active[xs, ys] &= candidate[xs, ys, index[xs, ys]] == mid
            eligible = active.copy()
            if distance is not None:
                eligible &= distance > depth * model.voxel_size_nm / math.tan(math.radians(angle))
            xs, ys = np.nonzero(eligible)
            candidate[xs, ys, index[xs, ys]] = 0
    else:
        raise ValueError(f'Unknown structure operation {operation}')
    return commit(model, candidate, f'Structure {operation}')
