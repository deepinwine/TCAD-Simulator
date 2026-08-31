# ROADMAP_PROCESS_CAD — M0–M12

One screen of truth for "what now". Target architecture: `docs/ARCHITECTURE_TARGET.md`;
decisions: `docs/DECISIONS.md`; pre-constitution milestone designs remain in
`docs/superpowers/specs|plans/` as history.

## M0 — Project Constitution ✅ (this milestone)

`AGENTS.md`, `docs/ARCHITECTURE_TARGET.md`, `docs/DECISIONS.md`, this roadmap.
Owner decision 2026-08-29: target stack React/TS/Vite + Three.js + Python (FastAPI path)
+ C++ ViennaPS route; strangler migration, never big-bang. GLM wrote; pending Codex review.

## M1 — Existing Runtime Regression Baseline ✅

Goal: make the current Process CAD workflow usable (done) and lock it with golden tests.

Already delivered (on `zcode/process-cad-shell`, pending merge + review):
- Fixed three-pane WebUI CAD shell; step drag/rename; snapshot timeline Previous/Next;
  atomic undo/redo; structured step errors; five process primitives
  (Strip/Fill/Flip/Bonding/Thinning); WebGL2 viewer (7 views, dual camera, X/Y/Z
  clipping, MaterialVisual); full test suite green; reproducible baseline runner on a
  fixed-physical-domain (640 nm) cubic grid with per-flow semantic structural checks.
- Added the public `load_demo_flows(material_db)` registry shared by WebUI, Golden tests,
  and `tools/run_process_cad_baseline.py`; the legacy private WebUI helper remains a
  compatibility wrapper.

Golden regression tests now cover all five named flows:

| Flow | Status |
| --- | --- |
| Basic Trench | ✅ demo + tests |
| Spacer Formation | ✅ demo + tests |
| Flip / Bond / Thin | ✅ demo + tests |
| W Plug + CMP | ✅ demo + tests |
| Basic BEOL | ✅ demo + tests |

Golden tests assert final geometry/material composition per flow so later migrations
(M2–M12) can prove behavior preservation.

## M2 — React Shell ✅（已交付）

`frontend/` with React + TypeScript + Vite: dense three-pane Process Flow /
Parameters / Viewer workspace, run + timeline integration, and a minimal real Three.js
mesh viewer. Parallel client only; legacy WebUI untouched (ADR-012). React consumes
**exactly** the frozen "M2 Compatibility API" defined in `docs/ARCHITECTURE_TARGET.md`
(existing WebUI HTTP endpoints, additive-only) — this is how M2 could start before the
M4 facade exists. Delivered on `codex/m2-react-shell` (see Current Branch State).

## M3 — Three.js Viewer (React)

Mesh load, orbit/pan/zoom, six views + ISO, perspective/orthographic, X/Y/Z clipping,
material visibility/transparency, selection, measurement visualization.

## M4 — Python API Facade

Typed facade over the existing runtime: recipe, step, run, snapshot, geometry, materials.
It wraps the frozen M2 Compatibility API semantics with typed schemas and then
standardizes toward FastAPI + Pydantic (ADR-013). Deprecations happen only behind the
versioned facade — the frozen surface stays intact until React parity (M5). New
API-layer modules target Python 3.12+ while the existing runtime keeps 3.10+
compatibility.

## M5 — React Parity

React reaches legacy-WebUI feature parity with regression tests green → legacy WebUI
deprecated (not deleted before).

## M6 — KLayout LayoutAdapter

`LayoutAdapter` abstraction; gdstk + optional KLayout for GDS/OASIS, hierarchy, booleans,
ROI; normalized mask geometry to lithography (ADR-016).

## M7 — ProcessBackend Interface

```text
ProcessBackend -> VoxelBackend -> ProcessModel   (behavior unchanged)
```

## M8 — ViennaPS Sandbox

Prototype only under `experiments/viennaps`; standalone validation (ADR-014).

## M9 — ViennaPSBackend

Accurate Mode behind the backend interface; capability model with explicit fallbacks.

## M10 — GeometryScene / VTK Bridge

Unified voxel + ViennaPS output → GeometryScene → VTK → Three.js (ADR-015).

## M11 — Hybrid Fast/Accurate

Per-process mode selection (e.g. Deposit FAST, HAR Etch ACCURATE, ALD ACCURATE,
Fill/CMP/Bonding FAST).

## M12 — Desktop Packaging

macOS / Windows application packaging (license review for Qt/PyQt5 implications first).

## Backlog (owner slots these into the sequence)

- Parameter sweep / DOE runner with metrology comparison (natural fit after M4).
- Device regions, electrodes, meshing export, electrical-solve interface stub.
- Calibration data ingestion; reproducible experiment packages.
- Incremental extraction of Worker/frontend/model subdomains; stable CI.
- Demo-load main-thread stall investigation (~30–60 s, observed 2026-08-28).

## Current Branch State (2026-08-31, M2 implementation complete)

| Branch | Commit | Relationship |
| --- | --- | --- |
| `origin/main`（FonaTech 公开仓库） | `41a2fcd` | 公开基线（2026-05 README 更新），不含任何 M1/M2 实现 |
| 本地 `main` | `d15722d` | 线性领先 `origin/main` 一个提交（M1 设计文档）；不含实现 |
| `backup/main`（deepinwine） | `063838a` | **M1 已通过 PR #1 合并**（五流程 Golden 基线 + 契约测试） |
| `codex/m2-react-shell` | `c47acdf`（实现尖端，其后再叠加 Task 9 文档收口提交） | 线性领先 `backup/main` 28 个提交（含 M2 全部 27 个实现/测试提交 + 本文档提交），可快进合并 |

祖先关系：`main ⊂ 063838a ⊂ …M2 提交… ⊂ c47acdf ⊂ docs 收口提交`。`origin` 上不存在
任何 M1/M2 功能分支。**是否将 M2 合并进 `backup/main`、何时同步 `origin/main` 由仓库
所有者决定；Agent 不得自行合并 feature 分支或推送 `origin`（ADR-010/017）。**

- Next: 独立 architecture/code review 通过后由所有者合并 M2 → 开始 M3 Three.js Viewer
  完善（正交相机、X/Y/Z 裁剪、材料显示控制、选择与测量）。
