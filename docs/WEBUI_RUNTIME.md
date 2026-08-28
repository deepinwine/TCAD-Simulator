# WebUI Runtime

The WebUI is built into `tcad_simulator.py`. It provides browser access to recipe editing, simulation, preview, history, library storage, export, mask design, Admin configuration, and optional Agent workflows.

## Main Components

- `WebUIServerManager`: starts/stops the user WebUI HTTP server.
- `_WebUIRequestHandler`: serves static assets and API endpoints.
- `WebUISession`: maps browser sessions to worker state, storage, and history.
- `_webui_worker_main()`: owns per-session model state and handles RPC commands.
- `AdminServerManager`: starts/stops the Admin server for material/process/library configuration.
- `_AdminRequestHandler`: handles Admin UI and configuration routes.

## Request Flow

```text
Browser
    -> HTTP request/API command
    -> _WebUIRequestHandler
    -> WebUISession
    -> worker message {cmd, payload, rid}
    -> ProcessModel/recipe/library/export/agent action
    -> JSON or binary response
```

Where supported, sessions use isolated worker processes. Fallback modes keep the same command contract while reducing isolation.

## Worker State

A worker typically owns:

- `MaterialDatabase` and `ProcessModel`.
- current recipe and serialized recipe history.
- autosave and undo/snapshot cache.
- preview cache, render settings, and exported assets.
- library profile and encrypted library access.
- optional literature/Agent state and LLM provider config.

Large snapshots can be spilled to disk through the `_tcad_snapshot_*` helpers so WebUI sessions do not keep every array in process memory.

## Storage

By default, runtime state is stored under `TCAD_Web_Data/` next to the launch root. This can be overridden:

```bash
TCAD_WEBUI_STORAGE_ROOT=/path/to/storage
TCAD_STORAGE_ROOT=/path/to/storage
TCAD_LAUNCH_ROOT=/path/to/app/root
```

Do not commit `TCAD_Web_Data/`. It can contain encrypted libraries, master keys, Admin config, private recipes, exports, and literature databases.

## Assets And Downloaded JavaScript

The WebUI may need browser-side JavaScript assets such as Three.js helpers. Runtime-downloaded copies like `three.js`, `three.min.js`, `STLLoader.js`, and `OrbitControls.js` are ignored by `.gitignore`.

`tools/html_vendor/` is an offline documentation-site vendor cache for generated HTML docs. It is also ignored by default because it is large and reproducible.

## Rendering And Export

The WebUI supports both browser-side WebGL-style preview and host-assisted rendering paths. The host side can produce:

- preview manifests and gbuffer-like render data.
- cross-section and doping slices.
- STL/TCAD geometry exports.
- image frame sequences.
- optional MP4 through `imageio-ffmpeg`, system `ffmpeg`, or `TCAD_FFMPEG`.

Rendering code should consume `ProcessModel` surfaces, meshes, and metrology outputs rather than duplicating process-state logic.

## Viewer Backend Status

The 3D viewer prefers a WebGL2 context. WebGL capability probing uses a temporary canvas; the real viewer canvas is passed to `THREE.WebGLRenderer` exactly once. A browser console message such as `Canvas has an existing context of a different type` indicates a regression of this contract.

The status chip on the viewer reports the actually initialized backend, not just the probe result:

- `WebGL2` (or `WebGL1`): the renderer initialized successfully on the real canvas. Standard views, perspective/orthographic cameras, X/Y/Z clipping, and material display toggles are available.
- `Host Render · <reason>`: visible fallback with the normalized failure reason. WebGL-only features such as the multi-axis cutaway are disabled rather than silently dropped.

Camera, projection, clipping, and material visibility interactions are browser-local: they must not trigger worker recomputes, `preview/manifest` refetches, or geometry re-downloads. Only lightweight UI state is persisted (for example `ui_state.clipPlanes3d` and per-material display modes under `ui_state.materialDisplaySolid`/`materialDisplayFast`). The clipping status element (role `status`) reads `未启用裁剪` when idle and `X+Y+Z 组合裁剪 · 多轴不封口` when several axes are active.

## Manual Viewer Smoke Check

Start an isolated WebUI with a throwaway storage root:

```bash
TCAD_VIEW_DIR=$(mktemp -d /tmp/tcad-viewer-manual.XXXXXX)
TCAD_WEBUI_STORAGE="$TCAD_VIEW_DIR" TCAD_SKIP_QT=1 MPLBACKEND=Agg \
  python3 -c 'import os, threading; from pathlib import Path; from tcad_simulator import WebUIServerManager; manager = WebUIServerManager(host="127.0.0.1", port=8766, storage_root=Path(os.environ["TCAD_WEBUI_STORAGE"])); manager.start(); print(manager.url, flush=True); threading.Event().wait()'
```

The manager prints the actual URL; it moves to the next free port when 8766 is taken.

Verify in a real desktop browser (at least 1280 px wide):

1. No `Canvas has an existing context of a different type` console error, and the status chip shows `WebGL2`.
2. ISO/TOP/BOTTOM/FRONT/BACK/LEFT/RIGHT views each reposition the camera deterministically and keep the model centered and fully visible.
3. Switching perspective/orthographic keeps the model at a comparable visible scale; it must not jump out of the viewport.
4. X/Y/Z clipping can be enabled together and inverted independently; the clipping status reflects the combination, and the cut corner moves when an axis is inverted.
5. Toggling material visibility cycles solid → translucent → hidden without new `preview/manifest` requests; the session `preview/` cache keeps its existing `.geom` files and mtimes.
