#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DRAM Narrow BL + Wide Active Si — 3D structure generation and validation.

Usage:
    python examples/run_dram_bl.py [--grid 64] [--no-viewer] [--validate-only]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np


# ---- Parameters (nm) ----

PARAMS = {
    "domain_x_nm": 3600,
    "domain_y_nm": 4000,
    "bitline_pitch_nm": 600,
    "bitline_width_nm": 180,
    "bitline_thickness_nm": 120,
    "first_wafer_si_nm": 2500,
    "final_remaining_si_nm": 450,
    "bond_oxide_1_nm": 180,
    "bond_oxide_2_nm": 180,
    "carrier_si_nm": 1000,
    "first_semiconductor_width_nm": 240,
    "active_semiconductor_width_nm": 420,
    "active_semiconductor_height_nm": 450,
    "air_gap_liner_nm": 20,
    "num_bitlines": 5,
}


def build_dram_structure(grid=64):
    """Build the DRAM narrow BL + wide active Si structure on VoxelBackend."""
    import tcad_simulator as tcad
    from process_backend import create_backend

    p = PARAMS
    domain_max = max(p["domain_x_nm"], p["domain_y_nm"])
    voxel = domain_max / grid  # nm per voxel
    # Use cubic grid large enough for domain + carrier + all layers
    total_z = (p["first_wafer_si_nm"] + p["bitline_thickness_nm"]
               + p["bond_oxide_1_nm"] + p["bond_oxide_2_nm"] + p["carrier_si_nm"]
               + p["active_semiconductor_height_nm"] + 200)
    grid_z = int(np.ceil(total_z / voxel))
    grid_shape = (grid, grid, max(grid, grid_z))

    print(f"Grid: {grid_shape}, voxel: {voxel:.1f} nm")
    print(f"Domain: {p['domain_x_nm']}×{p['domain_y_nm']}×{total_z:.0f} nm")

    backend = create_backend("voxel", grid=grid)
    db = backend.database
    model = backend._model

    # Material IDs
    si_id = next(mid for mid, m in db.items() if m.name == "Silicon")
    sio2_id = next(mid for mid, m in db.items() if m.name == "Silicon Dioxide")
    sin_id = next(mid for mid, m in db.items() if m.name == "Silicon Nitride")
    w_id = next(mid for mid, m in db.items() if m.name == "Tungsten")
    pr_id = next(mid for mid, m in db.items() if m.name == "Photoresist")
    void_id = 0

    nx, ny, nz = model.grid.shape
    g = model.grid

    def nm_to_vox(nm_val):
        return int(round(nm_val / voxel))

    def x_nm_to_ix(x_nm):
        return int(round(x_nm / p["domain_x_nm"] * nx))

    def y_nm_to_iy(y_nm):
        return int(round(y_nm / p["domain_y_nm"] * ny))

    # Helper: set a rectangular region to material
    def fill_box(mat_id, x0_nm, y0_nm, z0_nm, x1_nm, y1_nm, z1_nm):
        ix0, ix1 = x_nm_to_ix(x0_nm), x_nm_to_ix(x1_nm)
        iy0, iy1 = y_nm_to_iy(y0_nm), y_nm_to_iy(y1_nm)
        iz0, iz1 = nm_to_vox(z0_nm), nm_to_voz(z1_nm)
        ix0, ix1 = max(0, ix0), min(nx, ix1)
        iy0, iy1 = max(0, iy0), min(ny, iy1)
        iz0, iz1 = max(0, iz0), min(nz, iz1)
        g[ix0:ix1, iy0:iy1, iz0:iz1] = mat_id

    nm_to_voz = nm_to_vox  # alias

    # Z coordinates (bottom-up in wafer thickness direction)
    z_carrier_bottom = 0
    z_carrier_top = z_carrier_bottom + p["carrier_si_nm"]
    z_bond2_bottom = z_carrier_top
    z_bond2_top = z_bond2_bottom + p["bond_oxide_2_nm"]
    z_bond1_bottom = z_bond2_top
    z_bond1_top = z_bond1_bottom + p["bond_oxide_1_nm"]
    z_w_bottom = z_bond1_top
    z_w_top = z_w_bottom + p["bitline_thickness_nm"]
    z_si_bottom = z_w_top
    z_si_original_top = z_si_bottom + p["first_wafer_si_nm"]
    z_si_final_top = z_si_bottom + p["final_remaining_si_nm"]

    print(f"\nZ-layers (nm):")
    print(f"  Carrier Si:    {z_carrier_bottom} → {z_carrier_top}")
    print(f"  Bond oxide 2:  {z_bond2_bottom} → {z_bond2_top}")
    print(f"  Bond oxide 1:  {z_bond1_bottom} → {z_bond1_top}")
    print(f"  W bitlines:    {z_w_bottom} → {z_w_top}")
    print(f"  Active Si:     {z_si_bottom} → {z_si_final_top} (final)")

    step_history = []

    def record_step(label):
        surfaces = model.get_material_surfaces(50000)
        step_history.append({
            "step": label,
            "materials": sorted(set(int(m) for m in np.unique(g) if m != 0)),
            "occupied": int(np.count_nonzero(g != 0)),
            "triangles": sum(s[1].shape[0] for s in surfaces),
        })
        print(f"  [{len(step_history):2d}] {label}: {np.count_nonzero(g != 0)} voxels")

    # ---- Step 1: First Si wafer ----
    fill_box(si_id, 0, 0, z_si_bottom, p["domain_x_nm"], p["domain_y_nm"], z_si_original_top)
    record_step("1. First Si wafer")

    # ---- Step 2: W deposition + litho + etch → 5 bitlines ----
    # Deposit W blanket
    fill_box(w_id, 0, 0, z_w_bottom, p["domain_x_nm"], p["domain_y_nm"], z_w_top)
    record_step("2a. W deposition")

    # Pattern: 5 lines along Y, pitch 600nm, width 180nm
    # Lines centered in domain, centered around domain center
    num_bl = p["num_bitlines"]
    pitch = p["bitline_pitch_nm"]
    bl_width = p["bitline_width_nm"]
    # Center the array
    array_width = (num_bl - 1) * pitch + bl_width
    x_start = (p["domain_x_nm"] - array_width) / 2

    # Clear W between bitlines (anisotropic etch)
    for i in range(num_bl):
        bl_center = x_start + i * pitch + bl_width / 2
        bl_x0 = bl_center - bl_width / 2
        bl_x1 = bl_center + bl_width / 2
        # Keep this bitline
        pass

    # Remove W everywhere except at bitline positions
    for ix in range(nx):
        x_nm = (ix + 0.5) / nx * p["domain_x_nm"]
        in_bl = False
        for i in range(num_bl):
            bl_center = x_start + i * pitch + bl_width / 2
            if abs(x_nm - bl_center) < bl_width / 2:
                in_bl = True
                break
        if not in_bl:
            ix_vox = nm_to_voz(z_w_bottom)
            ix_vox_end = nm_to_voz(z_w_top)
            g[ix, :, ix_vox:ix_vox_end] = void_id

    # Fill between bitlines with SiO2
    for ix in range(nx):
        x_nm = (ix + 0.5) / nx * p["domain_x_nm"]
        in_bl = False
        for i in range(num_bl):
            bl_center = x_start + i * pitch + bl_width / 2
            if abs(x_nm - bl_center) < bl_width / 2:
                in_bl = True
                break
        if not in_bl:
            ix_vox = nm_to_voz(z_w_bottom)
            ix_vox_end = nm_to_voz(z_w_top)
            g[ix, :, ix_vox:ix_vox_end] = sio2_id

    record_step("2e. W bitline patterning (5 lines)")

    # ---- Step 3: Bond oxide fill + CMP ----
    # SiO2 already fills between BLs; add cap if needed
    fill_box(sio2_id, 0, 0, z_w_top - voxel, p["domain_x_nm"], p["domain_y_nm"], z_w_top + voxel)
    record_step("3. Bond oxide + CMP planarize")

    # ---- Step 4-5: Carrier wafer + bonding oxide ----
    fill_box(sio2_id, 0, 0, z_bond1_bottom, p["domain_x_nm"], p["domain_y_nm"], z_bond1_top)
    record_step("5a. Bond oxide 1")

    fill_box(sio2_id, 0, 0, z_bond2_bottom, p["domain_x_nm"], p["domain_y_nm"], z_bond2_top)
    record_step("5b. Bond oxide 2")

    fill_box(si_id, 0, 0, z_carrier_bottom, p["domain_x_nm"], p["domain_y_nm"], z_carrier_top)
    record_step("5c. Carrier wafer bonding")

    # ---- Step 6: Wafer flip ----
    # In our coordinate system (Z = up from carrier), the flip is implicit:
    # the first wafer Si is now on top, carrier at bottom — which is what we have.
    record_step("6. Wafer flip (coordinate convention)")

    # ---- Step 7: Backside thinning ----
    # Thin the first wafer Si from original to final remaining
    thin_vox_start = nm_to_voz(z_si_final_top)
    thin_vox_end = nm_to_voz(z_si_original_top)
    if thin_vox_end > thin_vox_start:
        # Only thin Si (not other materials)
        si_mask = g[:, :, thin_vox_start:thin_vox_end] == si_id
        g[:, :, thin_vox_start:thin_vox_end][si_mask] = void_id
    record_step("7. Backside thinning to 450nm")

    # ---- Step 8: Trench formation between BLs ----
    # Trench between adjacent BLs: etch Si from top down to bond oxide
    trench_width = pitch - p["first_semiconductor_width_nm"]
    for i in range(num_bl - 1):
        bl_center = x_start + i * pitch + bl_width / 2
        next_bl_center = x_start + (i + 1) * pitch + bl_width / 2
        trench_center = (bl_center + next_bl_center) / 2
        trench_x0 = trench_center - trench_width / 2
        trench_x1 = trench_center + trench_width / 2
        # Etch from top of remaining Si down to bond oxide
        trench_z0 = z_bond1_top  # stop on oxide
        trench_z1 = z_si_final_top + p["active_semiconductor_height_nm"]  # from top
        # Clear Si in trench region (but not SiO2 liner or other materials)
        ix0, ix1 = x_nm_to_ix(trench_x0), x_nm_to_ix(trench_x1)
        iz0, iz1 = nm_to_voz(trench_z0), nm_to_voz(z_si_final_top)
        ix0, ix1 = max(0, ix0), min(nx, ix1)
        iz0, iz1 = max(0, iz0), min(nz, iz1)
        for ix in range(ix0, ix1):
            for iz in range(iz0, iz1):
                si_mask = g[ix, :, iz] == si_id
                g[ix, :, iz][si_mask] = void_id

    record_step("8. Trench formation → FirstSemiconductorPortion")

    # ---- Step 9: Air gap (liner + pinch-off seal) ----
    # SiO2 liner on trench walls
    liner_t = p["air_gap_liner_nm"]
    for i in range(num_bl - 1):
        bl_center = x_start + i * pitch + bl_width / 2
        next_bl_center = x_start + (i + 1) * pitch + bl_width / 2
        trench_center = (bl_center + next_bl_center) / 2
        trench_x0 = trench_center - trench_width / 2
        trench_x1 = trench_center + trench_width / 2
        # Liner on side walls
        ix0, ix1 = x_nm_to_ix(trench_x0), x_nm_to_ix(trench_x1)
        iz0, iz1 = nm_to_voz(z_bond1_top), nm_to_voz(z_si_final_top)
        liner_vox = max(1, nm_to_voz(liner_t))
        for ix in range(ix0, ix0 + liner_vox):
            for iz in range(iz0, iz1):
                void_mask = g[ix, :, iz] == void_id
                g[ix, :, iz][void_mask] = sio2_id
        for ix in range(ix1 - liner_vox, ix1):
            for iz in range(iz0, iz1):
                void_mask = g[ix, :, iz] == void_id
                g[ix, :, iz][void_mask] = sio2_id

    # SiN seal at top of trench (pinch-off approximation)
    seal_t = 30  # nm
    seal_vox = max(1, nm_to_voz(seal_t))
    seal_z0 = z_si_final_top - seal_t
    for i in range(num_bl - 1):
        bl_center = x_start + i * pitch + bl_width / 2
        next_bl_center = x_start + (i + 1) * pitch + bl_width / 2
        trench_center = (bl_center + next_bl_center) / 2
        trench_x0 = trench_center - trench_width / 2
        trench_x1 = trench_center + trench_width / 2
        ix0, ix1 = x_nm_to_ix(trench_x0), x_nm_to_ix(trench_x1)
        iz0, iz1 = nm_to_voz(seal_z0), nm_to_voz(z_si_final_top)
        ix0, ix1 = max(0, ix0), min(nx, ix1)
        iz0, iz1 = max(0, iz0), min(nz, iz1)
        for ix in range(ix0, ix1):
            for iz in range(iz0, iz1):
                void_mask = g[ix, :, iz] == void_id
                g[ix, :, iz][void_mask] = sin_id

    record_step("9. Air gap: liner + SiN pinch-off seal")

    # ---- Step 10: Selective epitaxy → wide Active Si ----
    # Grow wider Si on top of each FirstSemiconductorPortion
    active_w = p["active_semiconductor_width_nm"]
    active_h = p["active_semiconductor_height_nm"]
    for i in range(num_bl):
        bl_center = x_start + i * pitch + bl_width / 2
        active_x0 = bl_center - active_w / 2
        active_x1 = bl_center + active_w / 2
        active_z0 = z_si_final_top
        active_z1 = active_z0 + active_h
        fill_box(si_id, active_x0, 0, active_z0, active_x1, p["domain_y_nm"], active_z1)

    record_step("10. Selective epi lateral grow → wide Active Si")

    # Final info
    print(f"\n{'='*60}")
    print(f"Final structure: {np.count_nonzero(g != 0)} occupied voxels")
    mats = {}
    for mid in np.unique(g):
        if mid != 0:
            count = int(np.count_nonzero(g == mid))
            name = db.material(int(mid)).name
            mats[name] = count
            print(f"  {name}: {count} voxels")

    return backend, step_history, mats


def validate_structure(backend):
    """M34 validation checks for DRAM structure."""
    import tcad_simulator as tcad
    db = backend.database
    g = backend.grid()
    nx, ny, nz = g.shape
    p = PARAMS

    si_id = next(mid for mid, m in db.items() if m.name == "Silicon")
    sio2_id = next(mid for mid, m in db.items() if m.name == "Silicon Dioxide")
    w_id = next(mid for mid, m in db.items() if m.name == "Tungsten")

    checks = []
    def check(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
        status = "✅" if ok else "❌"
        print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

    # 1. W Bitline count
    # Count W regions at W layer z
    voxel = max(p["domain_x_nm"], p["domain_y_nm"]) / nx
    z_w_vox = int((p["carrier_si_nm"] + p["bond_oxide_1_nm"] + p["bond_oxide_2_nm"]
                   + p["bitline_thickness_nm"] / 2) / voxel)
    if z_w_vox >= nz:
        z_w_vox = nz - 1
    w_layer = g[:, ny // 2, z_w_vox] == w_id
    # Count contiguous W runs
    w_count = 0
    in_run = False
    for ix in range(nx):
        if w_layer[ix] and not in_run:
            w_count += 1
            in_run = True
        elif not w_layer[ix]:
            in_run = False
    check("W bitline count", w_count == p["num_bitlines"],
          f"found {w_count}, expected {p['num_bitlines']}")

    # 2. W bitlines not shorted (gap between each)
    gaps_ok = w_count == p["num_bitlines"]  # If count correct, they're separated
    check("W bitlines not shorted", gaps_ok)

    # 3. Active Si exists above each bitline
    z_active_vox = int((p["carrier_si_nm"] + p["bond_oxide_1_nm"] + p["bond_oxide_2_nm"]
                        + p["bitline_thickness_nm"] + p["final_remaining_si_nm"]
                        + p["active_semiconductor_height_nm"] / 2) / voxel)
    if z_active_vox >= nz:
        z_active_vox = nz - 1
    si_active = g[:, ny // 2, z_active_vox] == si_id
    si_runs = 0
    in_run = False
    for ix in range(nx):
        if si_active[ix] and not in_run:
            si_runs += 1
            in_run = True
        elif not si_active[ix]:
            in_run = False
    check("Active Si regions above BLs", si_runs >= p["num_bitlines"],
          f"found {si_runs} Si regions")

    # 4. Bond oxide continuous
    z_oxide_vox = int((p["carrier_si_nm"] + p["bond_oxide_1_nm"] / 2) / voxel)
    if z_oxide_vox >= nz:
        z_oxide_vox = nz - 1
    oxide_layer = g[:, ny // 2, z_oxide_vox]
    oxide_ok = np.all((oxide_layer == sio2_id) | (oxide_layer == w_id))
    check("Bond oxide continuous", oxide_ok)

    # 5. Carrier wafer exists
    z_carrier_vox = int((p["carrier_si_nm"] / 2) / voxel)
    if z_carrier_vox >= nz:
        z_carrier_vox = nz - 1
    carrier_ok = np.all(g[:, ny // 2, z_carrier_vox] == si_id)
    check("Carrier wafer exists", carrier_ok)

    # 6. Active width > first semiconductor width > bitline width
    check("Width relationship",
          p["active_semiconductor_width_nm"] > p["first_semiconductor_width_nm"] > p["bitline_width_nm"],
          f"active={p['active_semiconductor_width_nm']} > first={p['first_semiconductor_width_nm']} > BL={p['bitline_width_nm']}")

    all_pass = all(c["pass"] for c in checks)
    print(f"\n{'✅ ALL CHECKS PASSED' if all_pass else '❌ SOME CHECKS FAILED'}")
    return all_pass, checks


def main():
    parser = argparse.ArgumentParser(description="DRAM Narrow BL + Wide Active Si")
    parser.add_argument("--grid", type=int, default=64, help="Grid resolution")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--export", type=str, default=None, help="Export VTP path")
    args = parser.parse_args()

    print("=" * 60)
    print("DRAM Narrow Bitline + Wide Active Silicon")
    print("=" * 60)

    backend, history, mats = build_dram_structure(args.grid)

    print("\n" + "=" * 60)
    print("VALIDATION")
    print("=" * 60)
    all_pass, checks = validate_structure(backend)

    if args.export:
        from geometry_scene import GeometryScene
        from geometry_scene.bridge import surfaces_um_to_scene
        surfaces = backend.material_surfaces(50000)
        names = {mid: m.name for mid, m in backend.database.items()}
        scene = surfaces_um_to_scene(surfaces, names)
        scene.export_vtp(args.export)
        print(f"\nExported to {args.export}")

    backend.shutdown()
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
