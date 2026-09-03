#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M24: Performance benchmarks — geometry conversion, voxel ops, ViennaPS steps.

Usage: python tools/run_benchmarks.py [--output result.json] [--grid 64|128|256]
"""
import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")


def _time_ms(fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = (time.perf_counter() - started) * 1000
    return elapsed, result


def bench_voxel_pipeline(grid_size):
    """Voxel backend: init → deposit → etch → surfaces."""
    import tcad_simulator as tcad
    from geometry_scene.bridge import surfaces_um_to_scene

    db = tcad.MaterialDatabase()
    model = tcad.ProcessModel(
        db, grid_shape=(grid_size,)*3,
        voxel_size_nm=640.0 / grid_size, max_workers=1,
    )
    results = {}

    flow = tcad.load_demo_flows(db)["Basic Trench"]["steps"]
    total_start = time.perf_counter()
    for blob in flow:
        step = tcad._webui_deserialize_step(blob, db)
        if step is not None:
            step.execute(model)
    results["full_recipe_s"] = round(time.perf_counter() - total_start, 3)

    ms, surfaces = _time_ms(model.get_material_surfaces, 40000)
    results["surface_extraction_ms"] = round(ms, 1)
    results["triangle_count"] = sum(s[1].shape[0] for s in surfaces)

    ms, scene = _time_ms(surfaces_um_to_scene, surfaces)
    results["scene_conversion_ms"] = round(ms, 1)

    try:
        model.parallel.shutdown()
    except Exception:
        pass
    return results


def bench_scene_to_voxel(grid_size):
    """GeometryScene → Voxel grid conversion."""
    import numpy as np
    from geometry_scene import GeometryScene
    from geometry_scene.bridge import scene_to_voxel_grid

    tri_count = grid_size * grid_size * 2
    triangles = np.random.rand(tri_count, 3, 3) * 100
    scene = GeometryScene.from_surfaces([(1, triangles)])
    voxel_nm = 640.0 / grid_size
    shape = (grid_size, grid_size, grid_size)

    ms, grid = _time_ms(scene_to_voxel_grid, scene, shape, voxel_nm)
    return {
        "grid_size": grid_size,
        "triangle_count": tri_count,
        "voxelization_ms": round(ms, 1),
        "occupied_voxels": int((grid != 0).sum()),
    }


def bench_viennaps(grid_nm=16.0):
    """ViennaPS: init → dry etch."""
    try:
        import viennaps  # noqa: F401
    except ImportError:
        return {"skipped": "viennaps not installed"}

    from process_backend import create_backend

    class S:
        def __init__(self, n, p):
            self.name, self.params = n, p

    backend = create_backend("viennaps", grid_nm=grid_nm)
    results = {"grid_nm": grid_nm}

    ms, _ = _time_ms(backend.execute_step, S("Initialize Wafer", {"thickness_nm": 200.0}))
    results["initialize_ms"] = round(ms, 1)

    ms, _ = _time_ms(backend.execute_step, S("Etch", {"time": 5.0, "chemistry": "Dry"}))
    results["etch_5s_ms"] = round(ms, 1)

    ms, surfaces = _time_ms(backend.material_surfaces, 20000)
    results["surfaces_ms"] = round(ms, 1)
    results["triangle_count"] = sum(s[1].shape[0] for s in surfaces) if surfaces else 0

    backend.shutdown()
    return results


def bench_hybrid(grid=32):
    """HybridBackend FAST→ACCURATE→FAST."""
    try:
        import viennaps  # noqa: F401
    except ImportError:
        return {"skipped": "viennaps not installed"}

    from process_backend.hybrid import ACCURATE, FAST, HybridBackend, ModeSelector

    backend = HybridBackend(grid=grid)
    sel = ModeSelector()
    sel.set_mode("Etch", ACCURATE)
    backend._selector = sel

    import tcad_simulator as tcad
    db = backend._fast.database
    flow = tcad.load_demo_flows(db)["Basic Trench"]["steps"]

    results = {"grid": grid}
    total_start = time.perf_counter()

    for blob in flow:
        step = tcad._webui_deserialize_step(blob, db)
        if step is not None:
            backend.execute_step(step)

    results["full_hybrid_s"] = round(time.perf_counter() - total_start, 3)
    results["routing_log"] = backend.routing_log
    results["canonical_scene_triangles"] = (
        backend.canonical_scene.total_triangles
        if backend.canonical_scene else 0
    )
    backend.shutdown()
    return results


def run_all(grid=64, output=None):
    report = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "grid": grid,
    }

    print(f"=== Voxel pipeline (grid={grid}) ===")
    report["voxel"] = bench_voxel_pipeline(grid)
    print(json.dumps(report["voxel"], indent=2))

    print(f"\n=== Scene→Voxel conversion (grid={grid}) ===")
    report["scene_to_voxel"] = bench_scene_to_voxel(grid)
    print(json.dumps(report["scene_to_voxel"], indent=2))

    print("\n=== ViennaPS (grid_nm=16) ===")
    report["viennaps"] = bench_viennaps(16.0)
    print(json.dumps(report["viennaps"], indent=2))

    print("\n=== Hybrid FAST→ACC→FAST (grid=32) ===")
    report["hybrid"] = bench_hybrid(32)
    print(json.dumps(report["hybrid"], indent=2))

    if output:
        Path(output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nSaved to {output}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Run performance benchmarks")
    parser.add_argument("--grid", type=int, default=64, help="Grid resolution")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()
    run_all(args.grid, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
