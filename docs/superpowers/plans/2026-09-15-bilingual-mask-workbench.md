# 双语版图与刻蚀参数工作台实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框；每完成一个小步骤就勾选，并在每个任务的验证点停下来核对实际输出。

**目标：** 在不破坏旧 Recipe、旧 Mask 文件路径和 Three.js 交互的前提下，为 React Process CAD 增加完整中英文切换、逐参数显示单位、严格的刻蚀深度/角度语义，以及可保存版本化 Mask Asset 的二维版图工作台。

**架构：** React 只负责翻译、显示单位和编辑草稿；Python 继续持有 canonical 参数、Mask Asset 版本、栅格化和工艺执行。Mask Workbench 以固定覆盖层挂在现有三栏工作区上，使 ThreeViewer 不卸载；Mask Asset 经独立 `mask_assets` 边界验证后，通过既有 `ExposureStep` 的布尔掩膜入口执行。M2 HTTP 契约只做加法扩展，并同步文档和可执行契约测试。

**技术栈：** Python 3.10+、`unittest`、NumPy、现有 `LayoutAdapter`/gdstk 可选依赖、React 18、TypeScript、Vite、Vitest、Testing Library、原生 SVG 与 CSS。

---

## 文件与职责总览

### 新建文件

- `frontend/src/i18n/catalogs.ts`：`zh-CN`/`en` 目录、稳定翻译键和键集合类型。
- `frontend/src/i18n/I18nContext.tsx`：浏览器语言检测、`localStorage` 持久化、`t()` 与语言切换。
- `frontend/src/i18n/catalogs.test.ts`：目录键一致性、默认语言和持久化回归。
- `frontend/src/components/LanguageSwitcher.tsx`：顶部 `中文 / EN` 控件。
- `frontend/src/units/units.ts`：canonical/display 单位注册表、解析、换算和格式化纯函数。
- `frontend/src/units/units.test.ts`：长度、时间、角度、速率往返与非法值测试。
- `mask_assets/__init__.py`：Mask Asset 公共类型和服务导出。
- `mask_assets/model.py`：v1 schema、图层/图形校验、JSON 与 `LayoutGeometry` 转换。
- `mask_assets/store.py`：session 内版本目录、候选写入、原子发布、读取、列举和受保护删除。
- `mask_assets/service.py`：栅格化预检、GDS/JSON 导入导出、哈希和 Recipe 引用检查。
- `tests/test_mask_assets.py`：schema、原子性、revision、引用保护、GDS 可选依赖测试。
- `frontend/src/mask/types.ts`：Mask Asset API 与编辑器类型。
- `frontend/src/mask/editorReducer.ts`：图形操作、吸附、Undo/Redo 的纯 reducer。
- `frontend/src/mask/editorReducer.test.ts`：绘制、变换、删除、吸附和历史测试。
- `frontend/src/mask/MaskCanvas.tsx`：原生 SVG 二维画布与指针交互。
- `frontend/src/mask/MaskWorkbench.tsx`：三栏工作台、导入导出、保存应用和放弃流程。
- `frontend/src/mask/MaskWorkbench.test.tsx`：完整编辑会话与失败保稿测试。

### 修改文件

- `tcad_simulator.py`：扩展 `ParameterSpec`、Etch 严格语义、Mask Asset worker/HTTP 路由、曝光精确 revision 解析及 mask hash。
- `recipe_planner/schema.py`：透传参数维度/单位/能力元数据，兼容旧 `sidewall` 键并校验新 Etch 参数。
- `process_api/schemas.py`、`process_api/facade.py`：M2 typed view 增加参数元数据和后端能力。
- `frontend/src/api/types.ts`、`frontend/src/api/schemas.ts`、`frontend/src/api/client.ts`：类型、解析器和 Mask Asset API 客户端。
- `frontend/src/state/appReducer.ts`、`frontend/src/state/AppStateContext.tsx`：能力状态、Mask 应用结果和不丢草稿的异步动作。
- `frontend/src/App.tsx`、`frontend/src/components/*.tsx`、`frontend/src/viewer/*.tsx`：迁移全部 React 用户文案并接入工作台覆盖层。
- `frontend/src/components/ParameterPanel.tsx`、`frontend/src/components/MaskControl.tsx`：逐字段单位选择、能力标记和「编辑版图」入口。
- `frontend/src/styles.css`：语言开关、单位组合输入和 Mask Workbench 布局。
- 现有相应 `*.test.tsx`/`*.test.ts`：语言切换、状态保持、API 和三维视口无卸载回归。
- `tests/test_process_backend.py`、`tests/test_recipe_planner.py`、`tests/test_process_api_facade.py`：Etch 和扩展 schema 回归。
- `tests/test_webui_cad_shell.py`：新增端点生命周期、方法绑定、失败原子性和文档一致性。
- `docs/ARCHITECTURE_TARGET.md`、`docs/DECISIONS.md`、`docs/ROADMAP_PROCESS_CAD.md`：M2 契约、ADR 和交付状态。

## Task 1：国际化基础与全 React 文案迁移

**文件：**

- 新建：`frontend/src/i18n/catalogs.ts`
- 新建：`frontend/src/i18n/I18nContext.tsx`
- 新建：`frontend/src/i18n/catalogs.test.ts`
- 新建：`frontend/src/components/LanguageSwitcher.tsx`
- 修改：`frontend/src/main.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/components/ErrorNotice.tsx`
- 修改：`frontend/src/components/MaskControl.tsx`
- 修改：`frontend/src/components/ParameterPanel.tsx`
- 修改：`frontend/src/components/ProcessFlowPane.tsx`
- 修改：`frontend/src/components/RecipeAssistant.tsx`
- 修改：`frontend/src/components/StatusBadge.tsx`
- 修改：`frontend/src/components/StepStructureBar.tsx`
- 修改：`frontend/src/components/TimelineBar.tsx`
- 修改：`frontend/src/components/Toolbar.tsx`
- 修改：`frontend/src/viewer/MaterialPanel.tsx`
- 修改：`frontend/src/viewer/ThreeViewer.tsx`
- 修改：`frontend/src/styles.css`
- 修改：`docs/DECISIONS.md`
- 测试：以上组件对应的现有测试及 `frontend/src/App.test.tsx`

- [ ] **1.1 写出翻译目录的失败测试。**

  在 `catalogs.test.ts` 断言两份目录具有完全相同的排序键集合，并断言至少包含：

  ```ts
  expect(t('toolbar.runAll')).toBe('全部运行');
  expect(t('parameter.empty')).toBe('选择一个工艺步骤以查看参数');
  expect(t('error.network')).toContain('连接');
  ```

- [ ] **1.2 运行红灯测试。**

  ```bash
  cd frontend
  npm test -- --run src/i18n/catalogs.test.ts
  ```

  预期：因 `catalogs.ts` 和 `I18nContext.tsx` 尚不存在而失败。

- [ ] **1.3 实现类型安全目录和 I18n Provider。**

  使用以下公开接口，不引入第三方 i18n 依赖：

  ```ts
  export type Locale = 'zh-CN' | 'en';
  export type TranslationKey = keyof typeof zhCN;
  export function detectInitialLocale(
    stored: string | null,
    browserLanguages: readonly string[],
  ): Locale;
  export function useI18n(): {
    locale: Locale;
    setLocale(locale: Locale): void;
    t(key: TranslationKey, params?: Record<string, string | number>): string;
  };
  ```

  持久化键固定为 `tcad.locale.v1`。缺少键时开发环境抛错，生产环境返回键名；
  Provider 外的组件测试使用中文默认 context，避免为独立组件测试制造无关样板。

- [ ] **1.4 接入语言开关并验证状态不重置。**

  `App` 的最外层放置 `I18nProvider`，`Toolbar` 渲染 `LanguageSwitcher`。在
  `App.test.tsx` 中输入一个尚未 blur 的参数草稿、切换语言，然后断言输入值、
  选中步骤和 ThreeViewer runtime 实例均保持不变。

- [ ] **1.5 迁移所有 React 用户可见硬编码。**

  覆盖标题、按钮、空状态、aria-label、状态名、表单帮助、错误标题和 viewer 控件；
  工艺自定义名称、材料名、Recipe 名和原始日志继续原样显示。API 层保留技术错误，
  `ErrorNotice` 通过 `error.code` 映射 `error.<code>`，未知 code 显示
  `error.unknown` 并在 `<details>` 中保留安全技术 detail。

- [ ] **1.6 扫描遗漏硬编码并运行前端回归。**

  ```bash
  rg -n "[\x{4e00}-\x{9fff}]" frontend/src --glob '!**/*.test.*' --glob '!i18n/catalogs.ts'
  npm test -- --run
  npm run typecheck
  npm run build
  ```

  预期：扫描只剩技术注释或明确列入翻译边界的诊断文本；全部测试通过，类型检查和
  构建退出码为 0。

- [ ] **1.7 记录完整双语决策。**

  在 `docs/DECISIONS.md` 增加 ADR-024，明确 supersede ADR-009：React 用户界面支持
  `zh-CN` 与 `en` 完整切换，技术名称不强制翻译，语言状态只影响呈现。

- [ ] **1.8 提交 Task 1。**

  ```bash
  git add frontend/src docs/DECISIONS.md
  git commit -m "feat(前端): 增加完整中英文界面切换"
  ```

## Task 2：参数元数据、逐字段单位与严格 Etch 语义

**文件：**

- 新建：`frontend/src/units/units.ts`
- 新建：`frontend/src/units/units.test.ts`
- 修改：`tcad_simulator.py`
- 修改：`recipe_planner/schema.py`
- 修改：`process_api/schemas.py`
- 修改：`process_api/facade.py`
- 修改：`frontend/src/api/types.ts`
- 修改：`frontend/src/api/schemas.ts`
- 修改：`frontend/src/components/ParameterPanel.tsx`
- 修改：`frontend/src/components/parameterValidation.ts`
- 修改：`frontend/src/state/appReducer.ts`
- 修改：`frontend/src/state/AppStateContext.tsx`
- 修改：`frontend/src/styles.css`
- 修改：`docs/DECISIONS.md`
- 测试：`tests/test_process_backend.py`
- 测试：`tests/test_recipe_planner.py`
- 测试：`tests/test_process_api_facade.py`
- 测试：`frontend/src/api/schemas.test.ts`
- 测试：`frontend/src/components/ParameterPanel.test.tsx`

- [ ] **2.1 写单位换算红灯测试。**

  覆盖 `1000 nm ↔ 1 µm`、`120 s ↔ 2 min`、`180 degree ↔ π rad`、
  `10 nm/s ↔ 0.6 µm/min`，并连续往返 100 次后与最初 canonical 值误差小于
  `1e-10`。`NaN`、`Infinity`、未知单位和维度不匹配必须返回结构化错误。

- [ ] **2.2 实现 canonical 单位注册表。**

  ```ts
  export type Dimension = 'length' | 'time' | 'angle' | 'rate';
  export type DisplayUnit = 'nm' | 'µm' | 'ms' | 's' | 'min' | '°' | 'rad' | 'nm/s' | 'µm/min';
  export function toCanonical(value: number, dimension: Dimension, unit: DisplayUnit): number;
  export function fromCanonical(value: number, dimension: Dimension, unit: DisplayUnit): number;
  export function formatDisplayValue(value: number, decimals: number): string;
  ```

  换单位时始终以 reducer 中的 canonical `draft.value` 为源，绝不以已格式化字符串
  二次换算。单位偏好键为 `tcad.unit.v1:<step-name>:<parameter-key>`。

- [ ] **2.3 先写 Python schema 红灯测试。**

  断言 `ParameterSpec` 和 M2 `ParameterSpecView` 能 round-trip：

  ```python
  self.assertEqual(spec.dimension, "length")
  self.assertEqual(spec.canonical_unit, "nm")
  self.assertEqual(spec.display_units, ("nm", "µm"))
  self.assertEqual(spec.capability_key, "etch.target_depth")
  ```

  同时断言不含新字段的旧 fixture 仍能装载和执行。

- [ ] **2.4 扩展 Python 与 TypeScript 参数契约。**

  `ParameterSpec` 新字段均提供空默认值；旧 WebUI 的
  `_webui_serialize_parameter_spec()` 输出 `dimension`、`canonical_unit`、
  `display_units`、`capability_key`，前端解析器将其映射为 camelCase。M4 typed
  `ParameterSpecView.to_json()` 使用现有 camelCase 输出 `canonicalUnit`、
  `displayUnits`、`capabilityKey`。两条路径都继续接受只有 `units` 的旧响应。

- [ ] **2.5 定义 Fast/voxel Etch 能力矩阵。**

  `/api/init` 增加加法字段 `backend_capabilities`：

  ```json
  {
    "etch.target_depth": "estimated",
    "etch.sidewall_angle": "approximate",
    "etch.incidence_angle": "unsupported"
  }
  ```

  React 状态保存该映射；`ParameterPanel` 按 `capability_key` 显示本地化的
  `exact / approximate / estimated / unsupported` 标记。未声明 capability 的旧字段
  不显示标记。

- [ ] **2.6 写 Etch 新旧配方和非法角度红灯测试。**

  测试以下行为：旧 `sidewall` 迁移为同物理含义的 `sidewall_angle_deg`；无新字段时
  仍按 `time` 执行；`target_depth_nm=120` 与 `nominal_rate_nm_s=4` 得出 30 秒估算；
  深度存在但所有速率非有限或非正时失败；`sidewall_angle_deg` 不在 `(0, 90]` 失败；
  当前 voxel 下 `incidence_angle_deg != 0` 返回 `unsupported_parameter`，且模型快照不变。

- [ ] **2.7 实现 Etch canonical 参数与执行准备。**

  暴露以下参数：

  ```python
  ParameterSpec("target_depth_nm", "Target depth", "float", None,
                minimum=1e-9, dimension="length", canonical_unit="nm",
                display_units=("nm", "µm"), capability_key="etch.target_depth")
  ParameterSpec("sidewall_angle_deg", "Sidewall angle", "float", 88.0,
                minimum=1e-9, maximum=90.0, dimension="angle",
                canonical_unit="degree", display_units=("°", "rad"),
                capability_key="etch.sidewall_angle")
  ParameterSpec("incidence_angle_deg", "Incidence angle", "float", 0.0,
                minimum=0.0, maximum=89.999999, dimension="angle",
                canonical_unit="degree", display_units=("°", "rad"),
                capability_key="etch.incidence_angle")
  ParameterSpec("nominal_rate_nm_s", "Nominal rate", "float", None,
                minimum=1e-12, dimension="rate", canonical_unit="nm/s",
                display_units=("nm/s", "µm/min"), capability_key="etch.target_depth")
  ```

  新增 `_prepare_etch_execution(params, material_db) -> EtchExecutionPlan`：仅当
  `target_depth_nm` 存在时，从 `nominal_rate_nm_s`、旧 `rate_override` 的 Å/min
  或材料数据库速率中选择第一个有限正值，计算估算时间并记录
  `last_metrics={"target_depth_nm": ..., "duration_mode": "estimated", "time_s": ...}`。
  非零入射角在调用 `model.etch_material()` 前失败；现有 `sidewall` 只作为旧配方输入别名。

- [ ] **2.8 实现逐字段单位控件并验证保存 payload。**

  数值输入右侧增加独立 `<select>`；切换单位只更新显示值和偏好，不调用 API；编辑后
  `saveParameter` 发送 canonical 数值。测试 `1 µm` 保存为 `1000`、`2 min` 保存为
  `120`，语言切换和服务端失败都保留显示单位及草稿。

- [ ] **2.9 运行 Task 2 回归。**

  ```bash
  python -m unittest tests.test_process_backend tests.test_recipe_planner tests.test_process_api_facade
  cd frontend
  npm test -- --run src/units/units.test.ts src/api/schemas.test.ts src/components/ParameterPanel.test.tsx
  npm run typecheck
  ```

  预期：全部通过；Python 输出 `OK`，前端无未处理 Promise 和 React act 警告。

- [ ] **2.10 记录 canonical 单位和能力降级决策。**

  在 `docs/DECISIONS.md` 增加 ADR-025：Recipe/Python 只保存 canonical 值；显示单位
  属于浏览器本地偏好；后端对目标深度与角度声明 `exact/approximate/estimated/unsupported`，
  `unsupported` 不得执行。

- [ ] **2.11 提交 Task 2。**

  ```bash
  git add tcad_simulator.py recipe_planner process_api tests frontend/src docs/DECISIONS.md
  git commit -m "feat(工艺): 增加逐参数单位与严格刻蚀语义"
  ```

## Task 3：版本化 Mask Asset 后端与 M2 API

**文件：**

- 新建：`mask_assets/__init__.py`
- 新建：`mask_assets/model.py`
- 新建：`mask_assets/store.py`
- 新建：`mask_assets/service.py`
- 新建：`tests/test_mask_assets.py`
- 修改：`tcad_simulator.py`
- 修改：`frontend/src/api/types.ts`
- 修改：`frontend/src/api/schemas.ts`
- 修改：`frontend/src/api/client.ts`
- 修改：`frontend/src/api/client.test.ts`
- 修改：`frontend/src/api/schemas.test.ts`
- 修改：`tests/test_webui_cad_shell.py`
- 修改：`docs/ARCHITECTURE_TARGET.md`
- 修改：`docs/DECISIONS.md`

- [ ] **3.1 写 Mask Asset schema 红灯测试。**

  使用固定资产 `mask_metal1`，验证矩形、圆、孔、有限宽线和闭合多边形；拒绝重复
  shape id、未知 layer、非有限坐标、负尺寸、自交或未闭合多边形、越界图形、超过
  `50_000` 个 shape 或 `500_000` 个 polygon vertex。`coordinate_unit` 只能是 `nm`。

- [ ] **3.2 实现 v1 model 与归一化几何转换。**

  ```python
  @dataclass(frozen=True)
  class MaskAsset:
      version: int
      id: str
      revision: int
      name: str
      coordinate_unit: str
      bounds_nm: tuple[float, float, float, float]
      layers: tuple[MaskLayer, ...]
      shapes: tuple[MaskShape, ...]
      source: Mapping[str, Any]

  def parse_candidate(payload: Mapping[str, Any]) -> MaskAssetCandidate:
      return MaskAssetCandidate.from_mapping(payload)

  def to_layout_geometry(asset: MaskAsset) -> LayoutGeometry:
      return LayoutGeometry.from_polygons(asset.to_polygons())
  ```

  圆以固定 64 边形离散；线按 `width_nm` 生成封闭 polygon；hole 使用 even-odd
  轮廓。第三方 gdstk/KLayout 对象不得离开 `LayoutAdapter`。

- [ ] **3.3 写 store 原子性和引用保护红灯测试。**

  断言首次保存 revision=1、再次保存 revision=2、历史 revision 不变；模拟
  `os.replace` 前验证失败时目录字节完全不变；删除被 Recipe 的步骤 3 引用的资产时，
  返回 `mask_asset_in_use` 和 `[{"recipe":"current","step_index":3}]`。

- [ ] **3.4 实现 session 版本存储和 service。**

  每个 session 使用 `mask_assets/<asset-id>/revisions/<revision>.json` 和
  `mask_assets/<asset-id>/manifest.json`。候选先写同目录临时文件，完成 schema、SHA-256、
  `adapter.rasterize(geometry, shape=(64, 64), bounds=bounds_nm)` 预检后，以 `os.replace`
  发布 revision 和 manifest。任一失败删除临时文件，不改变当前 revision。

- [ ] **3.5 写 GDS/JSON 导入导出红灯测试。**

  JSON round-trip 必须保留可编辑 shape；GDS 导入保留 layer/datatype 和源数据库单位；
  gdstk 缺失时返回 `dependency_missing`、`params={"dependency":"gdstk"}`，JSON 导入仍
  成功。GDS 导出再读回后比较层集合和几何面积。

- [ ] **3.6 实现导入导出。**

  `import_json` 走同一 candidate parser；`import_gds` 调用现有 `LayoutAdapter.read()`，
  每个归一化 polygon 转成可编辑 polygon shape，`source.kind="gds"` 并记录源文件名。
  导出 JSON 使用原始 v1 数据；导出 GDS 调用 `LayoutAdapter.write()`，不猜单位、不缩放。

- [ ] **3.7 写 Exposure revision 绑定与执行红灯测试。**

  保存 asset revision 1，修改成 revision 2；步骤显式绑定 revision 1 后执行，断言实际
  栅格与 revision 1 一致且 `last_metrics.mask_sha256` 等于 revision 1 内容哈希。缺失
  revision、栅格化失败或 set_step 失败时，模型、Recipe 引用和资产 manifest 均保持原值。

- [ ] **3.8 实现 worker 原子保存、绑定与曝光桥接。**

  新 worker RPC：`mask_asset_list`、`mask_asset_get`、`mask_asset_save_apply`、
  `mask_asset_import_apply`、`mask_asset_delete`。`mask_asset_save_apply` 在一个事务中完成
  候选预检、revision 发布、步骤参数更新；步骤使用
  `mask_asset_id`、`mask_asset_revision`、`mask_mode="Asset"`。任何异常恢复步骤 blob、
  删除本次 revision 并保留浏览器草稿。`ExposureStep.execute()` 读取精确 revision、
  按当前 domain 栅格化后复用 `mask_override`，并记录 revision 和 hash。

- [ ] **3.9 扩展 M2 HTTP 契约。**

  增加并固定：

  | Path | Method | 成功响应 |
  | --- | --- | --- |
  | `/api/mask/assets` | GET | JSON 资产摘要列表 |
  | `/api/mask/asset` | GET | JSON 精确 asset/revision |
  | `/api/mask/asset/save` | POST JSON | JSON asset + `SetStepView` |
  | `/api/mask/asset/import` | POST multipart | JSON asset + `SetStepView` |
  | `/api/mask/asset/delete` | POST JSON | JSON `{deleted:true}` |
  | `/api/mask/asset/export` | GET | JSON 或 GDS binary |

  所有失败 envelope 使用 `code`、`params`、安全 `error` 和可选 `detail`；错误状态码
  使用 400/404/409/413/500，wrong-method 继续 404。同步更新
  `ARCHITECTURE_TARGET.md` 表和 `M2ApiContractTests`，使文档静态一致性测试覆盖六个端点。

- [ ] **3.10 扩展 typed frontend client。**

  ```ts
  listMaskAssets(signal?: AbortSignal): Promise<readonly MaskAssetSummary[]>;
  getMaskAsset(id: string, revision: number, signal?: AbortSignal): Promise<MaskAsset>;
  saveAndApplyMaskAsset(request: SaveMaskAssetRequest, signal?: AbortSignal): Promise<MaskAssetApplyView>;
  importAndApplyMaskAsset(file: File, stepIndex: number, signal?: AbortSignal): Promise<MaskAssetApplyView>;
  deleteMaskAsset(id: string, signal?: AbortSignal): Promise<void>;
  exportMaskAsset(id: string, revision: number, format: 'json' | 'gds', signal?: AbortSignal): Promise<Blob>;
  ```

  parser 对所有坐标做 finite 检查，对 revision 做正整数检查，对未知 shape type 抛
  `ApiContractError`。

- [ ] **3.11 运行 Task 3 回归。**

  ```bash
  python -m unittest tests.test_mask_assets tests.test_layout_adapter tests.test_webui_cad_shell
  cd frontend
  npm test -- --run src/api/client.test.ts src/api/schemas.test.ts
  npm run typecheck
  ```

  预期：有 gdstk 时 GDS round-trip 通过；无 gdstk 时仅标注好的 GDS 测试 skip，JSON、
  Mask Asset 和 HTTP 生命周期全部通过。

- [ ] **3.12 记录 Mask Asset 版本与原子发布决策。**

  在 `docs/DECISIONS.md` 增加 ADR-026：Mask Exposure 引用不可变 revision；资产候选必须
  经过 schema、预算和栅格预检才发布；GDS 只经 `LayoutAdapter`；保存应用失败回滚
  manifest、revision 文件和步骤引用。

- [ ] **3.13 提交 Task 3。**

  ```bash
  git add mask_assets tcad_simulator.py tests frontend/src/api docs/ARCHITECTURE_TARGET.md docs/DECISIONS.md
  git commit -m "feat(版图): 增加版本化 Mask Asset 与原子 API"
  ```

## Task 4：Mask Workbench、保存返回与端到端结构验证

**文件：**

- 新建：`frontend/src/mask/types.ts`
- 新建：`frontend/src/mask/editorReducer.ts`
- 新建：`frontend/src/mask/editorReducer.test.ts`
- 新建：`frontend/src/mask/MaskCanvas.tsx`
- 新建：`frontend/src/mask/MaskWorkbench.tsx`
- 新建：`frontend/src/mask/MaskWorkbench.test.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/components/MaskControl.tsx`
- 修改：`frontend/src/components/ParameterPanel.tsx`
- 修改：`frontend/src/state/appReducer.ts`
- 修改：`frontend/src/state/AppStateContext.tsx`
- 修改：`frontend/src/i18n/catalogs.ts`
- 修改：`frontend/src/styles.css`
- 修改：`frontend/src/App.test.tsx`
- 修改：`frontend/src/viewer/ThreeViewer.test.tsx`
- 修改：`tests/test_webui_cad_shell.py`
- 修改：`docs/ROADMAP_PROCESS_CAD.md`

- [ ] **4.1 写 reducer 红灯测试。**

  依次测试：在活动层添加矩形；10 nm 网格吸附；多选移动；单图形缩放和旋转；删除；
  layer/datatype 切换；图层显隐不删除图形；Undo/Redo 恢复精确 JSON；分叉编辑后清空
  redo；历史上限 100 个状态。

- [ ] **4.2 实现纯编辑 reducer。**

  ```ts
  export interface MaskEditorState {
    asset: MaskAssetDraft;
    selection: readonly string[];
    activeLayerId: string;
    tool: 'select' | 'rectangle' | 'circle' | 'hole' | 'line' | 'polygon';
    gridVisible: boolean;
    snapNm: number;
    past: readonly MaskAssetDraft[];
    future: readonly MaskAssetDraft[];
    dirty: boolean;
  }
  export function maskEditorReducer(state: MaskEditorState, action: MaskEditorAction): MaskEditorState;
  ```

  pointer 移动期间只更新当前操作的 transient geometry；pointerup 时才压入一个历史项，
  避免每像素生成快照。

- [ ] **4.3 写 SVG 画布交互红灯测试。**

  以固定 `viewBox="0 0 2000 2000"` 测试矩形拖绘、圆心/半径、线宽、polygon 双击闭合、
  shape 点击选择、背景点击清选和 Delete 键。隐藏层图形既不渲染也不可命中。

- [ ] **4.4 实现 MaskCanvas。**

  使用原生 SVG `<rect>`、`<circle>`、`<line>`、`<polygon>`，坐标通过
  `svg.createSVGPoint()` 与 `getScreenCTM().inverse()` 转为 nm。网格只作视觉背景；所有
  写入坐标经 `snapCoordinate(value, snapNm)`。画布不直接调用 HTTP。

- [ ] **4.5 写工作台会话红灯测试。**

  从 Mask Exposure 点击「编辑版图」，断言主工作区仍挂载；编辑图形、Undo、切换 EN，
  断言草稿和历史不变；保存成功后关闭覆盖层、保持原步骤选中并更新 revision；保存失败
  时覆盖层、草稿和旧 revision 保持；放弃有改动时确认后返回且不调用 API。

- [ ] **4.6 实现三栏 Mask Workbench。**

  左栏：工具、图层、活动 layer/datatype、显隐、网格和吸附；中栏：`MaskCanvas`；右栏：
  资产名、bounds 和选中图形的精确数值 Inspector。顶部包含 Undo、Redo、GDS/JSON
  导入、GDS/JSON 导出、保存并应用、放弃。覆盖层使用 `role="dialog"` 和焦点圈闭，
  `Escape` 走放弃确认。

- [ ] **4.7 保持 ThreeViewer 和主工作状态。**

  `App` 始终渲染现有 `StudioShell`，仅在其后追加固定定位的 `MaskWorkbench`；不要用条件
  分支替换 `ThreeViewer`。测试记录 runtime `dispose()` 调用次数，打开/关闭工作台期间
  必须为 0；Recipe、selectedStepIndex、drafts、timeline 和 viewer camera snapshot 不变。

- [ ] **4.8 串联保存应用与预览刷新。**

  成功响应 dispatch `mask/assetApplied`：用服务端 `SetStepView` 更新步骤和状态，递增
  `previewGeneration`，再关闭工作台。失败只写 `globalError`，不清 editor state。
  旧 `uploadMask` 和 `/api/mask/preview_step` 控件继续可用，作为兼容导入路径。

- [ ] **4.9 增加 HTTP 端到端结构变化测试。**

  在 32×32×32 session 中构造左半开口 Mask Asset，依次运行 Initialize Wafer、Spin
  Resist、Mask Exposure、Resist Develop 和 Etch；断言：绑定 revision/hash 与响应一致，
  左右半区 Photoresist/目标材料体素计数不同，最终 preview manifest revision 增加且 STL
  非空。再用无效候选重试，断言 manifest revision、步骤引用和几何计数不变。

- [ ] **4.10 运行全量与规定基线。**

  ```bash
  python -m unittest discover -s tests
  python tools/run_process_cad_baseline.py --json
  python tools/run_demo_regression.py --grid 128
  cd frontend
  npm test -- --run
  npm run typecheck
  npm run build
  ```

  预期：Python 全量 `OK`（仅声明的可选依赖 skip）；baseline 返回成功 JSON；grid=128
  核心 demo 全部通过；前端测试、类型检查和生产构建退出码为 0。

- [ ] **4.11 无 gdstk 环境模拟。**

  ```bash
  python -m unittest tests.test_mask_assets.MaskAssetDependencyTests tests.test_webui_cad_shell.M2ApiContractTests
  ```

  测试内部通过 `sys.modules['gdstk']=None` 阻断导入；预期 GDS 请求返回
  `dependency_missing`，JSON 保存、导入、执行及旧图片 Mask 路径仍通过。

- [ ] **4.12 更新交付文档并提交 Task 4。**

  `ROADMAP_PROCESS_CAD.md` 记录双语、单位、Mask Workbench 与 Etch 能力矩阵的实际状态，
  不把 `unsupported` 描述成已支持。

  ```bash
  git add frontend/src tests/test_webui_cad_shell.py docs/ROADMAP_PROCESS_CAD.md
  git commit -m "feat(前端): 交付双语 Mask Workbench 闭环"
  ```

## Task 5：独立复审、合并与只推 backup/main

**文件：**

- 复审：从 `10d9c20` 到当前 HEAD 的完整 diff
- 可修改：仅复审发现对应文件
- 更新：`docs/ROADMAP_PROCESS_CAD.md`（若验证数字或已知限制发生变化）

- [ ] **5.1 做计划覆盖自检。**

  逐条对照设计文档 10 项验收标准，确认每项至少有一个明确测试；运行：

  ```bash
  rg -n "TODO|TBD|待定|待补|稍后实现|类似任务|适当处理" \
    frontend/src mask_assets tests docs/superpowers/plans/2026-09-15-bilingual-mask-workbench.md
  git diff --check 10d9c20..HEAD
  ```

  预期：无占位实现；`git diff --check` 无输出。

- [ ] **5.2 按 AGENTS.md §9 发起独立代码复审。**

  复审必须给出 Verdict、BLOCK/NB 编号、八项边界合规、回归风险和有序修复清单；重点
  检查 i18n 状态不重置、canonical 单位不漂移、Etch 不静默忽略、Mask save/apply
  原子性、旧 Recipe/旧 Mask 路径、gdstk skip 和 ThreeViewer 不卸载。

- [ ] **5.3 按编号修复所有 BLOCK 并重跑对应红绿测试。**

  每项修复先加入能复现问题的测试，再做最小实现。修复提交使用
  `fix(范围): 中文问题说明`，不得把无关格式化混入。

- [ ] **5.4 在最终提交上重新执行完整验证。**

  重复 4.10 与 4.11 的全部命令，记录实际测试数、skip 数、baseline 结果、grid=128
  demo 结果和前端测试数。不得引用修复前输出。

- [ ] **5.5 核对 Git 目标并合并。**

  ```bash
  git status --short
  git log --oneline --decorate -8
  git remote -v
  git merge-base --is-ancestor 10d9c20 HEAD
  ```

  确认工作树仅含本任务预期改动、祖先关系正确、目标远端名为 `backup` 且 URL 属于
  `deepinwine/TCAD-Simulator`。复审 APPROVE 后将功能分支合并至本地 `main`。

- [ ] **5.6 只推 deepinwine 的 main 并核验远端。**

  ```bash
  git push backup main
  git ls-remote backup refs/heads/main
  git rev-parse main
  ```

  最后两个 SHA 必须完全一致。不得运行 `git push origin`；`origin/FonaTech` 只在用户
  另行明确批准公开里程碑时处理。
