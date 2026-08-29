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

Frozen core (verified against the HTTP dispatchers in `tcad_simulator.py`; executable
contract tests: `tests/test_webui_cad_shell.py::M2ApiContractTests`). "JSON" responses
are `{"ok": bool, ...}` envelopes (successful worker results under `result`). Binary
endpoints send raw bytes with `application/octet-stream` (JSON error envelopes on 4xx/5xx).

| Endpoint | Method | Request (minimal) | Response |
| --- | --- | --- | --- |
| `/api/health` | GET | — | JSON |
| `/api/init` | GET | — | JSON; `result`: `recipe` (step list), `model` (summary), `recipe_factories`, `materials`, `demo_recipes`, `recipes`, `ui_state` |
| `/api/status`, `/api/log`, `/api/history` | GET | — | JSON |
| `/api/process_config` | GET | — | JSON |
| `/api/load_autosave` | POST | `{}` | JSON |
| `/api/recipe/new` | POST | `{name, current_name?}` | JSON |
| `/api/recipe/save` | POST | `{name, ui_state?}` | JSON |
| `/api/recipe/load`, `/api/recipe/delete`, `/api/recipe/set_name` | POST | recipe id/name fields | JSON |
| `/api/recipe/export` | GET | query (recipe id) | JSON (recipe blob) |
| `/api/recipe/import` | POST | `{recipe, autosave_current?, current_name?}` | JSON |
| `/api/recipe/add`, `/api/recipe/insert_steps`, `/api/recipe/remove`, `/api/recipe/duplicate` | POST | step payload / `{index}` / `{steps, insert_index?}` | JSON; `result`: full step list |
| `/api/recipe/move` | POST | `{index, direction:"up"\|"down"}` 或 `{index, to}` | JSON; `result`: step list |
| `/api/recipe/rename-step` | POST | `{index, instance_name (1–80 chars)}` | JSON; `result`: updated step |
| `/api/step/set` | POST | `{index, enabled?, params?, loop?, group?, no_autosave?}` | JSON; `result`: step, `statuses`: runtime-status list, `warnings?` |
| `/api/run/step` | POST | `{index}` | JSON; failure = flat structured payload (`step_index`, `instance_name`, `step_type`, `parameter_path`, `error`, `error_type`, `suggestion`, `rolled_back`) |
| `/api/run/all`, `/api/run/to` (alias `/api/run/until`) | POST | `{}` / `{index}` | JSON |
| `/api/undo`, `/api/redo` | POST | `{}` | JSON; `result.undone`/`redone`, `model`, `log` |
| `/api/reset`, `/api/domain/apply` | POST | `{}` / `{nx, ny, nz, voxel, threads}` | JSON |
| `/api/timeline/get` | POST | `{}` | JSON; `result.items[]`: `{index, state, runtime_status, snapshot_valid}`, `result.current` |
| `/api/timeline/restore` | POST | `{index}` | JSON; reject = `{ok:false, code:"no_valid_snapshot"}`（HTTP 200，不隐式重算） |
| `/api/preview/manifest` | GET | query `mode`, `face_limit` | JSON; `result.rev`, `result.meshes[]` (`mat_id`, …) |
| `/api/preview/geom` | GET | query `mat_id`, `rev`, `mode` | **binary** octet-stream |
| `/api/preview/stl` | GET | query `mat_id`, `rev`, `mode` | **binary** STL |
| `/api/preview/elements` | GET | query `max_points`, `channels`, `quality` | **binary**（动态 content-type） |
| `/api/slice` | GET | query `axis`, `index`, `kind` | JSON（`result.data_b64` 内嵌二进制） |
| `/api/render/gbuffer` | POST | render settings JSON | **binary** on success（支持 gzip），JSON error |
| `/api/material_colors` | POST | color overrides | JSON |
| `/api/mask/preview`, `/api/mask/preview_step` | GET | query (step/mask params) | JSON |
| `/api/upload/mask` | POST | mask payload | JSON |
| `/api/history/load` | POST | `{...}` | JSON |
| `/api/ui_state`, `/api/save` | POST | UI state payload | JSON |
| `/api/export` | POST | export options | JSON |
| `/api/export/download` | GET | query `file` | **binary** attachment |

Rules:

1. Any endpoint or response field a React component reads must be added to this table
   (in the same PR) before the client depends on it, and covered in
   `M2ApiContractTests`.
2. Methods are part of the contract: GET/POST membership above is enforced by the HTTP
   dispatchers (wrong-method requests fall through to a 404 JSON envelope).
3. Binary endpoints (`geom`, `stl`, `elements`, `gbuffer`, `export/download`) stay binary —
   React never parses them as JSON; `slice` is JSON with `data_b64`.
4. Cookie/session model stays as-is; WebSocket additions are new endpoints, not changes.

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
