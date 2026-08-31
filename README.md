# TCAD Process Simulator

<p align="center">
  <img src="TCAD_Demo.png" alt="TCAD Process Simulator WebUI demo" width="100%">
</p>

<p align="center">
  <strong>Process-focused TCAD-like simulator for semiconductor fabrication workflows.</strong><br>
  <strong>面向半导体制程流程的 TCAD-like 工艺仿真平台。</strong>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg">
  <img alt="GUI" src="https://img.shields.io/badge/Desktop-PyQt5-2b6cb0.svg">
  <img alt="WebUI" src="https://img.shields.io/badge/WebUI-Multi--user-0b7285.svg">
  <img alt="TCAD" src="https://img.shields.io/badge/TCAD-Process%20Simulation-6f42c1.svg">
</p>

`tcad_simulator.py` is the canonical single-file application. It combines process recipe editing, voxel-based wafer modeling, lithography/mask workflows, deposition, etch, CMP, implantation, annealing, oxidation/nitridation, metrology, 3D/2D visualization, export tools, a desktop GUI, a multi-user WebUI, and optional LLM-assisted recipe design.

`tcad_simulator.py` 是项目主入口和权威源码。它把工艺 recipe 编辑、体素晶圆模型、光刻/掩膜流程、沉积、刻蚀、CMP、离子注入、退火、氧化/氮化、测量、3D/2D 可视化、导出工具、桌面 GUI、多用户 WebUI 和可选 LLM recipe 辅助集成在一个单文件应用中。

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Process Model](#process-model)
- [WebUI Runtime](#webui-runtime)
- [Installation](#installation)
- [Run](#run)
- [Documentation](#documentation)
- [Developer Tooling](#developer-tooling)
- [Runtime Data](#runtime-data)
- [License](#license)

## Capabilities

| Area | Features |
| --- | --- |
| Process TCAD workflow | Wafer initialization, lithography, deposition, selective epitaxy, etch, CMP, implantation, anneal, oxidation/nitridation, surface reactions |
| Voxel process kernel | Configurable `NX × NY × NZ` domain, nanometer voxel size, material grid, height map, mask state, doping/defect fields, snapshots |
| Lithography and mask | Spin resist, exposure, PEB, develop, image/NumPy/GDSII masks, mask designer, DRC-style metrics, process-window probes |
| Materials and recipes | Built-in material database, process parameters, Admin overrides, recipe JSON migration, presets, history, loop workflows |
| Visualization | 3D stack preview, material components, cross-sections, doping/exposure heatmaps, WebGL/host-assisted render paths |
| Metrology and export | CD/feature metrics, material inventory, interfaces, CSV, STL, TCAD geometry, PNG frame sequences, optional MP4 video |
| Desktop and WebUI | PyQt5 desktop application, multi-user WebUI, isolated sessions where supported, Admin UI, encrypted library storage |
| Process CAD Shell | Three-pane WebUI workspace (Process Flow / Parameters / 3D Viewer), step drag-and-drop and rename, snapshot timeline with Previous/Next, undo/redo, structured step errors |
| Knowledge and Agent | Optional PDF/literature ingestion, local retrieval, process mapping, physics audit, skills, LLM-assisted recipe drafting |

## Architecture

```mermaid
flowchart TD
    subgraph Interfaces[User Interfaces]
        Desktop[PyQt5 desktop GUI]
        Browser[Multi-user browser WebUI]
        CLI[Headless CLI and selftests]
        Admin[Admin UI]
    end

    subgraph Orchestration[Application Orchestration]
        Controller[SimulatorController]
        WebServer[WebUIServerManager and HTTP API]
        Session[WebUISession]
        Worker[Worker runtime]
        Headless[simulate_headless]
        RecipeIO[Recipe JSON migration and history]
    end

    subgraph RecipeLayer[Recipe and Step Layer]
        Recipe[Process recipe]
        Factories[PROCESS_STEP_FACTORIES]
        Steps[ProcessStep subclasses]
        Params[ParameterSpec UI schema]
    end

    subgraph ProcessKernel[TCAD Process Kernel]
        Model[ProcessModel]
        Materials[MaterialDatabase]
        Grid[Voxel material grid]
        Height[Height map and open mask]
        Fields[Doping, dopant species, defects, exposure fields]
        Snapshots[Snapshot, cache, undo, spill-to-disk]
    end

    subgraph PhysicsDomains[Process Physics Domains]
        Litho[Lithography and resist]
        Dep[Deposition]
        Epi[Selective epitaxy]
        Etch[Etch]
        CMP[CMP]
        Implant[Implantation]
        Anneal[Anneal and diffusion]
        Ox[Oxidation, nitridation, surface reactions]
    end

    subgraph Analysis[Analysis and Output]
        Geometry[Level-set, marching cubes, surface patches]
        Preview[3D stack, slices, heatmaps]
        Metrology[CD, interfaces, inventory, component metrics]
        Export[CSV, STL, TCAD geometry, PNG frames, MP4]
    end

    subgraph Knowledge[Optional Knowledge and Agent]
        Docs[PDF and text ingestion]
        Retrieval[Local retrieval]
        Mapper[ProcessMapper]
        Auditor[PhysicsAuditor]
        Agent[LLM-assisted recipe drafting]
    end

    subgraph Storage[Runtime Storage]
        WebData[TCAD_Web_Data]
        Static[_static WebUI assets]
        Library[Encrypted library]
        Literature[Local literature DB]
    end

    Desktop --> Controller
    Browser --> WebServer
    Admin --> WebServer
    WebServer --> Session --> Worker
    CLI --> Headless
    Controller --> RecipeIO
    Worker --> RecipeIO
    Headless --> Recipe
    RecipeIO --> Recipe
    Recipe --> Factories --> Steps --> Model
    Params --> Steps
    Model --> Materials
    Model --> Grid
    Model --> Height
    Model --> Fields
    Model --> Snapshots
    Model --> Litho
    Model --> Dep
    Model --> Epi
    Model --> Etch
    Model --> CMP
    Model --> Implant
    Model --> Anneal
    Model --> Ox
    Grid --> Geometry --> Preview
    Fields --> Preview
    Grid --> Metrology --> Export
    Geometry --> Export
    Worker --> WebData
    WebData --> Static
    WebData --> Library
    WebData --> Literature
    Docs --> Retrieval --> Mapper --> Agent --> Recipe
    Auditor --> Recipe
    Retrieval --> Auditor
```

`ProcessModel` is the central state boundary. GUI, WebUI, headless execution, recipe import/export, and optional Agent proposals all converge through the same `ProcessStep.execute(model)` protocol.

`ProcessModel` 是核心状态边界。桌面 GUI、WebUI、headless 执行、recipe 导入导出和可选 Agent proposal 最终都会通过同一个 `ProcessStep.execute(model)` 协议进入工艺内核。

## Process Model

```mermaid
flowchart LR
    Start([Recipe start]) --> Init[Initialize Wafer]
    Init --> Spin[Spin Resist]
    Spin --> Exposure[Mask Exposure]
    Exposure --> PEB[Post-Exposure Bake]
    PEB --> Develop[Resist Develop]
    Develop --> Etch[Etch]
    Etch --> Deposition[Deposition]
    Deposition --> Epitaxy[Selective Epitaxy]
    Epitaxy --> CMP[CMP]
    CMP --> Implant[Implantation]
    Implant --> Anneal[Anneal]
    Anneal --> OxNit[Oxidation / Nitridation]
    OxNit --> Surface[Surface Reaction]
    Surface --> Metro[Metrology]
    Metro --> Export[Export]
    Export --> End([Recipe complete])

    subgraph LithographyControls[Lithography controls]
        MaskInput[Image, NumPy, or GDSII mask]
        MaskMetrics[Mask metrics and DRC]
        Aerial[Aerial image and exposure dose]
        Resist[Resist chemistry and tone]
    end

    subgraph MaterialControls[Material and process controls]
        MatDB[MaterialDatabase]
        Selectivity[Selectivity and etch rates]
        Conformality[Conformality, accessibility, feature loading]
        Dopants[Dopant species, dose, energy, tilt]
        Thermal[Temperature, time, ambient]
    end

    MaskInput --> Exposure
    Exposure --> Aerial --> Resist --> Develop
    MaskMetrics --> Exposure
    MatDB --> Init
    MatDB --> Deposition
    MatDB --> Epitaxy
    MatDB --> Etch
    Selectivity --> Etch
    Conformality --> Deposition
    Conformality --> Epitaxy
    Dopants --> Implant
    Dopants --> Deposition
    Thermal --> Anneal
    Thermal --> OxNit
    Thermal --> Surface
```

```mermaid
flowchart TD
    subgraph State[Mutable simulator state]
        Grid[3D material-id voxel grid]
        Height[Height map]
        OpenMask[Open-mask and resist state]
        Doping[Doping concentration field]
        Species[Dopant species fields]
        Defects[Defect and damage fields]
        ExposureField[Exposure and resist chemistry fields]
        Logs[Run log and snapshots]
    end

    subgraph Numeric[Numeric kernels]
        EDT[Euclidean distance transform]
        Propagation[Binary and weighted propagation distance]
        LevelSet[Signed distance and level-set evolution]
        Normals[Surface normals]
        FFT[FFT blur and lithography approximations]
        Compression[Voxel compression and snapshot spill]
    end

    subgraph GeometryPath[Geometry reconstruction]
        Mesh[Marching cubes meshes]
        Patches[Height-map surface patches]
        Components[Material component summaries]
        BRep[B-Rep readiness and smooth surfaces]
    end

    subgraph Observables[User-visible outputs]
        Stack3D[3D stack preview]
        Slices[Cross-sections and heatmaps]
        Metrics[CD, inventory, interfaces, component diameters]
        Reports[Run reports]
        Files[CSV, STL, TCAD geom, PNG, MP4]
    end

    Grid --> Height
    Grid --> OpenMask
    Grid --> EDT
    Grid --> Propagation
    Grid --> LevelSet
    Doping --> Slices
    Species --> Slices
    Defects --> Slices
    ExposureField --> FFT
    LevelSet --> Normals
    LevelSet --> Mesh
    Height --> Patches
    Grid --> Components
    Mesh --> BRep
    Mesh --> Stack3D
    Patches --> Stack3D
    Components --> Metrics
    Grid --> Metrics
    Slices --> Reports
    Metrics --> Reports
    Stack3D --> Files
    Reports --> Files
    Logs --> Reports
    Compression --> Logs
```

The numerical model is physics-inspired and designed for research, teaching, and process exploration. It is not a calibrated commercial TCAD sign-off tool.

该数值模型是 physics-inspired 的研究/教学/探索工具，不是经过工业标定的商业 TCAD sign-off 替代品。除非已经用真实工艺数据验证，否则生成的结构、掺杂场和 metrology 数值都应视为探索性结果。

## WebUI Runtime

```mermaid
sequenceDiagram
    participant Browser
    participant HTTP as WebUIRequestHandler
    participant Session as WebUISession
    participant Worker as Worker Runtime
    participant Recipe as Recipe/History
    participant Model as ProcessModel
    participant Render as Preview/Export
    participant Agent as Optional Agent
    participant Store as TCAD_Web_Data

    Browser->>HTTP: GET / and /static assets
    HTTP->>Store: ensure _static assets
    HTTP-->>Browser: HTML, CSS, JS, Three.js
    Browser->>HTTP: POST API command
    HTTP->>Session: resolve cookie and client session
    Session->>Worker: RPC {cmd, payload, rid}
    Worker->>Recipe: load, edit, migrate, autosave
    Recipe->>Model: ProcessStep.execute(model)
    Worker->>Model: run step, run all, reset, undo
    Worker->>Render: preview manifest, gbuffer, slice, export
    Worker->>Agent: optional recipe proposal and audit
    Worker->>Store: history, cache, preview, exports, library
    Model-->>Worker: state, metrics, geometry
    Render-->>Worker: images, meshes, files
    Agent-->>Worker: candidate recipe or critique
    Worker-->>Session: {ok, result, rid}
    Session-->>HTTP: JSON / binary response
    HTTP-->>Browser: WebUI update
```

```mermaid
flowchart TD
    subgraph Source[Repository source]
        App[tcad_simulator.py]
        Readme[README and TCAD_Demo.png]
        Docs[docs markdown]
        Tools[tools]
        Scripts[run and split scripts]
    end

    subgraph Generated[Generated developer outputs]
        Html[docs_html offline site]
        Vendor[tools/html_vendor docsite libraries]
        Split[tcad_simulator_split package view]
        SplitHtml[tcad_simulator_split/docs_html]
        Reports[SPLIT_REPORT and VERIFY_REPORT]
    end

    subgraph Runtime[Local runtime data]
        WebData[TCAD_Web_Data]
        Static[_static WebUI JS/CSS assets]
        SessionData[session autosave, logs, cache]
        Exports[exports and preview cache]
        Library[encrypted library and Admin config]
        LitDB[local literature DB]
    end

    subgraph Tooling[Automation]
        Docsite[tools/docsite.py]
        VendorFetch[tools/vendor_docsite_libs.py]
        Splitter[tools/split_tcad.py]
        WebAssetFetch[WebUI Three.js downloader]
    end

    Docs --> Docsite --> Html
    Docsite --> VendorFetch --> Vendor
    App --> Splitter --> Split
    Splitter --> Reports
    Split --> SplitHtml
    App --> WebData
    WebData --> Static
    WebData --> SessionData
    WebData --> Exports
    WebData --> Library
    WebData --> LitDB
    WebAssetFetch --> Static
    Scripts --> App
    Scripts --> Splitter

    classDef generated fill:#eef6ff,stroke:#2b6cb0,color:#17324d;
    classDef local fill:#fff7e6,stroke:#b7791f,color:#4a2f00;
    class Html,Vendor,Split,SplitHtml,Reports generated;
    class WebData,Static,SessionData,Exports,Library,LitDB local;
```

WebUI JavaScript assets are prepared automatically under `TCAD_Web_Data/_static/`. The downloader uses local reuse first, then region-friendly CDN fallbacks, then npm/npmmirror tarball extraction for Three.js assets.

WebUI 的 JavaScript 资源会自动准备到 `TCAD_Web_Data/_static/`。下载逻辑会先复用本地已有文件，再按地区友好的 CDN fallback 下载，最后从 npm/npmmirror tarball 中提取 Three.js 资源。

Useful asset environment variables:

```bash
TCAD_WEBUI_CDN_REGION=cn
TCAD_WEBUI_ASSET_BASE=https://your-mirror.example/three@0.145.0
TCAD_WEBUI_THREE_TARBALL=https://your-mirror.example/three-0.145.0.tgz
TCAD_WEBUI_ASSET_TIMEOUT=8
```

## Repository Layout

```text
.
├── tcad_simulator.py          # Canonical single-file simulator
├── TCAD_Demo.png              # README screenshot
├── README.md                  # Project overview
├── docs/                      # Source-focused architecture and algorithm docs
├── requirements.txt           # Recommended dependencies
├── run_tcad_macos.sh          # macOS launcher
├── run_tcad_linux.sh          # Linux launcher
├── run_tcad.ps1               # Windows PowerShell launcher
├── run_tcad.bat               # Windows CMD launcher
├── split_tcad.sh              # macOS/Unix developer split helper
├── split_tcad_linux.sh        # Linux developer split helper
├── split_tcad.ps1             # Windows PowerShell split helper
├── split_tcad.bat             # Windows CMD split helper
├── tools/                     # Documentation/split tooling
├── .github/                   # Issue templates and smoke workflow
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── CONTRIBUTING.md
├── SECURITY.md
└── CODE_OF_CONDUCT.md
```

Generated and local runtime paths such as `TCAD_Web_Data/`, `docs_html/`, `tools/html_vendor/`, `tcad_simulator_split/`, and `tcad_simulator_split.zip` are ignored by default.

`TCAD_Web_Data/`、`docs_html/`、`tools/html_vendor/`、`tcad_simulator_split/` 和 `tcad_simulator_split.zip` 默认作为本地运行/生成产物忽略。

## Installation

Python 3.10 or newer is recommended.

推荐使用 Python 3.10 或更新版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For a smaller core runtime:

如果只需要较小的核心运行栈：

```bash
python -m pip install numpy matplotlib PyQt5 scipy scikit-image cryptography
```

Optional feature dependencies:

- GDSII import/export: `gdstk` or `gdspy`
- PDF literature ingestion: `pdfminer.six`, `PyPDF2`, or optional `PyMuPDF`
- Image/mask helpers: `Pillow`
- MP4 export: `imageio-ffmpeg` or system `ffmpeg`
- Numeric acceleration: `numba`

## Process CAD Shell

The WebUI provides a fixed three-pane CAD workspace for process engineers: **Process Flow** (step list with drag-and-drop ordering, double-click rename, per-step execution status), **Parameters** (editor driven by `ProcessStep.parameter_specs()`, autosaved with dirty-marking of the current and later steps), and the **3D Viewer** (WebGL2 with seven standard views, perspective/orthographic cameras, independent X/Y/Z clipping planes, and MaterialVisual-driven display control). A timeline bar under the workspace supports Previous/Next and slider review of valid step snapshots without recomputation; undo/redo restores model state together with runtime statuses, step errors, and the timeline position.

Three demo recipes are built in: **Basic Trench**, **Spacer Formation**, and **Bonding + Thinning** (select them under *Process Recipe → Demo Recipes*). Editing a step invalidates only that step and everything after it; earlier snapshots stay reviewable. Failed steps roll back automatically and surface structured errors (step index/type, parameter path, suggestion, rollback status). Secondary tools (Domain Settings, History, Export, AI Agent) stay in the collapsible left drawer.

WebUI 提供固定三栏的 CAD 工作面：**Process Flow**（拖拽排序、双击重命名、逐步执行状态）、**Parameters**（由 `ProcessStep.parameter_specs()` 驱动、自动保存并使后续步骤 Dirty）和 **3D Viewer**（WebGL2、七个标准视图、透视/正交相机、X/Y/Z 独立裁剪、MaterialVisual 材质控制）。底部时间线支持 Previous/Next 与滑杆回看有效快照且不触发重算；撤销/重做会连同运行状态、步骤错误和时间线位置一起原子恢复。

内置 **Basic Trench**、**Spacer Formation**、**Bonding + Thinning** 三个示例配方（在 *Process Recipe → Demo Recipes* 中加载）。编辑步骤只使当前及后续步骤失效，前序快照保持可回看；失败步骤自动回滚并展示结构化错误（步骤索引/类型、参数路径、建议操作、回滚状态）。Domain Settings、History、Export、AI Agent 等次级工具保留在左侧可折叠抽屉中。

## Run

Desktop application:

桌面应用：

```bash
python tcad_simulator.py
```

Cross-platform launchers:

跨平台启动脚本：

```bash
# macOS
./run_tcad_macos.sh

# Linux
./run_tcad_linux.sh
```

```powershell
# Windows PowerShell
.\run_tcad.ps1
```

```bat
:: Windows CMD
run_tcad.bat
```

Headless smoke test:

Headless 快速自测：

```bash
TCAD_SKIP_QT=1 MPLBACKEND=Agg python tcad_simulator.py --mask-prompt-selftest --n 3 --res 128
```

Other selftest entry points:

其他自测入口：

```bash
python tcad_simulator.py --webui-selftest --skip-video
python tcad_simulator.py --saqp-selftest --skip-ref
python tcad_simulator.py --recipe-io-selftest
```

Some regression selftests require local fixtures such as `SAQP_Thinking_Flow.json`, `tcad_simulator_2.19.py`, or `LLM_Test_Config.json`. Missing fixtures can make those tests fail even when the simulator itself runs correctly.

部分 regression selftest 需要本地 fixture。缺少这些 fixture 时测试失败，不一定表示 simulator 无法运行。

### React Studio (M2 + M3 parallel client)

The React + TypeScript + Vite client lives in `frontend/` and talks to the same
WebUI backend through the frozen M2 Compatibility API. The legacy WebUI at `/` is
unchanged; the React client is served same-origin at `/studio/`.

The 3D viewer (M3) supports perspective/orthographic projection toggle, X/Y/Z
clipping planes with per-axis sliders, per-material visibility/opacity control,
mesh picking with hit info, and two-point distance measurement — all
browser-local (camera/clip/material/pick operations issue zero API requests).
After a run fails with a network error, a one-click 重新同步 reconciles the UI
with the server-authoritative timeline (the server may have finished the run).

React + TypeScript + Vite 客户端位于 `frontend/`，通过冻结的 M2 Compatibility API
访问同一个 WebUI 后端。旧 WebUI（`/`）保持不变；React 客户端在同源路径 `/studio/` 提供。

3D 查看器（M3）支持透视/正交投影切换、X/Y/Z 独立裁剪平面（逐轴滑杆）、材料级
可见性/透明度控制、网格点选信息与两点距离测量——全部为浏览器本地能力（相机、
裁剪、材料、拾取操作不产生任何 API 请求）。运行因网络错误失败后，一键
「重新同步」即可按服务端权威 timeline 对账（服务端可能已完成运行）。

```bash
# 后端（无桌面环境的无头启动；WebUI 以守护线程提供，进程需保持运行。
# 有 Qt 桌面环境时，从桌面应用内启动 WebUI 亦可。）
TCAD_SKIP_QT=1 MPLBACKEND=Agg python3 -c \
  "import time; from tcad_simulator import WebUIServerManager as W; W(host='127.0.0.1', port=8765).start(); time.sleep(3600)"

# React 开发服务器（开发期热更新，代理 /api 到后端）
cd frontend
npm ci
npm run dev

# 同源生产构建（构建产物由后端在 /studio/ 直接提供）
npm run build
# 访问 http://127.0.0.1:8765/studio/
```

## Documentation

Formal source-focused documentation lives in [`docs/`](docs/):

正式文档位于 [`docs/`](docs/)，重点解释 `tcad_simulator.py` 的架构、算法和维护边界：

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/ALGORITHMS.md`](docs/ALGORITHMS.md)
- [`docs/WEBUI_RUNTIME.md`](docs/WEBUI_RUNTIME.md)
- [`docs/MASK_LITHOGRAPHY.md`](docs/MASK_LITHOGRAPHY.md)
- [`docs/AGENT_KNOWLEDGE.md`](docs/AGENT_KNOWLEDGE.md)
- [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md)

Build offline HTML docs:

生成离线 HTML 文档：

```bash
python3 tools/docsite.py --docs-dir docs --out-dir docs_html
```

If `tools/html_vendor/` is missing Mermaid, Marked, MathJax, or Highlight.js, the docsite builder downloads the required vendor assets automatically. `docs_html/` and `tools/html_vendor/` are reproducible generated outputs and are ignored by default.

如果 `tools/html_vendor/` 缺少 Mermaid、Marked、MathJax 或 Highlight.js，HTML 文档构建器会自动下载依赖。`docs_html/` 和 `tools/html_vendor/` 是可再生成产物，默认被 Git 忽略。

## Developer Tooling

Optional split tooling generates a package-style source view, reports, and generated docs:

可选 split 工具会生成 package-style 源码视图、报告和开发文档：

```bash
./split_tcad.sh
./split_tcad_linux.sh
```

```powershell
.\split_tcad.ps1
```

```bat
split_tcad.bat
```

Generated outputs include `tcad_simulator_split/docs/`, `tcad_simulator_split/docs_html/`, `SPLIT_REPORT.json`, and `VERIFY_REPORT.json`. They are for developer inspection and are ignored by default.

生成物包括 `tcad_simulator_split/docs/`、`tcad_simulator_split/docs_html/`、`SPLIT_REPORT.json` 和 `VERIFY_REPORT.json`，用于开发检查，默认被 Git 忽略。

A reproducible Process CAD baseline runs five named flows headless on a cubic 640 nm physical domain and records per-flow wall time, best-effort process RSS (see the `peak_rss_scope` field; falls back to `psutil` or `null` on Windows), occupied voxels, material-semantic checks, and preview-mesh triangle counts. WebUI, Golden tests, and the baseline share the public `load_demo_flows(material_db)` registry. `--grid` controls the resolution on all three axes, so `--grid 128` is a true 128³ run with 5 nm voxels:

```bash
TCAD_SKIP_QT=1 MPLBACKEND=Agg python3 tools/run_process_cad_baseline.py --grid 128 --output /tmp/tcad-cad-baseline.json
```

Exit code 0 and `"ok": true` mean all five flows completed and passed their structural checks; the JSON is suitable for archiving and cross-revision comparison.

可复现的 Process CAD 基准会在 640 nm 立方物理域中以 headless 方式运行 5 套具名流程。WebUI、Golden 测试和基准共用公开的 `load_demo_flows(material_db)` 注册表。`--grid` 同时控制三轴分辨率，因此 `--grid 128` 表示真正的 128³ 网格和 5 nm 体素。报告包含每套流程的耗时、尽力而为的进程内存（语义见 `peak_rss_scope` 字段；Windows 上回退到 `psutil` 或置空）、占用体素数、材料语义检查和预览网格面数；退出码为 0 且 `"ok": true` 表示 5 套流程均已完成并通过结构检查。

## Runtime Data

The simulator creates local runtime and generated files while running the desktop GUI, WebUI, documentation builder, and developer split tools. These files are intentionally ignored by Git because they can be large, machine-specific, or private.

仿真器在运行桌面 GUI、WebUI、文档构建器和开发拆分工具时会生成本地运行数据和构建产物。这些文件可能很大、只适用于当前机器，或包含私有信息，因此默认被 Git 忽略。

| Path | Purpose |
| --- | --- |
| `TCAD_Web_Data/` | WebUI sessions, static assets, autosaves, logs, preview cache, exports, encrypted library data, Admin config, and local keys |
| `docs_html/` | Generated offline HTML version of `docs/` |
| `tools/html_vendor/` | Downloaded JavaScript/CSS vendor cache for HTML documentation |
| `tcad_simulator_split/` | Generated package-style source view and developer reports |
| `tcad_simulator_split.zip` | Generated split archive |
| `TCAD_Selftest_Output_*/` | Selftest artifacts and exported regression data |

Do not place API keys, private process recipes, proprietary datasets, private papers, or internal experiment outputs in the repository.

不要把 API key、私有工艺 recipe、专有数据集、未公开论文或内部实验输出放进仓库。

## License

This project is released under the MIT License. See [`LICENSE`](LICENSE).

本项目代码采用 MIT License 发布，见 [`LICENSE`](LICENSE)。

Third-party dependencies remain under their own licenses. In particular, PyQt5 is distributed under GPL/commercial licensing, and optional PyMuPDF/MuPDF is distributed under AGPL/commercial licensing. This matters most when redistributing packaged binaries or commercial bundles. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for dependency license notes.

第三方依赖仍遵循各自许可证。尤其是 PyQt5 采用 GPL/commercial 许可，可选 PyMuPDF/MuPDF 采用 AGPL/commercial 许可；这主要影响二进制打包、商业捆绑或再分发场景。依赖许可证说明见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
