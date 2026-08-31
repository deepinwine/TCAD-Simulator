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

Frozen core — one row per endpoint, verified against the HTTP dispatchers in
`tcad_simulator.py`. Unless a row explicitly says "裸 JSON", JSON responses are
`{"ok": bool, …}` envelopes (successful worker results under `result`). Binary endpoints
send raw bytes on success (JSON error envelopes on 4xx/5xx). Contract tests:
`tests/test_webui_cad_shell.py::M2ApiContractTests`
(behavioral) and `::M2ApiDocConsistencyTests` (doc vs dispatcher drift).

| Endpoint | Method | Request (minimal) | Response |
| --- | --- | --- | --- |
| `/api/health` | GET | — | JSON |
| `/api/init` | GET | — | JSON; `result`: `recipe`、`model`、`recipe_factories`、`materials`、`demo_recipes`、`recipes`、`ui_state` |
| `/api/status` | GET | — | JSON |
| `/api/log` | GET | — | JSON |
| `/api/history` | GET | — | JSON（历史清单） |
| `/api/process_config` | GET | — | JSON |
| `/api/load_autosave` | POST | `{}` | JSON |
| `/api/recipe/new` | POST | `{name, current_name?}` | JSON |
| `/api/recipe/save` | POST | `{name, note?, ui_state?}` | JSON |
| `/api/recipe/load` | POST | `{id, current_name?}` | JSON |
| `/api/recipe/delete` | POST | `{id}` | JSON |
| `/api/recipe/set_name` | POST | `{name}` | JSON |
| `/api/recipe/export` | GET | query `id` 或 `scope=current` | JSON（**裸 recipe blob**，无 `ok` 封套；含 `steps_full`） |
| `/api/recipe/import` | POST | `{recipe, autosave_current?, current_name?}` | JSON |
| `/api/recipe/add` | POST | `{name, insert_index?}` | JSON; `result`: step list |
| `/api/recipe/insert_steps` | POST | `{steps, insert_index?}` | JSON; `result`: step list |
| `/api/recipe/remove` | POST | `{index}` | JSON; `result`: step list |
| `/api/recipe/duplicate` | POST | `{index}` | JSON; `result`: step list |
| `/api/recipe/move` | POST | `{index, direction}` 或 `{index, to}` | JSON; `result`: step list |
| `/api/recipe/rename-step` | POST | `{index, instance_name (1–80 字符)}` | JSON; `result`: step |
| `/api/step/set` | POST | `{index, enabled?, params?, loop?, group?, no_autosave?}` | JSON; `result`: step、`statuses` 列表、`warnings?` |
| `/api/run/step` | POST | `{index}` | JSON；失败为平面结构化载荷（`step_index`、`instance_name`、`step_type`、`parameter_path`、`error`、`error_type`、`suggestion`、`rolled_back`） |
| `/api/run/all` | POST | `{}` | JSON |
| `/api/run/to`（dispatcher 别名 `/api/run/until`） | POST | `{index}` | JSON |
| `/api/undo` | POST | `{}` | JSON; `result.undone`、`model`、`log` |
| `/api/redo` | POST | `{}` | JSON; `result.redone`、`model`、`log` |
| `/api/reset` | POST | `{}` | JSON |
| `/api/domain/apply` | POST | `{nx, ny, nz, voxel, threads}` | JSON |
| `/api/timeline/get` | POST | `{}` | JSON; `result.items[]`：`{index, state, runtime_status, snapshot_valid}`、`result.current` |
| `/api/timeline/restore` | POST | `{index}` | JSON；拒绝 = `{ok:false, code:"no_valid_snapshot"}`（HTTP 200，不隐式重算） |
| `/api/preview/manifest` | GET | query `mode`、`face_limit` | JSON; `result.rev`、`result.meshes[]`（`mat_id`…） |
| `/api/preview/geom` | GET | query `mat_id`、`rev`、`mode` | **binary** `application/octet-stream` |
| `/api/preview/stl` | GET | query `mat_id`、`rev`、`mode` | **binary** STL（`application/sla`） |
| `/api/preview/elements` | GET | query `max_points`、`channels`、`quality` | **binary**（动态 content-type） |
| `/api/slice` | GET | query `axis`、`index`、`kind` | JSON（`result.data_b64` 内嵌二进制） |
| `/api/render/gbuffer` | POST | render 设置 JSON | **binary**（支持 gzip），JSON error |
| `/api/material_colors` | POST | `{action, mode?, …}` | JSON |
| `/api/mask/preview` | GET | query `file`（已上传掩膜文件名） | **binary** `image/*`（`.npy` → `image/png`，其他支持格式保留源 MIME），JSON error |
| `/api/mask/preview_step` | GET | query `step_index`（或 `index`） | **binary**（默认 `image/png`），JSON error |
| `/api/upload/mask` | POST | **multipart/form-data**：`file` 字段 + query `step_index` | JSON；顶层 `path` 为保存后完整路径（含哈希文件名），`result` 为嵌套的 `set_step` 封套，基名位于 `result.result.params.mask_name` |
| `/api/history/load` | POST | `{id, current_name?}` | JSON |
| `/api/ui_state` | POST | `{recipe_id, ui_state}` | JSON |
| `/api/save` | POST | `{}` | JSON |
| `/api/export` | POST | 导出选项 JSON | JSON |
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

## Frontend Structure (delivered in M2)

```text
frontend/
├── package.json / vite.config.ts / tsconfig.json   # base=/studio/, dev proxy /api -> 8765
└── src/
    ├── App.tsx                 # bootstrap + composition（可注入 viewerRuntimeFactory 测试缝）
    ├── components/             # Toolbar, ProcessFlowPane, ParameterPanel, TimelineBar, ErrorNotice
    ├── viewer/                 # ThreeViewer + fitCamera/meshLoader 纯函数 + viewerRuntime(Three.js)
    ├── api/                    # client(TcadApiError) + schemas + types（冻结契约的 TS 边界）
    ├── state/                  # appReducer(纯) + AppStateContext(会话动作/变更 gate)
    └── styles.css
```

React is a parallel client against the existing backend; the legacy WebUI stays until
React passes feature parity and regression tests (M5). Never delete the old WebUI early.
The built bundle is served same-origin at `/studio/` by the Python WebUI (ADR-012);
Three.js visualization is browser-local — camera/view operations never issue API
requests, only `preview/manifest` + `preview/stl` on model revision changes.

## Migration Strategy — Strangler, Never Big Bang

Preferred sequence (details and status in `docs/ROADMAP_PROCESS_CAD.md`):

1. **M1** Stabilize the existing Process CAD workflow and lock it with golden regression
   tests (five named flows).
2. **M2** React/TS/Vite shell as a parallel frontend (`frontend/`) — delivered: dense
   three-pane shell, frozen-API typed client, run/timeline integration, minimal real
   mesh load + orbit/pan/zoom in the Three.js viewer.
3. **M3** Three.js viewer completion inside React (perspective/orthographic, X/Y/Z
   clipping, material display control, selection, measurement; six views + ISO and
   orbit/pan/zoom already delivered in M2).
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
