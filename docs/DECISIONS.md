# DECISIONS.md — Architecture Decision Records

Numbered, settled decisions. Agents: read before proposing alternatives.
To change a decision, add a new ADR that supersedes the old one — never deviate silently.

ADR-027 — 当前交付优先参数化 Structure CAD，暂停新增物理仿真（2026-10-07）。
Reason: 所有者明确选择输入参数得到半导体结构，以控制工程量。
Rules: 增加纯几何 Structure ProcessStep，尺寸直接构造几何，不调用速率、光学或
ViennaPS 求解；继续使用 React/Python/ProcessModel/Three.js 和既有 Recipe/资产契约。
既有仿真配方保留原语义。Structure UI 明确标识构建模式、网格精度和几何能力。
ADR-014 的 Accurate 栈保持兼容；其新增功能与校准工作暂停，直至所有者恢复安排。

ADR-028 — 结构编辑器采用八类工艺目录与原子步骤类型替换（2026-10-08）。
Reason: 所有者要求只显示光刻、刻蚀、沉积、氧化、外延、去胶、CMP、掺杂，
已有步骤也可在右侧改类型。
Rules: 晶圆初始化保留为底层 Recipe 步骤并经项目设置编辑；填充归沉积模式，
版图开口归光刻，平坦化归 CMP。旧工厂名称与仿真配方不自动迁移。
右侧修改类型先配置候选；确认后通过 `/api/step/set` 的可选 `name` 加法字段
完整校验再原子替换同索引，不使用 remove/add，不把厚度猜成刻蚀深度。
氧化、外延使用目标几何尺寸，掺杂只写浓度区域，不预测速率、扩散或激活。
掺杂颜色使用既有 `/api/preview/elements` 的真实场点云，不伪造材料编号。

---

ADR-001 — Python `ProcessModel` stays the geometry/process backend (Fast Mode).
Reason: the voxel implementation works, is testable, and is shared by desktop, WebUI,
headless, and Agent paths.
Constraint: do not replace before equivalent regression coverage exists; wrapped as
`VoxelBackend` at M7 with behavior unchanged.

ADR-002 — ~~WebUI is the primary Process CAD interface for V1; no React migration.~~
**SUPERSEDED by ADR-012** (owner decision, 2026-08-29): the long-term frontend is
React + TypeScript + Vite, introduced as a parallel frontend from M2. The spirit of this
ADR survives as a migration rule: the legacy WebUI remains functional and is only
deprecated after React parity (M5).

ADR-003 — ViennaPS / external TCAD backends deferred behind an adapter.
Reason: validate workflow and geometry UX on the voxel backend first.
Path (per ADR-014): experiments/ sandbox at M8 → `ViennaPSBackend` at M9.

ADR-004 — `tcad_simulator.py` remains the single canonical source until an explicit
migration milestone.
Reason: one distributable file is the current release model; the split package is a
generated navigation aid.
Constraint: no mass extraction for aesthetics; new modules only for real boundaries.

ADR-005 — Recipe JSON compatibility is additive-only.
Reason: recipes are user data; breaking them breaks trust.
Rule: new optional fields + version migration; load/save round-trip preserves step types,
order, enabled state, and instance names.

ADR-006 — Desktop GUI is maintained but not the primary CAD surface.
Reason: the WebUI session/worker model fits the CAD shell better; Qt stays compatible.
Constraint: no feature may exist in only one UI's private execution path.

ADR-007 — Viewer interactions are browser-local.
Reason: camera, projection, clipping, and material visibility must feel instant.
Rule: they must not trigger worker recomputes, `preview/manifest` refetches, or geometry
re-downloads; only lightweight UI state is persisted.

ADR-008 — Timeline restore is view-only; undo/redo is atomic with metadata.
Reason: reviewing a snapshot must never silently recompute; history restores model state
together with runtime statuses, step errors, timeline position, and recipe name.
Rule: restoring an invalid snapshot returns a structured error, never an implicit run.
Note: undo/redo intentionally invalidates the incremental step cache; it rebuilds on the
next run.

ADR-009 — UI language is Chinese-first with English technical terms.

ADR-010 — Push discipline: `backup` remote during development; `origin` (public) only at
approved milestone merges.

ADR-011 — Agent relay: one feature per agent, cross-review on handoff.
Reason: interleaved half-finished features are the main quality risk; boundaries matter
more than style. (Roles formalized in ADR-017.)

ADR-012 — Target frontend is React + TypeScript + Vite, built as a **parallel** frontend
under `frontend/` starting at M2 (supersedes ADR-002).
Reason: owner decision; a component frontend better serves the Process CAD UI long term.
Constraints: legacy WebUI is not deleted; React consumes stable APIs; deprecation only
after parity + regression green (M5).

ADR-013 — Python API layer target: FastAPI + Pydantic, reached by strangler migration.
Reason: typed schemas and async APIs suit the React frontend and job orchestration.
Constraints: first build a compatibility facade over the existing worker/session runtime;
standardize endpoints incrementally; API delegates to existing layers and never becomes a
source of process physics; large geometry uses binary/streaming representations.

ADR-014 — Accurate engine = C++20 ViennaPS + ViennaLS + VTK via official bindings or
pybind11 (extends ADR-003).
Reason: mature scientific libraries beat hand-rolled engines; heavy compute belongs in
compiled code.
Constraints: prototype only under `experiments/viennaps` (M8) before `ViennaPSBackend`
(M9); the app runs without ViennaPS; no per-step forced ViennaPS implementations; no
hidden repeated voxel↔level-set lossy conversions.

ADR-015 — VTK is the canonical geometry/scientific data interchange.
Reason: bridges voxel and level-set backends to the viewer with one representation.
Rule: VTP/VTU for surfaces/volumes; HDF5 or Zarr for large arrays; STL is export-only.

ADR-016 — KLayout is an optional layout engine behind `LayoutAdapter` (M6).
Reason: GDS/OASIS hierarchy, booleans, ROI extraction beyond gdstk.
Constraints: gdstk support stays; lithography receives normalized mask geometry, never
KLayout objects; KLayout never becomes a process engine.

ADR-020 — KLayout 后端已实现但未在真实 KLayout 环境验证（2026-09-01）。
Reason: 本环境（macOS/arm64）klayout wheel 镜像 403，无法安装。
Constraints: `layout/klayout_backend.py` 与 gdstk 后端同语义（归一化进出），
测试以 skipUnless 保护；能力探测（`LayoutAdapter.probe`）在 klayout 存在时自动
启用。待具备 KLayout 的环境（Linux CI 或本机安装成功）跑通
`KLayoutBackendTests` 后在本文件勾销。

ADR-021 — ViennaPS 沙盒已在本环境真机验证（2026-09-01 完成）。
Reason: PyPI 的 ViennaLS/ViennaPS 预编译 wheel 存在跨模块 pybind11 ABI 不匹配
（导入即 SIGSEGV）；按官方仓库（ViennaTools/ViennaPS）源码构建（libomp +
pybind11 3.0.x + Python 3.13 定向）后稳定。
Constraints: 引擎仅用于 `experiments/viennaps` 沙盒（ADR-014）；参考实验
（SF6O2 沟槽刻蚀，0.64µm 视场）完整执行并产出 VTK 网格；`process_backend`
注册表仍只有 'voxel'，ViennaPSBackend 与能力模型留待 M9。构建步骤记录于
`experiments/viennaps/README.md`。

ADR-022 — 桌面打包走无 Qt 路线：无头服务器 + 系统浏览器（2026-09-02）。
Reason: PyQt5 为 GPL v3，与项目 MIT 许可冲突；React + WebUIServerManager 已可
完全替代 Qt GUI（TCAD_SKIP_QT=1），桌面打包无需引入 Qt。
Constraints: PyInstaller spec（tcad_studio.spec）排除全部 Qt/PySide/tkinter；
React 前端以静态文件嵌入；许可保持 MIT。

ADR-017 — Agent roles: GLM implements, Codex reviews.
Reason: mutual review beats single-agent drift; the reviewer must not compete with the
implementer.
Rule: reviews produce a verdict + findings + repair list; fixes go back to the
implementer; `main` receives only approved merges. Owner arbitrates architecture; agent
counter-proposals are recorded as "Future Architecture Suggestion", not implemented.

ADR-018 — One concern per change.
Reason: mixed diffs (migration + physics + UI + dependency) are unreviewable and risky.
Rule: if a task forces two concerns, split the commits or the milestone.

ADR-019 — The existing WebUI HTTP API is frozen as the "M2 Compatibility API".
Reason: React (M2) must start before the typed facade (M4) exists; freezing the current
endpoints (methods, payload shapes, JSON/binary response types) gives React a stable
surface without waiting for M4.
Rule: evolution is additive-only; endpoints and fields React consumes must be listed in
`docs/ARCHITECTURE_TARGET.md` (M2 Compatibility API table) and covered by
`tests/test_webui_cad_shell.py::M2ApiContractTests` in the same change; methods are part
of the contract (wrong-method requests 404); binary endpoints stay binary; deprecation
only behind M4's versioned facade, never before React parity (M5).

ADR-023 — 配方与几何变更必须可执行、可验证、原子提交（2026-09-07）。
Reason: 旧自然语言解析器会丢动作并输出执行器不识别的参数；部分网格下载、
配方导入和 Hybrid 切换失败后仍可能展示旧几何，形成「成功但只有硅块」的假象。
Rules:
- Recipe 参数以 `ProcessStep.parameter_specs()` 和少量已登记的兼容扩展为唯一约束；
  仅迁移物理含义一致的别名，禁止把目标深度猜成刻蚀时间。
- 配方及 domain 在替换会话状态前完整校验；模型分配、步骤执行、后端切换与
  canonical scene 提取失败时回滚，不发布半完成状态。
- Fast/voxel 是现有 WebUI 的实际执行后端。Accurate 推荐仅表示 ViennaPS 能力；
  只有可证明无损的矩形层堆叠允许跨后端导入，图形化结构必须显式回退。
- Demo 和示例必须通过正式 ProcessStep 回放并量测输出几何；不得吞异常、直接
  写体素网格或用输入常量冒充测量结果，描述必须注明几何代理的适用范围。

ADR-024 — React 用户界面支持 `zh-CN` 与 `en` 完整切换（取代 ADR-009，2026-09-15）。
Reason: 工作台需要在不中断工艺编辑与几何查看的前提下，为中英文用户提供一致界面。
Rules:
- React 用户可见文案、可访问性标签和已知错误码文案统一由对等的中英文目录提供。
- 工艺自定义名称、材料名、Recipe 名称、原始日志与其他技术名称不强制翻译。
- 语言状态只影响呈现；切换语言不得改变 Recipe、未保存草稿、相机、Timeline、
  undo/redo 状态或单位偏好，也不得触发重新 bootstrap 或工艺 API 请求。

ADR-025 — 参数值使用 canonical 单位，显示单位属于浏览器逐字段偏好（2026-09-16）。
Reason: 换单位不能改变工艺定义或累积舍入误差；界面必须明确当前后端的能力边界。
Rules:
- Recipe、Python 与 API 参数仅保存 canonical 值：length=nm、time=s、angle=degree、rate=nm/s。
  React 从 canonical 草稿或服务端值换算显示；显示舍入结果不作为后续换算源。
- 显示单位不写入 Recipe；偏好以 `tcad.unit.v1:<step-name>:<parameter-key>` 保存在 localStorage。
- ParameterSpec 加法元数据和 backend capabilities 经 M2 snake_case / M4 camelCase 契约透传。
  后端声明 exact、approximate、estimated 或 unsupported，旧 API 没有声明时不推测能力。
- Fast/voxel 的目标深度只按名义/覆盖/材料库速率估算执行时间（estimated），侧墙为 approximate，
  入射角为 unsupported。非零入射角必须在模型变更前显式拒绝，不得执行或静默忽略。
- 旧 Etch time 模式保持兼容；sidewall 显式迁移为 sidewall_angle_deg，冲突必须拒绝。
  target_depth_nm 未设置时仍使用 time；不把旧 depth_nm 猜测为时间，也不声称按实测深度反馈停止。

ADR-026 — Mask Asset 使用不可变 revision 与候选原子发布（2026-10-04）。
Reason: Recipe 快照必须能复现实际曝光版图；保存、导入或步骤绑定失败时，不能让
资产 manifest、revision 文件与 Mask Exposure 引用处于相互矛盾的半完成状态。
Rules:
- Mask Exposure 通过 `mask_asset_id` 与正整数 `mask_asset_revision` 精确引用不可变版本；
  执行时读取该 revision、按当前仿真 domain 栅格化，并记录内容 SHA-256。不得静默升级
  到最新 revision。
- 候选先完成 v1 schema、有限坐标、闭合/非自交几何、资源预算与 64×64 栅格预检，
  再以同目录临时文件和 `os.replace` 发布 revision 与 manifest。保存应用任一步失败必须
  恢复步骤参数、旧 manifest，并删除本次 revision。
- JSON 是可编辑 round-trip 格式；GDS/OASIS 只经 `LayoutAdapter` 转为归一化几何，
  保留 layer/datatype 与源 database unit 元数据，第三方引擎对象不得进入 ProcessStep。
  缺少 gdstk 时 GDS 路径返回结构化 `dependency_missing`，JSON 路径仍可工作。
- 被当前 Recipe 引用的资产不得删除；服务返回引用的 recipe 与 step index。历史 revision
  首版只读，不支持就地重写。
- 这是 M2 Compatibility API 的加法扩展。旧 `mask_file`、Designer/Image/Custom 模式、
  `/api/upload/mask` 与预览端点继续工作，不强制迁移既有 Recipe。
- Mask Asset 栅格按 editable layer id 分组：普通 shape（包含折线段及圆形内部接缝）
  取并集，再减去该层显式 hole，最后各层取并集。孤立 hole 不产生实心区域，
  也不挖去其他层的图形。通用 `LayoutAdapter.rasterize` 保留旧 even-odd 契约。
- 单 polygon 最多 1,024 个不同顶点（另加闭合点），单 line 最多 1,024 个路径点。
  在坐标转换及拓扑检查前拒绝超限输入；另在整个候选的坐标转换前累计所有 polygon
  的 `n*(n-1)/2`，最多 250,000 次潜在边比较，超限返回预算错误 413。因此点数上限
  不保证单图形可通过累计工作预算。资产总预算
  仍为 50,000 shapes / 500,000 个生成顶点，折线内部接缝的 64 顶点也计入总预算。
  Polygon 拒绝重复点、零长边、端点相触、共线重叠、自交及零面积。
- GDS 导出通过 `LayoutAdapter.boolean` 对同层普通轮廓求并集后减显式 hole；结果经
  adapter 内部 gdstk fracture 拆为最多 5 顶点的简单 polygon，避免 GDS 孔洞的重复
  桥接边违反可编辑 polygon 的严格拓扑契约，并保留重导入后的孔洞和面积。
