#!/usr/bin/env python3
"""Reproducible Process CAD baseline.

Runs the five named Process CAD flows headless on a fixed-size cubic grid and
records per-demo wall time, best-effort process RSS (see ``peak_rss_scope``),
occupied-voxel/material counts, semantic acceptance checks, and preview-mesh triangle
counts with mesh generation time. Results are written as JSON so runs can be archived
and compared across revisions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import resource  # Unix only; absent on Windows
except ImportError:
    resource = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import tcad_simulator as tcad  # noqa: E402


DEMO_NAMES = (
    "Basic Trench",
    "Spacer Formation",
    "Bonding + Thinning",
    "W Plug + CMP",
    "Basic BEOL",
)
MESH_FACE_LIMIT = 20000
PHYSICAL_EXTENT_NM = 640.0


def _peak_rss_mb() -> Optional[float]:
    """Best-effort process RSS in MB; None when unavailable (Windows without psutil).

    Prefers ``resource.getrusage`` (macOS reports bytes, Linux reports KiB); falls back
    to ``psutil``'s current RSS. Callers must handle ``None``.
    """
    if resource is not None:
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return float(ru) / (1024.0 * 1024.0)
        return float(ru) / 1024.0
    try:
        import psutil  # type: ignore[import-not-found]

        return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        return None


def _rss_scope() -> str:
    """Document how ``peak_rss_mb`` was measured so reports stay comparable."""
    if resource is not None:
        # ru_maxrss is monotonic for the process: per-demo values are the cumulative
        # peak at the moment the demo finished.
        return "ru_maxrss_cumulative_process"
    try:
        import psutil  # type: ignore[import-not-found]

        psutil.Process()
        return "psutil_current_rss_per_demo"
    except Exception:
        return "unavailable"


def _void_material_id(database: tcad.MaterialDatabase) -> int:
    try:
        return int(database.id_for("Void"))
    except Exception:
        return 0


def _xy_component_count(mask: np.ndarray) -> int:
    mask = np.asarray(mask, dtype=bool)
    seen = np.zeros_like(mask, dtype=bool)
    count = 0
    nx, ny = mask.shape
    for x, y in np.argwhere(mask):
        if seen[x, y]:
            continue
        count += 1
        seen[x, y] = True
        stack = [(int(x), int(y))]
        while stack:
            current_x, current_y = stack.pop()
            for next_x, next_y in (
                (current_x - 1, current_y),
                (current_x + 1, current_y),
                (current_x, current_y - 1),
                (current_x, current_y + 1),
            ):
                if not (0 <= next_x < nx and 0 <= next_y < ny):
                    continue
                if mask[next_x, next_y] and not seen[next_x, next_y]:
                    seen[next_x, next_y] = True
                    stack.append((next_x, next_y))
    return count


def _materials_are_face_adjacent(grid: np.ndarray, first: int, second: int) -> bool:
    for axis in range(3):
        lower = [slice(None)] * 3
        upper = [slice(None)] * 3
        lower[axis] = slice(None, -1)
        upper[axis] = slice(1, None)
        lower_values = grid[tuple(lower)]
        upper_values = grid[tuple(upper)]
        if np.any(
            ((lower_values == first) & (upper_values == second))
            | ((lower_values == second) & (upper_values == first))
        ):
            return True
    return False


def _semantic_checks(
    name: str,
    database: tcad.MaterialDatabase,
    model: tcad.ProcessModel,
    material_names: set[str],
    triangle_count: int,
) -> Dict[str, bool]:
    checks: Dict[str, bool] = {
        "occupied_geometry": bool(np.any(model.grid != _void_material_id(database))),
        "mesh_generated": int(triangle_count) > 0,
    }
    if name == "Basic Trench":
        checks.update(
            {
                "silicon_present": "Silicon" in material_names,
                "patterned_oxide_present": "Silicon Dioxide" in material_names,
                "resist_stripped": "Photoresist" not in material_names,
                "trench_depth_visible": int(model.height_map.max()) - int(model.height_map.min()) >= 4,
            }
        )
    elif name == "Spacer Formation":
        checks.update(
            {
                "silicon_present": "Silicon" in material_names,
                "nitride_spacer_present": "Silicon Nitride" in material_names,
                "core_removed": "Polysilicon" not in material_names,
                "resist_stripped": "Photoresist" not in material_names,
            }
        )
    elif name == "Bonding + Thinning":
        checks.update(
            {
                "silicon_present": "Silicon" in material_names,
                "oxide_interface_present": "Silicon Dioxide" in material_names,
                "active_side_bottom": str(model.active_side).strip().lower() == "bottom",
            }
        )
    elif name == "W Plug + CMP":
        tungsten = database.id_for("Tungsten")
        silicon = database.id_for("Silicon")
        checks.update(
            {
                "silicon_present": "Silicon" in material_names,
                "oxide_present": "Silicon Dioxide" in material_names,
                "tungsten_plugs_present": "Tungsten" in material_names,
                "resist_stripped": "Photoresist" not in material_names,
                "no_tungsten_blanket": not bool(
                    np.any(np.all(model.grid == tungsten, axis=(0, 1)))
                ),
                "contacts_touch_silicon": _materials_are_face_adjacent(
                    model.grid,
                    tungsten,
                    silicon,
                ),
                "four_contact_plugs": _xy_component_count(
                    np.any(model.grid == tungsten, axis=2)
                )
                == 4,
                "planar_surface": int(model.height_map.max())
                - int(model.height_map.min())
                <= 1,
            }
        )
    elif name == "Basic BEOL":
        copper = database.id_for("Copper")
        tantalum = database.id_for("Tantalum")
        silicon = database.id_for("Silicon")
        checks.update(
            {
                "silicon_present": "Silicon" in material_names,
                "oxide_present": "Silicon Dioxide" in material_names,
                "copper_lines_present": "Copper" in material_names,
                "tantalum_liner_present": "Tantalum" in material_names,
                "resist_stripped": "Photoresist" not in material_names,
                "no_copper_blanket": not bool(
                    np.any(np.all(model.grid == copper, axis=(0, 1)))
                ),
                "no_tantalum_blanket": not bool(
                    np.any(np.all(model.grid == tantalum, axis=(0, 1)))
                ),
                "two_copper_lines": _xy_component_count(
                    np.any(model.grid == copper, axis=2)
                )
                == 2,
                "copper_isolated_from_silicon": not _materials_are_face_adjacent(
                    model.grid,
                    copper,
                    silicon,
                ),
                "planar_surface": int(model.height_map.max())
                - int(model.height_map.min())
                <= 1,
            }
        )
    return checks


def _run_demo(name: str, grid: int, voxel_nm: float) -> Dict[str, Any]:
    database = tcad.MaterialDatabase()
    recipe = tcad.load_demo_flows(database)[name]
    model = tcad.ProcessModel(
        database,
        grid_shape=(grid, grid, grid),
        voxel_size_nm=float(voxel_nm),
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
        material_names = sorted(database.material(material_id).name for material_id in present)
        triangle_count = int(sum(int(s[1].shape[0]) for s in surfaces))
        checks = _semantic_checks(name, database, model, set(material_names), triangle_count)
        rss = _peak_rss_mb()

        return {
            "ok": bool(all(checks.values())),
            "elapsed_s": round(elapsed_s, 3),
            "peak_rss_mb": (round(rss, 1) if rss is not None else None),
            "material_count": len(present),
            "materials": material_names,
            "occupied_voxels": occupied_voxels,
            "triangle_count": triangle_count,
            "mesh_elapsed_s": round(mesh_elapsed_s, 3),
            "checks": checks,
        }
    finally:
        try:
            model.parallel.shutdown()
        except Exception:
            pass


def run_baseline(grid_size: int) -> Dict[str, Any]:
    grid = max(32, int(grid_size))
    voxel_nm = float(PHYSICAL_EXTENT_NM) / float(grid)
    result: Dict[str, Any] = {
        "ok": True,
        "grid": grid,
        "grid_shape": [grid, grid, grid],
        "physical_extent_nm": float(PHYSICAL_EXTENT_NM),
        "voxel_nm": float(voxel_nm),
        "peak_rss_scope": _rss_scope(),
        "demos": {},
    }
    for name in DEMO_NAMES:
        try:
            demo = _run_demo(name, grid, voxel_nm)
            result["demos"][name] = demo
            if not demo.get("ok"):
                result["ok"] = False
        except Exception as exc:  # noqa: BLE001 - record failures instead of aborting
            result["ok"] = False
            result["demos"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Process CAD baseline and write a JSON report.")
    parser.add_argument("--grid", type=int, default=128, help="Cubic grid resolution (minimum 32); default 128")
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
