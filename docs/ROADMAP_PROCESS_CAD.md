# ROADMAP_PROCESS_CAD — M0–M12

One screen of truth for "what now". Target architecture: `docs/ARCHITECTURE_TARGET.md`;
decisions: `docs/DECISIONS.md`; pre-constitution milestone designs remain in
`docs/superpowers/specs|plans/` as history.

## M0 — Project Constitution ✅ (this milestone)

`AGENTS.md`, `docs/ARCHITECTURE_TARGET.md`, `docs/DECISIONS.md`, this roadmap.
Owner decision 2026-08-29: target stack React/TS/Vite + Three.js + Python (FastAPI path)
+ C++ ViennaPS route; strangler migration, never big-bang. GLM wrote; pending Codex review.

## M1 — Existing Runtime Regression Baseline (in progress)

Goal: make the current Process CAD workflow usable (done) and lock it with golden tests.

Already delivered (on `zcode/process-cad-shell`, pending merge + review):
- Fixed three-pane WebUI CAD shell; step drag/rename; snapshot timeline Previous/Next;
  atomic undo/redo; structured step errors; five process primitives
  (Strip/Fill/Flip/Bonding/Thinning); WebGL2 viewer (7 views, dual camera, X/Y/Z
  clipping, MaterialVisual); full test suite green; reproducible baseline runner on a
  fixed-physical-domain (640 nm) cubic grid with per-demo semantic structural checks
  (`tools/run_process_cad_baseline.py`, commit `10f6fbd`).

Remaining for M1 — golden regression tests for five named flows:

| Flow | Status |
| --- | --- |
| Basic Trench | ✅ demo + tests |
| Spacer Formation | ✅ demo + tests |
| Flip / Bond / Thin | ✅ demo + tests |
| W Plug + CMP | ❌ to add |
| Basic BEOL | ❌ to add |

Golden tests assert final geometry/material composition per flow so later migrations
(M2–M12) can prove behavior preservation.

## M2 — React Shell

`frontend/` with React + TypeScript + Vite: Process Flow, Parameters, Viewer shell,
Timeline shell. Parallel client only; legacy WebUI untouched (ADR-012).

## M3 — Three.js Viewer (React)

Mesh load, orbit/pan/zoom, six views + ISO, perspective/orthographic, X/Y/Z clipping,
material visibility/transparency, selection, measurement visualization.

## M4 — Python API Facade

Typed facade over the existing runtime: recipe, step, run, snapshot, geometry, materials.
Then incremental standardization toward FastAPI + Pydantic (compat API first; ADR-013).

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

## Current Branch State (2026-08-29)

- `zcode/process-cad-shell` — M1 shell + M0 constitution + calibrated baseline;
  pushed to `backup`.
- `codex/process-cad-shell` — parallel line at `4c3e32f` (M1 work).
- Next: Codex reviews the M0/M1 diff → merge both lines → land on `main` → begin M1
  golden-test completion (W Plug + CMP, Basic BEOL).
