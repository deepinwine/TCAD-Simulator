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

## M6 — KLayout LayoutAdapter ✅（已交付）

`LayoutAdapter` abstraction; gdstk + optional KLayout for GDS/OASIS, hierarchy, booleans,
ROI; normalized mask geometry to lithography (ADR-016). Delivered on
`codex/m6-layout`: `layout/` package — normalized geometry types (nm polygons +
layer/datatype, pure ROI crop), gdstk-backed LayoutAdapter (GDS/OASIS read-write
round trips, hierarchy flattening, and/or/not/sub/xor booleans, even-odd
rasterization), the lithography bridge (`mask_from_layout` → boolean grid → .npy
→ ExposureStep params, verified end-to-end: GDS left-half mask → expose → develop
leaves resist only on the unexposed half), and an optional KLayout backend with
same semantics (implemented; real-environment verification pending per ADR-020
since the local wheel mirror 403s).

## M7 — ProcessBackend Interface ✅（已交付）

```text
ProcessBackend -> VoxelBackend -> ProcessModel   (behavior unchanged)
```

Delivered on `codex/m7-backend`: `process_backend/` package — the `ProcessBackend`
ABC (info/summary/execute_step/snapshot/restore/material_surfaces/grid/shutdown,
structured `ProcessBackendError`), `VoxelBackend` as a behavior-unchanged wrapper
over `ProcessModel` (parity test: identical voxel grids and surface meshes vs
direct `step.execute(model)` execution), and a registry (`create_backend('voxel')`)
where M8's viennaps sandbox will later register 'viennaps'. The capability model
with explicit fallbacks arrives with M9 as planned.

## M8 — ViennaPS Sandbox ✅（已验证）

Prototype only under `experiments/viennaps`; standalone validation (ADR-014).
Delivered and **validated on this machine**: the PyPI wheels' cross-module pybind11
ABI mismatch (import-time SIGSEGV) was diagnosed and resolved by building ViennaLS +
ViennaPS 4.7.0 from source (libomp, pybind11 3.0.x, Python 3.13) — steps recorded in
`experiments/viennaps/README.md`. The reference experiment (masked SF6O2 trench etch,
0.64µm field, 8nm grid, 30s process) runs end-to-end and emits a VTK surface mesh;
guard tests green; the backend registry still only contains 'voxel' (ADR-014/021).

## M9 — ViennaPSBackend ✅（首切片已交付）

Accurate Mode behind the backend interface; capability model with explicit fallbacks.
Delivered on `codex/m9-viennaps-backend`: `process_backend/viennaps_backend.py` —
`ViennaPSBackend` (`precision='geometry'`) registered as `'viennaps'`; supports
Initialize Wafer (flat Si substrate) and Etch(Dry→SF6O2, default fluxes);
`unsupported_step` raises with an explicit fallback suggestion to the voxel backend
(never silent substitution); snapshot/restore via level-set deepCopy; surface meshes
via in-memory `getSurfaceMesh`. First dual-engine calibration recorded (Basic-Trench
etch: voxel ≈300 nm vs geometry ≈6 nm at default fluxes — parameter mapping is the
next calibration step). Multi-material stacks / masked etch / more step types are the
M9 follow-up slices. Follow-up progress (2026-09-02): the calibration MEASUREMENT was
corrected (top-surface descent, not mesh z-range); flux-term mapping was tested and
found NOT to be the rate lever (300 vs default ≈ identical ≈5nm/30s — rate is
dominated by Ions.meanEnergy / A_ie terms); the ineffective override was reverted and
the mapping seam documented in-code. Remaining: per-term calibration against the
voxel baseline, masked etch via M6 vector masks, multi-material stacks.

## M10 — GeometryScene / VTK Bridge

Unified voxel + ViennaPS output → GeometryScene → VTK → Three.js (ADR-015).

## M11 — Hybrid Fast/Accurate

Per-process mode selection (e.g. Deposit FAST, HAR Etch ACCURATE, ALD ACCURATE,
Fill/CMP/Bonding FAST).

## M12 — Desktop Packaging ✅（无 Qt 路线已交付）

macOS / Windows application packaging (license review for Qt/PyQt5 implications first).
License review completed (ADR-022): PyQt5 GPL conflicts with MIT → the packaging goes
**headless** (`tcad_studio.py` launcher + `WebUIServerManager` + React frontend +
system browser). PyInstaller spec (`tcad_studio.spec`) excludes all Qt/PySide/tkinter;
React build output embedded as static data. No Qt dependency in the packaged binary.

## M13 — Geometry Bridge (2026-09-02)

**Implemented**: `geometry_scene/bridge.py` — Voxel↔GeometryScene↔ViennaPS 三条 conversion path + `docs/GEOMETRY_BRIDGE.md` 语义约定（nm canonical、+Z up、MaterialDatabase ID）。
**Integrated**: `HybridBackend` 使用 GeometryScene 作为切换边界，并在执行、恢复、
桥接或 canonical scene 提取失败时原子回滚。
**Known limitation**: ViennaPS v1 导入仅接受完整矩形层堆叠；图形化、断开、开口或
重叠网格会明确回退 Fast，避免不可逆铺平。Fast→Accurate 只对横向完全一致的
体素列生成解析矩形 slab，不使用 marching-cubes 表面猜测层边界。现有 WebUI
仍直接使用 Fast/voxel。
**Status**: 平坦衬底的真实 Fast→Accurate 路径与安全边界已实现并测试；任意图形的
VTK/level-set 导入仍属后续工作。

## M14 — ViennaPS Process Expansion (2026-09-02)

**Implemented**: ViennaPSBackend supports Initialize Wafer, Etch-Dry (SF6O2), Wet Etch (IsotropicProcess), Resist Develop, Deposition (conformal GeometricAdvect), Selective Epitaxy (experimental).
**Integrated**: capabilities() returns structured accurate_support dict.
**Known limitation**: 可选依赖，CI 无 ViennaPS 时跳过真实引擎用例；跨后端只支持
保守矩形层子集。
**Status**: 材料映射、绝对坐标、多材料 surface 提取与原子 restore 已验证；
主 WebUI 尚未切换为 Hybrid 执行器。

## M15 — Calibration Framework (2026-09-02)

**Implemented**: `calibration/` — CalibrationProfile/Runner/Report/Metrics, grid search, reproducibility (git commit + engine version + timestamp).
**Known limitation**: measure_etch_depth() uses mesh z-range (BUG-004, not true etch depth); only synthetic references; ViennaPS flux=100 is experimental placeholder (BUG-008).
**Status**: Implemented + Tested (framework ready, measurement semantics need M21).

## M16 — Natural Language Recipe Parser (2026-09-02)

**Implemented**: `recipe_planner/` — 多动作规则解析、边界安全的材料/单位归一化、
由真实 ParameterSpec 导出的参数契约，以及类型、枚举、材料、有限值和顺序校验。
**Known limitation**: 无 LLM 时复杂 SADP/键合描述会明确报告歧义，不承诺自动生成。
**Status**: 主 WebUI 与 v2 接口共用 planner；导入前执行原子预检。

## M17 — Recipe Assistant Integration (2026-09-02)

**Implemented**: React RecipeAssistant component (textarea → parse → review → apply → import); `/api/recipe/parse` POST endpoint in main WebUI server (tcad_simulator.py)。
**Integrated**: Single-server (no FastAPI dependency); component wired into App.tsx left pane above Process Flow.
**Validated**: 参数契约与前端错误恢复测试通过；输入示例显式包含涂胶/曝光/显影，
刻蚀使用时间参数。旧的“任意中文描述生成 5 步并成功运行”不作为当前能力保证。
**Status**: Implemented + Integrated + Validated.

## M18 — Hybrid Geometry Truth (2026-09-07, safe subset complete)

**Goal**: Make GeometryScene the canonical state in HybridBackend; enable true FAST↔ACCURATE↔FAST continuity.
**Completed**: z_min 排序、占据层数 height-map 语义、版本化/旧格式 snapshot、
执行及 bridge 回滚、退化三角形和不支持拓扑拒绝、绝对坐标与材料 surface 提取，
以及真实平坦体素衬底通过解析 slab 进入 Accurate 的连续性验证。
**Remaining**: 图形化 Voxel→ViennaPS 无损导入；在完成前按 ADR-023 显式 Fast 回退。

## Structure Reliability Closure (2026-09-07)

- React 对 manifest/部分 STL 失败可见并可重试；Run All 部分失败后只读同步服务端
  timeline/preview，保留原步骤错误；Recipe Assistant 等待导入成功才清空草稿。
- 公共 demo registry 为核心 5 项 + 高级 7 项。测试逐步执行且验证开窗、填槽、
  plug/via、侧墙、深槽和键合层；Fast 几何近似写入每个 demo 描述。
- DRAM 示例改为 16 个正式 ProcessStep 的可回放理想叠层，使用已标定的 grid=64
  掩膜、保存每步完整快照，并从最终网格量测 5 条 W 位线与 5 条更宽 Active Si；
  其他 grid 明确拒绝，不宣称气隙、侧向外延或器件物理。

## M20–M22 (2026-09-03)

**M20**: Directional Etch (`DirectionalProcess`), ALD Deposition (`SingleParticleALD`), Selective Etch (`IsotropicProcess` with materialRates). 7 tests green.
**M21**: `calibration/metrology.py` — MetrologyEngine with ROI-based etch depth (surface descent, BUG-004 fix), CD, film thickness, step coverage. 9 tests green.
**M22**: RecipeValidator KNOWN_STEPS from PROCESS_STEP_FACTORIES, ACCURATE_SUPPORT from ViennaPSBackend.capabilities() (BUG-005 fix). All planner tests green.

## M24 — Performance Benchmarks (2026-09-03)

**Implemented**: `tools/run_benchmarks.py` — profiling at 64³/128³ for voxel pipeline, scene→voxel conversion, ViennaPS steps, hybrid flow.

### Key Results (128³)
| Operation | Time | Assessment |
|---|---|---|
| Voxel full recipe (10 steps) | 0.83s | ✅ production ready |
| Surface extraction | 65ms | ✅ fast |
| GeometryScene conversion | 0.1ms | ✅ negligible |
| **Scene→Voxel (Python voxelizer)** | **41.5s** | ❌ **HOTSPOT** |
| ViennaPS init | 3ms | ✅ fast |
| ViennaPS etch (5s process) | 8s | ✅ reasonable |
| Hybrid FAST→ACC→FAST (32³) | 0.3s | ✅ good |

### Performance Hotspot
Scene→Voxel conversion is the clear bottleneck: Python even-odd voxelizer at O(triangles × nx × ny).
Next step: VTK C++ pipeline or C++ accelerated voxelizer (libtcad_core).

## Backlog (owner slots these into the sequence)

- Parameter sweep / DOE runner with metrology comparison (natural fit after M4).
- Device regions, electrodes, meshing export, electrical-solve interface stub.
- Calibration data ingestion; reproducible experiment packages.
- Incremental extraction of Worker/frontend/model subdomains; stable CI.
- Demo-load main-thread stall investigation (~30–60 s, observed 2026-08-28).

## Current Branch State (2026-09-07, structure reliability integration)

| Branch | Commit | Relationship |
| --- | --- | --- |
| `origin/main`（FonaTech 公开仓库） | `41a2fcd` | 公开基线（2026-05 README 更新），不含任何 M1–M5 实现 |
| `backup/main`（deepinwine） | `58d8a09` | M31 基线；本修复验证后由所有者授权更新 |
| 本地 `main` | `58d8a09` | 修复合并前与 `backup/main` 一致 |
| `codex/structure-reliability` | 本文对应提交 | 从 `58d8a09` 分支，承载可靠性修复与回归 |

祖先关系：`41a2fcd ⊂ …M2–M17 提交… ⊂ 3f7faba ⊂ …M18–M35 提交… ⊂ 58d8a09`。
**`origin`（FonaTech）是上游第三方仓库，不归本项目所有者——永远不做同步/推送
（ADR-010/017）；`backup`（deepinwine）是唯一的开发与发布远端。** 2026-08-31 曾误开
fork PR #1，已立即关闭。

- Next: 在任意图形 GeometryScene→ViennaPS 无损导入和校准数据完成前，保持 WebUI
  Fast/voxel 执行边界；随后继续 Task 8，不提前弃用旧 WebUI（ADR-012）。

## 双语与 Mask Workbench（2026-10-05，Task 4）

`codex/i18n-mask-workbench` 已交付中英文界面、逐字段显示单位、版本化 Mask Asset
与三栏二维版图工作台。Recipe 和版图坐标始终保存 canonical 值（nm、s、degree、nm/s）；
切换语言保持工艺参数草稿、版图历史和 Three.js 状态。

工作台支持矩形、圆、孔、有限宽线、闭合多边形、选择及多选移动、精确尺寸与旋转编辑、
GDS layer/datatype、图层显隐、网格吸附（0 关闭）和最多 100 项 Undo/Redo。
指针绘图和移动只在 pointerup 提交一次历史；未完成绘图需要确认放弃。
覆盖层保留 StudioShell 和 ThreeViewer 挂载，自动化测试验证相机视角保持、mount 一次、
dispose 为 0，关闭后焦点回到编辑入口。

「保存并应用」消费服务端权威步骤及状态并刷新预览，失败保留原 revision 和草稿。
「导入并应用」成功后立即绑定工艺步骤并同步 revision；返回不会撤销已完成的导入。
导出 JSON/GDS 使用明确的已保存版本；未保存草稿需先保存。
gdstk 缺失时 GDS 返回 `dependency_missing`，JSON 和旧图片 Mask 上传、预览路径继续可用。
Python HTTP 端到端测试使用 32³ session 验证左右开口造成曝光、显影和刻蚀后的实际结构差异、
非空 STL、权威 hash/revision 及无效候选失败原子性。

Fast/voxel 刻蚀能力保持 ADR-025：目标深度为 `estimated`、侧壁角为 `approximate`、
非零入射角为 `unsupported`，不得静默忽略不支持的参数。

Task 4 前端验证：`npm test -- --run`（24 个文件、379 项通过）、`npm run typecheck`、
`npm run build` 均退出 0。jsdom 保留原有 canvas/navigation 提示，Vite 保留 Three.js
包体积提示；没有新增未处理 Promise 或 React act 警告。
Python 全量最终复验及独立质量审查在集成交付时记录；本提交不合并或推送。
