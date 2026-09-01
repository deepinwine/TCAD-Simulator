# -*- coding: utf-8 -*-
"""ViennaPS 参考实验：掩膜开口的 SF6O2 干法刻蚀沟槽（ADR-014 沙盒）。

与 VoxelBackend 的 Basic Trench 流程同量纲（0.64µm 视场），用于 M9
ViennaPSBackend 的第一个标定样例。仅在沙盒内运行，不接入注册表。

用法：python experiments/viennaps/trench_reference.py [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run_trench(out_dir: Path) -> dict:
    import viennaps as ps

    # 与体素基准同量纲：视场 0.64µm、网格 8nm、掩膜开口 0.12µm、刻蚀 30s
    grid_delta = 0.008
    x_extent = 0.32
    trench_width = 0.12
    process_time = 30.0

    ps.setDimension(3)
    ps.setNumThreads(4)
    # 内部一律 µm/秒（与示例一致），与体素基准对照时换算 nm
    ps.Length.setUnit("um")
    ps.Time.setUnit("s")

    geometry = ps.Domain()
    ps.MakeTrench(
        geometry,
        gridDelta=grid_delta,
        xExtent=2.0 * x_extent,
        yExtent=2.0 * x_extent,
        trenchWidth=trench_width,
        trenchDepth=0.0,
        makeMask=True,
    ).apply()

    model_params = ps.SF6O2Etching.defaultParameters()
    model_params.ionFlux = 10.0
    model_params.etchantFlux = 10.0
    model_params.Ions.meanEnergy = 100.0
    model = ps.SF6O2Etching(model_params)

    process = ps.Process(geometry, model)
    process.setProcessDuration(process_time)

    cov_params = ps.CoverageParameters()
    cov_params.tolerance = 1e-3
    process.setParameters(cov_params)

    process.apply()

    mesh_path = out_dir / "viennaps_trench.vtk"
    geometry.saveSurfaceMesh(str(mesh_path))

    levels = geometry.getLevelSets()
    summary = {
        "ok": True,
        "engine": f"viennaps {getattr(ps, '__version__', 'unknown')}",
        "grid_delta_nm": grid_delta * 1000.0,
        "trench_width_nm": trench_width * 1000.0,
        "process_time_s": process_time,
        "level_sets": len(levels),
        "mesh_prefix": str(mesh_path),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir", default=".", help="表面网格输出目录（默认当前目录）",
    )
    parser.add_argument("--json", action="store_true", help="机读输出")
    args = parser.parse_args()

    try:
        summary = run_trench(Path(args.out_dir))
    except ImportError as exc:
        print(f"ViennaPS 引擎不可用：{exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - 沙盒独立验证要完整记录失败
        summary = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(summary)
    return 0 if summary.get("ok") else 4


if __name__ == "__main__":
    raise SystemExit(main())
