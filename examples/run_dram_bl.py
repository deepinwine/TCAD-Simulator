#!/usr/bin/env python3
"""Replayable *ideal geometry* example: narrow W lines under wider active Si.

Replaces the direct-grid drawing example from 28fdfd2. This recipe constructs
the final stack using ordinary deposition/lithography/etch/fill steps. It does
NOT claim to simulate wafer-transfer integration, lateral epitaxy, sealed air
gaps, or a completed DRAM device. No simulator grid is written by this script.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('TCAD_SKIP_QT', '1')
os.environ.setdefault('MPLBACKEND', 'Agg')

import numpy as np
import tcad_simulator as tcad
from recipe_planner.schema import validate_import

PARAMS = {
    'domain_x_nm': 3600, 'domain_y_nm': 4000,
    'bitline_pitch_nm': 600, 'bitline_width_nm': 180,
    'bitline_thickness_nm': 120, 'num_bitlines': 5,
    'carrier_si_nm': 1000, 'bond_oxide_nm': 360, 'cap_oxide_nm': 180,
    'active_semiconductor_width_nm': 420, 'active_semiconductor_height_nm': 450,
}

# 每个采样密度对应一套掩膜。grid=64 为历史校准文件（字节不变）；grid=128 掩膜由
# generate_line_mask 按体素边界生成：五条线等宽、组居中、无边缘截断。
GRID_MASK_SUFFIX = {64: '', 128: '_128'}
GRID128_MASK_START = {'bitline': 17, 'active': 14}


def generate_line_mask(columns, *, start, pitch_nm, width_nm, count, voxel_nm):
    """Return a 1D boolean column profile: True = 掩膜不透明（线条受保护）。"""
    pitch = max(1, int(round(pitch_nm / voxel_nm)))
    width = max(1, int(round(width_nm / voxel_nm)))
    cols = np.zeros(int(columns), dtype=bool)
    for k in range(int(count)):
        i0 = int(start) + k * pitch
        if i0 + width > cols.size:
            raise ValueError(f'line {k+1} overruns mask domain ({i0}+{width} > {cols.size})')
        cols[i0:i0 + width] = True
    return cols


def write_mask_pgm(path, cols):
    body = '\n'.join(['P2', f'1 {len(cols)}', '255'] + ['0' if v else '255' for v in cols])
    Path(path).write_text(body + '\n', encoding='ascii')


def build_recipe(grid=64):
    # grid=64 使用校准掩膜；grid=128 使用生成的等宽掩膜。其它采样密度会改变
    # 边缘线宽，返回确定性但物理错误的结构，因此仍然拒绝。
    allowed = tuple(GRID_MASK_SUFFIX)
    if isinstance(grid, bool) or not isinstance(grid, int) or grid not in GRID_MASK_SUFFIX:
        raise ValueError(f'grid must be one of {allowed} for the DRAM masks')
    p = dict(PARAMS)
    voxel = p['domain_y_nm'] / grid
    shape = [int(math.ceil(p['domain_x_nm']/voxel)), grid, int(math.ceil(2800/voxel))]
    suffix = GRID_MASK_SUFFIX[grid]
    def step(name, label, **params):
        return {'name': name, 'instance_name': label, 'enabled': True, 'params': params}

    def pattern(width, name):
        mask_name = f'dram_bitline_mask{suffix}.pgm' if width == p['bitline_width_nm'] else f'dram_active_mask{suffix}.pgm'
        exposure = step('Mask Exposure', name, advanced_enable=1, mask_mode='Custom',
                        mask_file=f'examples/{mask_name}', mask_name=name, dose=80.0)
        return [step('Spin Resist', 'Patterning resist', thickness_nm=250.0), exposure,
                step('Resist Develop', 'Open spaces between lines', time=60.0, rate=300.0, contrast=3.0, threshold=10.0)]

    def etch(material, depth, stop):
        # Explicit rate in Angstrom/min and time in seconds, not depth-as-time.
        return step('Etch', f'Pattern {material}', material=material, chemistry='Dry',
                    time=60.0, rate_override=depth*20, selectivity=500.0,
                    sidewall=90.0, stop_on_material=stop)

    steps = [step('Initialize Wafer', 'Carrier silicon', thickness_nm=float(p['carrier_si_nm'])),
             step('Deposition', 'Bond oxide geometry', material='Silicon Dioxide', thickness=float(p['bond_oxide_nm']))]
    steps.append(step('Deposition', 'Tungsten bitline film', material='Tungsten', thickness=float(p['bitline_thickness_nm'])))
    steps.extend(pattern(p['bitline_width_nm'], 'Five narrow bitlines'))
    steps.extend([etch('Tungsten', p['bitline_thickness_nm'], 'Silicon Dioxide'),
                  step('Strip', 'Strip bitline resist', materials='Photoresist'),
                  step('Fill', 'Isolate bitlines with oxide', material='Silicon Dioxide', max_depth_nm=200.0),
                  step('Deposition', 'Oxide cap', material='Silicon Dioxide', thickness=float(p['cap_oxide_nm'])),
                  step('Deposition', 'Ideal active silicon film (not lateral epitaxy)', material='Silicon', thickness=float(p['active_semiconductor_height_nm']))])
    steps.extend(pattern(p['active_semiconductor_width_nm'], 'Five wider active silicon lines'))
    steps.extend([etch('Silicon', p['active_semiconductor_height_nm'], 'Silicon Dioxide'),
                  step('Strip', 'Strip active resist', materials='Photoresist')])
    return {'version': 1, 'name': 'DRAM Narrow BL + Wide Active Si (ideal geometry)',
            'description': '可回放最终叠层几何：5道窄W线与5道较宽Active Si；不模拟侧向外延、气隙、键合整合或完整DRAM器件。',
            'parameters': p, 'domain': {'grid_shape': shape, 'voxel_size_nm': voxel, 'threads': 1}, 'steps': steps}


def replay_recipe(recipe):
    from copy import deepcopy
    recipe = deepcopy(recipe)
    root = Path(__file__).resolve().parents[1]
    for blob in recipe.get('steps', []):
        mask_file = blob.get('params', {}).get('mask_file')
        if mask_file and not Path(mask_file).is_absolute():
            blob['params']['mask_file'] = str(root / mask_file)
    db = tcad.MaterialDatabase()
    validate_import(recipe, db)
    domain = recipe['domain']
    model = tcad.ProcessModel(db, grid_shape=tuple(domain['grid_shape']),
                              voxel_size_nm=domain['voxel_size_nm'], max_workers=1)
    snapshots = []
    try:
        for index, blob in enumerate(recipe['steps']):
            step = tcad._webui_deserialize_step(blob, db)
            if step is None:
                raise ValueError(f'Unknown step {index+1}')
            step.execute(model)
            snapshots.append(model.snapshot_state(compression='dense'))
        return model, recipe, snapshots
    except Exception:
        model.parallel.shutdown()
        raise


def build_dram_structure(grid=64):
    return replay_recipe(build_recipe(grid))


def _widths(mask, voxel):
    # Measure a physical cross section through the long lines, not input widths.
    occupied = mask[:, mask.shape[1]//2]
    edges = np.diff(np.r_[False, occupied, False].astype(int))
    return ((np.flatnonzero(edges == -1)-np.flatnonzero(edges == 1))*voxel).tolist()


def validate_structure(model, recipe):
    p, voxel = recipe['parameters'], model.voxel_size_nm
    metal = model.grid == model.material_db.id_for('Tungsten')
    si = model.grid == model.material_db.id_for('Silicon')
    # Locate active layer from measured metal height, excluding carrier silicon.
    z_metal = np.flatnonzero(metal.any(axis=(0, 1)))
    active = si.copy()
    cutoff = int(z_metal[-1]+1) if z_metal.size else active.shape[2]
    active[:, :, :cutoff] = False
    bitline_widths = _widths(metal.any(axis=2), voxel)
    active_widths = _widths(active.any(axis=2), voxel)
    active_heights = active.sum(axis=2)[active.any(axis=2)] * voxel
    metal_heights = metal.sum(axis=2)[metal.any(axis=2)] * voxel
    expected = p['num_bitlines']
    checks = [len(bitline_widths) == expected, len(active_widths) == expected,
              bool(active_heights.size), bool(metal_heights.size),
              not np.any(model.grid == model.material_db.id_for('Photoresist'))]
    for observed, target in ((bitline_widths, p['bitline_width_nm']), (active_widths, p['active_semiconductor_width_nm']),
                             (active_heights, p['active_semiconductor_height_nm']), (metal_heights, p['bitline_thickness_nm'])):
        checks.append(bool(len(observed)) and bool(np.all(np.abs(np.asarray(observed)-target) <= voxel*1.5)))
    checks.append(bool(bitline_widths and active_widths) and min(active_widths) > max(bitline_widths))
    return {'ok': bool(all(checks)), 'bitline_count': len(bitline_widths), 'active_count': len(active_widths),
            'bitline_widths_nm': bitline_widths, 'active_widths_nm': active_widths,
            'active_height_nm': float(np.median(active_heights)) if active_heights.size else 0,
            'bitline_height_nm': float(np.median(metal_heights)) if metal_heights.size else 0,
            'voxel_size_nm': voxel, 'grid_shape': list(model.grid.shape),
            'scope': 'ideal final-stack geometry; no air gap / lateral epitaxy / device physics'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grid', type=int, choices=tuple(GRID_MASK_SUFFIX), default=64,
                        help='Sampling density (64: calibrated masks; 128: generated equal-width masks)')
    parser.add_argument('--recipe', type=Path, help='Replay an exported full recipe JSON')
    parser.add_argument('--output', type=Path, help='Directory for recipe, measured report and final grid')
    parser.add_argument('--regenerate-masks', action='store_true',
                        help='Rewrite the generated grid=128 mask files from the design and exit')
    parser.add_argument('--no-viewer', action='store_true', help='Compatibility flag; this tool is headless')
    parser.add_argument('--validate-only', action='store_true', help='Execute and measure; never bypass execution')
    args = parser.parse_args()
    if args.regenerate_masks:
        voxel = PARAMS['domain_y_nm'] / 128
        columns = int(math.ceil(PARAMS['domain_x_nm'] / voxel))
        here = Path(__file__).resolve().parent
        for kind, width_nm in (('bitline', PARAMS['bitline_width_nm']),
                               ('active', PARAMS['active_semiconductor_width_nm'])):
            cols = generate_line_mask(columns, start=GRID128_MASK_START[kind],
                                      pitch_nm=PARAMS['bitline_pitch_nm'], width_nm=width_nm,
                                      count=PARAMS['num_bitlines'], voxel_nm=voxel)
            out = here / f'dram_{kind}_mask_128.pgm'
            write_mask_pgm(out, cols)
            print(f'wrote {out} ({int(cols.sum())} exposed-line columns of {columns})')
        return 0
    recipe = json.loads(args.recipe.read_text()) if args.recipe else build_recipe(args.grid)
    model, recipe, snapshots = replay_recipe(recipe)
    try:
        metrics = validate_structure(model, recipe)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output/'recipe.json').write_text(json.dumps(recipe, ensure_ascii=False, indent=2)+'\n')
            (args.output/'measurements.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2)+'\n')
            np.savez_compressed(args.output/'final_grid.npz', grid=model.grid, voxel_size_nm=model.voxel_size_nm)
        return 0 if metrics['ok'] else 1
    finally:
        model.parallel.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
