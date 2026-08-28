#!/usr/bin/env python3
"""Reproducible Process CAD baseline.

Runs the three Process CAD demo recipes headless on a configurable grid and
records per-demo wall time, process peak RSS, occupied-voxel/material counts,
and preview-mesh triangle counts with mesh generation time. Results are written
as JSON so runs can be archived and compared across revisions.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import tcad_simulator as tcad  # noqa: E402


DEMO_NAMES = ("Basic Trench", "Spacer Formation", "Bonding + Thinning")
MESH_FACE_LIMIT = 20000


def _peak_rss_mb() -> float:
    """Process peak RSS in MB (macOS reports bytes, Linux reports KiB)."""
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return float(ru) / (1024.0 * 1024.0)
    return float(ru) / 1024.0


def _void_material_id(database: tcad.MaterialDatabase) -> int:
    try:
        return int(database.id_for("Void"))
    except Exception:
        return 0


def _run_demo(name: str, grid: int) -> Dict[str, Any]:
    database = tcad.MaterialDatabase()
    recipe = tcad._webui_demo_recipes(database)[name]
    # The Bonding demo needs ~21 voxels of Z headroom on top of the front-side
    # structure, so small grids keep a floor of 96 Z slices (the demo's design
    # height at grid 64); the official 128 grid still scales to 192.
    nz = max(96, grid * 3 // 2)
    model = tcad.ProcessModel(
        database,
        grid_shape=(grid, grid, nz),
        voxel_size_nm=10.0,
        max_workers=1,
    )
    try:
        started = time.perf_counter()
        for blob in recipe["steps"]:
            if not blob.get("enabled", True):
                continue
            step = tcad._webui_deserialize_step(blob, database)
            if step is None:
                raise RuntimeError(f"demo {name}: could not deserialize step {blob.get('name')!r}")
            step.execute(model)
        elapsed_s = time.perf_counter() - started

        mesh_started = time.perf_counter()
        surfaces = model.get_material_surfaces(face_limit=MESH_FACE_LIMIT)
        mesh_elapsed_s = time.perf_counter() - mesh_started

        void_id = _void_material_id(database)
        occupied_voxels = int(np.count_nonzero(model.grid != void_id))
        present = sorted({int(m) for m in np.unique(model.grid) if int(m) != void_id})
        triangle_count = int(sum(int(s[1].shape[0]) for s in surfaces))

        return {
            "ok": True,
            "elapsed_s": round(elapsed_s, 3),
            # ru_maxrss is monotonic for the process, so per-demo values are the
            # cumulative peak at the moment the demo finished.
            "peak_rss_mb": round(_peak_rss_mb(), 1),
            "material_count": len(present),
            "occupied_voxels": occupied_voxels,
            "triangle_count": triangle_count,
            "mesh_elapsed_s": round(mesh_elapsed_s, 3),
        }
    finally:
        try:
            model.parallel.shutdown()
        except Exception:
            pass


def run_baseline(grid_size: int) -> Dict[str, Any]:
    grid = max(24, int(grid_size))
    result: Dict[str, Any] = {"ok": True, "grid": grid, "voxel_nm": 10.0, "demos": {}}
    for name in DEMO_NAMES:
        try:
            result["demos"][name] = _run_demo(name, grid)
        except Exception as exc:  # noqa: BLE001 - record failures instead of aborting
            result["ok"] = False
            result["demos"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Process CAD baseline and write a JSON report.")
    parser.add_argument("--grid", type=int, default=128, help="X/Y grid size (NZ is 1.5x); default 128")
    parser.add_argument("--output", required=True, help="Path of the JSON report to write")
    args = parser.parse_args()

    result = run_baseline(grid_size=args.grid)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "ok": result["ok"],
        "grid": result["grid"],
        "demos": {
            name: {k: v for k, v in demo.items() if k in ("ok", "elapsed_s", "triangle_count", "mesh_elapsed_s")}
            for name, demo in result["demos"].items()
        },
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
