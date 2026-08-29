# ARCHITECTURE_TARGET — TCAD Studio Long-Term Architecture

Companion to `AGENTS.md` (constitution). This file describes where the project is going
and how it gets there without a big-bang rewrite. Current-system behavior is described in
`docs/ARCHITECTURE.md`; nothing there changes until an approved migration milestone.

## Target Data Flow

```text
React / Three.js
    |  HTTP / WebSocket API
    v
Python Application Layer (Recipe, ProcessStep, jobs, state, routing)
    v
Backend Router
    |                |
    v                v
Voxel Backend    ViennaPS Backend
(FAST)           (ACCURATE)
    |                |
    +-------+--------+
            v
    Geometry / VTK interchange
            v
        Three.js
```

Layout runs on a separate path: `GDS / OASIS -> gdstk / KLayout (LayoutAdapter) ->
normalized mask geometry -> Process Recipe / Backend`. Lithography never depends on
KLayout object types.

## Layer Responsibilities

- **React (frontend/)**: Process Flow editor, parameter forms, material tree, timeline,
  job state, project/session state, metrology UI. Owns UI state only. Sends typed process
  requests; never computes deposited/etched geometry.
- **Three.js**: mesh rendering, camera (perspective/orthographic), X/Y/Z clipping,
  selection, visibility, transparency, measurement and cross-section visualization.
  Visualization only — never mutates simulation state.
- **Python application layer**: recipe, ProcessStep execution, simulation jobs, snapshots
  and replay, material registry, backend routing, persistence, metrology orchestration,
  LLM/AI workflows, serialization, and the API surface (FastAPI + Pydantic when the new
  API layer is introduced). Python-version policy: the existing runtime keeps Python
  3.10+ compatibility (as documented in the README); new application/API-layer modules
  (M4+) target Python 3.12+ and may declare it explicitly — do not gratuitously drop
  3.10 support from the existing runtime.
- **C++ accurate engine**: ViennaPS + ViennaLS + VTK behind adapters (official bindings or
  pybind11). Used for surface evolution, HAR etching, plasma etch, wet undercut, ALD/CVD
  topography, shadowing, redeposition, selective processes — where voxel geometry is
  insufficient. The application must still run when ViennaPS is unavailable.

## Geometry & Data

- VTK is the scientific geometry interchange: VTP/VTK PolyData for surfaces, VTU for
  volume meshes. HDF5 or Zarr for large voxel/field arrays.
- STL remains an export format, not the internal representation.
- Avoid: per-voxel Three.js cubes, repeated voxel↔mesh and voxel↔level-set conversions,
  giant nested-JSON geometry payloads (prefer binary/streaming representations).

## M2 Compatibility API — Minimum Stable Contract (resolves the M2/M4 ordering)

React (M2) starts **before** the typed API facade exists (M4). Resolution: the existing
WebUI HTTP API is frozen as the **M2 Compatibility API**; React consumes exactly this
surface; M4 later wraps the same semantics with typed schemas (FastAPI/Pydantic) and may
deprecate members only behind a versioned facade — never by breaking the frozen set
before React parity (M5).

Frozen core (additive-only evolution — new fields/endpoints allowed, semantics of listed
members immutable until M4 versions them):

| Group | Endpoints |
| --- | --- |
| Bootstrap / session | `GET /api/init`, `GET /api/health`, `GET /api/status`, `GET /api/log`, `POST /api/load_autosave` |
| Recipe editing | `POST /api/recipe/new\|save\|load\|delete\|export\|import\|add\|insert_steps\|remove\|duplicate\|move\|rename-step\|set_name`, `POST /api/step/set` |
| Execution & history | `POST /api/run/step\|all\|to`, `POST /api/undo\|redo`, `POST /api/reset`, `POST /api/domain/apply` |
| Timeline | `POST /api/timeline/get\|restore` |
| Preview / geometry (binary) | `GET /api/preview/manifest\|geom\|elements\|stl`, `GET /api/slice`, `POST /api/render/gbuffer` |
| Materials & masks | `GET/POST /api/material_colors`, `GET /api/process_config`, `POST /api/mask/preview`, `POST /api/mask/preview_step`, `POST /api/upload/mask` |
| History & UI state | `GET /api/history`, `POST /api/history/load`, `POST /api/ui_state`, `POST /api/save` |
| Export | `POST /api/export`, `GET /api/export/download` |

Rules:

1. Any endpoint or response field a React component reads must be added to this table
   (in the same PR) before the client depends on it.
2. Binary endpoints (`geom`, `slice`, `gbuffer`, downloads) stay binary — React never
   parses them as JSON.
3. Cookie/session model stays as-is; WebSocket additions are new endpoints, not changes.
4. Structured step-failure payloads keep their current field names
   (`step_index`, `instance_name`, `step_type`, `parameter_path`, `error`,
   `error_type`, `suggestion`, `rolled_back`).

## Frontend Structure (when M2 begins)

```text
frontend/
├── package.json / vite.config.ts / tsconfig.json
└── src/
    ├── App.tsx
    ├── components/   # ProcessFlow, ParameterPanel, MaterialPanel, Timeline, Toolbar
    ├── viewer/       # ThreeViewer, camera, clipping, materials, selection
    ├── api/          # tcadApi client
    ├── state/
    └── types/
```

React is a parallel client against the existing backend; the legacy WebUI stays until
React passes feature parity and regression tests (M5). Never delete the old WebUI early.

## Migration Strategy — Strangler, Never Big Bang

Preferred sequence (details and status in `docs/ROADMAP_PROCESS_CAD.md`):

1. **M1** Stabilize the existing Process CAD workflow and lock it with golden regression
   tests (five named flows).
2. **M2** React/TS/Vite shell as a parallel frontend (`frontend/`).
3. **M3** Three.js viewer inside React (mesh load, orbit/pan/zoom, six views + ISO,
   clipping, materials, selection).
4. **M4** Stable Python API facade around the existing runtime; then standardize toward
   FastAPI + Pydantic (compatibility API first, strangler-style).
5. **M5** React reaches parity → legacy WebUI deprecated (not before).
6. **M6** `LayoutAdapter` + optional KLayout; gdstk kept.
7. **M7** `ProcessBackend` interface; wrap `ProcessModel` as `VoxelBackend` with behavior
   unchanged.
8. **M8** ViennaPS prototype sandboxed under `experiments/viennaps` only.
9. **M9** `ViennaPSBackend` behind the interface.
10. **M10** `GeometryScene` / VTK bridge unifying voxel and ViennaPS output for the viewer.
11. **M11** Hybrid Fast/Accurate per-process mode selection.
12. **M12** Package as desktop macOS / Windows application.

Hard rules during migration:

- The compatibility path `Recipe -> PROCESS_STEP_FACTORIES -> ProcessStep.execute(model)
  -> ProcessModel` keeps working at every step.
- Adapters over rewrites; new architecture only when a milestone calls for it.
- One concern per change: never mix migration + physics + UI redesign in one diff.
- If unsure, prefer `existing behavior + adapter + tests` over `replacement + refactor`.

## Backend Capability Model (M7+)

- Every backend declares per-step capabilities; unsupported steps fail explicitly with
  fallback guidance instead of silently degrading.
- Fast/Accurate assignment is recipe- or user-driven; e.g. Deposit FAST, HAR Etch
  ACCURATE, ALD ACCURATE, Fill/CMP/Bonding FAST.
- No assumption that ViennaPS handles CMP, implant, bonding, flip, or thinning.
