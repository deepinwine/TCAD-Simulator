"""Atomic geometry operations on the existing ProcessModel storage."""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt

SEMICONDUCTORS = ('Silicon', 'Polysilicon', 'Germanium', 'Silicon Germanium')
OXIDIZABLE = ('Silicon', 'Polysilicon')


def preflight_candidate(step, model, supplied=None, *, mask_asset_service=None):
    """Validate detached configuration; never execute against final recipe geometry."""
    from recipe_planner.schema import normalize_params, parameter_errors
    params = dict(step.params)
    if supplied is not None:
        params.update(normalize_params(step.name, supplied))
    if any(isinstance(value, (bool, np.bool_)) and 'material' in key for key, value in params.items()):
        raise ValueError('Material must be a registered material, not a boolean')
    errors = parameter_errors(step.name, params, material_db=model.material_db)
    if errors:
        raise ValueError('; '.join(errors))
    step.params = params
    if not step.name.startswith('Structure '):
        return
    operation = getattr(step, 'operation', 'Pattern')
    if operation in ('Wafer', 'Deposit', 'Oxidation', 'Epitaxy'):
        count = layers(model, params['thickness_nm'], 'thickness_nm')
        if count > model.grid.shape[2]:
            raise ValueError('Structure thickness exceeds domain height')
    elif operation in ('Etch', 'Doping'):
        layers(model, params['depth_nm'], 'depth_nm')
    elif operation in ('Fill', 'Planarize'):
        count = layers(model, params['height_nm'], 'height_nm', zero=True)
        if count > model.grid.shape[2]:
            raise ValueError('Structure height exceeds domain height')
    if operation == 'Etch':
        angle = number(params['sidewall_angle_deg'], 'sidewall_angle_deg')
        if angle > 90:
            raise ValueError('sidewall_angle_deg must be in (0, 90]')
    elif operation == 'Doping':
        number(params['concentration_cm3'], 'concentration_cm3')
    elif step.name == 'Structure Pattern':
        if mask_asset_service is not None:
            step.bind_mask_asset_service(mask_asset_service)
        step.geometry_mask(model)


def semiconductor_id(model, value, *, oxidation=False):
    mid = material_id(model, value)
    allowed = OXIDIZABLE if oxidation else SEMICONDUCTORS
    if model.material_db.material(mid).name not in allowed:
        raise ValueError('Structure requires a supported semiconductor material')
    return mid


def coverage_mask(model, coverage):
    if coverage not in ('Full wafer', 'Open mask'):
        raise ValueError('Unknown Structure coverage')
    return np.ones(model.grid.shape[:2], dtype=bool) if coverage == 'Full wafer' else np.asarray(model.open_mask, dtype=bool)


def exposed_columns(grid, mid, opened):
    h = heights(grid)
    x, y = np.nonzero(opened & (h > 0))
    eligible = np.zeros(grid.shape[:2], dtype=bool)
    eligible[x, y] = grid[x, y, h[x, y]-1] == mid
    return h, eligible


def dope(model, params):
    """Assign one species; repeat assignments replace it, different species add to total."""
    mid = semiconductor_id(model, params['material'])
    species = params['species']
    if species not in ('B', 'P', 'As', 'Sb'):
        raise ValueError('Unknown Structure Doping species')
    concentration = number(params['concentration_cm3'], 'concentration_cm3')
    if concentration > 1e22:
        raise ValueError('concentration_cm3 must not exceed 1e22')
    n = layers(model, params['depth_nm'], 'depth_nm')
    h, eligible = exposed_columns(model.grid, mid, coverage_mask(model, params['coverage']))
    z = np.arange(model.grid.shape[2])[None, None, :]
    selected = eligible[..., None] & (z >= (h-n)[..., None]) & (z < h[..., None]) & (model.grid == mid)
    # Stop depth at the first non-selected material or void, rather than crossing a barrier.
    contiguous = np.zeros_like(selected)
    active = eligible.copy()
    for depth in range(min(n, model.grid.shape[2])):
        index = h - 1 - depth
        active &= index >= 0
        x, y = np.nonzero(active)
        active[x, y] &= model.grid[x, y, index[x, y]] == mid
        x, y = np.nonzero(active)
        contiguous[x, y, index[x, y]] = True
    selected &= contiguous
    if not selected.any():
        raise ValueError('Structure Doping: no exposed target material or effective opening')
    model._require_writable_spatial_volumes('Structure Doping')
    model._ensure_doping_field()
    field = model._ensure_dopant_species_field(species)
    delta = np.float32(concentration) - field[selected]
    model.doping[selected] = np.maximum(0, model.doping[selected] + delta)
    field[selected] = np.float32(concentration)
    model.last_implant_species = species
    return int(selected.sum())


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
    if operation == 'Doping':
        return dope(model, params)
    candidate = model.grid.copy()
    nz = candidate.shape[2]
    z = np.arange(nz)[None, None, :]
    if operation in ('Wafer', 'Deposit', 'Fill', 'Etch'):
        mid = material_id(model, params['material'])
    if operation in ('Oxidation', 'Epitaxy'):
        n = layers(model, params['thickness_nm'], 'thickness_nm')
        seed = semiconductor_id(model, params['material'] if operation == 'Oxidation' else params['seed_material'], oxidation=operation == 'Oxidation')
        mid = material_id(model, 'Silicon Dioxide') if operation == 'Oxidation' else semiconductor_id(model, params['material'])
        h, eligible = exposed_columns(candidate, seed, coverage_mask(model, params['coverage']))
        if not eligible.any():
            raise ValueError(f'Structure {operation}: no exposed target material or effective opening')
        consumed = max(1, int(math.floor(n / 2.27 + .5))) if operation == 'Oxidation' else 0
        if np.any(h[eligible] + n - consumed > nz):
            raise ValueError(f'Structure {operation} exceeds domain height')
        if consumed:
            # Every consumed voxel must belong to the selected substrate.
            region = eligible[..., None] & (z >= (h-consumed)[..., None]) & (z < h[..., None])
            if np.any(h[eligible] < consumed) or np.any(candidate[region] != seed):
                raise ValueError('Structure Oxidation exceeds selected substrate thickness')
        candidate[eligible[..., None] & (z >= (h-consumed)[..., None]) & (z < (h+n-consumed)[..., None])] = mid
    elif operation == 'Strip':
        candidate[candidate == material_id(model, 'Photoresist')] = 0
    elif operation == 'Wafer':
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
    changed = commit(model, candidate, f'Structure {operation}')
    if operation == 'Strip':
        model.open_mask = np.ones(candidate.shape[:2], dtype=bool)
    return changed
