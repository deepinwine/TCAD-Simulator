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

## M3 — Three.js Viewer (React) ✅（已交付）

Mesh load, orbit/pan/zoom, six views + ISO (delivered with M2); then completed in
M3 on `codex/m3-viewer`: perspective/orthographic projection toggle (equivalent
view-size switch, no visual jump), X/Y/Z independent clipping planes
(normalized sliders mapped to world coordinates), material visibility/opacity
control (from manifest `visual` data, browser-local only), mesh picking with hit
info + highlight, and two-point distance measurement with markers/line/readout.
Plus: run network-failure reconciliation — a one-click 重新同步 that refetches the
server-authoritative timeline and forces a viewer geometry refresh (closes the
M2 known limitation observed during acceptance). All M3 capabilities issue zero
API requests.

## M4 — Python API Facade ✅（已交付）

Typed facade over the existing runtime: recipe, step, run, snapshot, geometry, materials.
Delivered on `codex/m4-api-facade`: `process_api/` package (typed dataclass schemas with
camelCase JSON identical to the frozen contract; session facade with load/init/set_step/
run_step/run_to/run_all/get_timeline/restore_timeline/preview_manifest/material_stl;
structured ProcessCadError), runtime-parity tests (facade vs direct runtime identical
voxels/materials), and an optional read-only FastAPI `/api/v2` adapter with error
envelopes matching contract semantics. It wraps the frozen M2 Compatibility API
semantics with typed schemas and then
standardizes toward FastAPI + Pydantic (ADR-013). Deprecations happen only behind the
versioned facade — the frozen surface stays intact until React parity (M5). New
API-layer modules target Python 3.12+ while the existing runtime keeps 3.10+
compatibility.

## M5 — React Parity ✅（核心工艺流已交付）

React reaches legacy-WebUI feature parity with regression tests green → legacy WebUI
deprecated (not deleted before). Delivered on `codex/m5-parity`: undo/redo (with
geometry/timeline resync), recipe management (demo load/new/save/export-download/
import via the frozen contract), step structure editing (add/remove/duplicate/move/
rename with server-side status cascade), and mask upload + preview for Exposure steps
(multipart upload with nested set_step application + server-rendered preview image).
Remaining legacy-only areas (History/Domain Settings/AI Agent drawers) are Backlog —
secondary workflow tools, not core process editing. Legacy-WebUI deprecation decision
stays with the owner (ADR-012: only after parity + regression green).

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

## Current Branch State (2026-09-01, M5 implementation complete)

| Branch | Commit | Relationship |
| --- | --- | --- |
| `origin/main`（FonaTech 公开仓库） | `41a2fcd` | 公开基线（2026-05 README 更新），不含任何 M1–M4 实现 |
| `backup/main`（deepinwine） | `3f7faba` | **M4 已由所有者授权快进合并**（M3 `31ce391` + M4 7 提交，2026-08-31） |
| 本地 `main` | `3f7faba` | 与 `backup/main` 一致 |
| `codex/m4-api-facade` | `3f7faba` | M4 交付分支，已全部包含于 `main`（保留作历史） |
| `codex/m5-parity` | M5 交付分支（计划 + 4 个功能提交 + 本文档提交） | 线性领先 `backup/main`（`f61e069`），可快进合并 |

祖先关系：`41a2fcd ⊂ …M2/M3 提交… ⊂ 31ce391 ⊂ …M4 7 提交… ⊂ 3f7faba`。
**`origin`（FonaTech）是上游第三方仓库，不归本项目所有者——永远不做同步/推送
（ADR-010/017）；`backup`（deepinwine）是唯一的开发与发布远端。** 2026-08-31 曾误开
fork PR #1，已立即关闭。

- Next: M5 经所有者审查后合并 `backup/main` → 旧 WebUI 弃用决定（ADR-012：需所有者
  单独评审）→ 开始 M6 KLayout LayoutAdapter 或按 Backlog 补 History/Domain 抽屉。
