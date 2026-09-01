# M5 React Parity 设计说明

- 日期：2026-08-31
- 状态：已实现（M5 核心工艺流交付于 `codex/m5-parity`；History/Domain/AI 抽屉记为 Backlog）
- 目标里程碑：M5 — React Parity
- 基线提交：`f61e069`（backup/main，M4 已合并）

## 1. 背景与目标

M2–M4 交付了 React Shell、完整 Three.js 查看器与 Python API Facade。React 客户端
已覆盖：步骤浏览/参数编辑/运行（step/to/all）/Timeline 快照恢复/3D 检视全套。
M5 补齐与旧 WebUI 的剩余功能差距，全部通过**已冻结**的 M2 Compatibility API
实现——不新增、不修改任何后端端点。

## 2. 对等差距清单（对照旧 WebUI 能力）

| 能力 | 旧 WebUI | React 现状 | M5 任务 |
| --- | --- | --- | --- |
| 撤销/重做 | ✅ | ❌ | T1 |
| 配方管理（Demo 加载、新建/保存/导出/导入、重命名） | ✅ | ❌（init 已返回 demo_recipes/recipes 但未使用） | T2 |
| 步骤结构编辑（新增/删除/复制/移动/重命名） | ✅ | ❌ | T3 |
| 掩膜上传与预览（Exposure 步骤） | ✅ | ❌ | T4 |
| 配方导出下载 | ✅ | ❌ | T5（并入 T2 或独立） |
| History/Domain/AI Agent 抽屉 | ✅ | ❌ | 记为 M5 后续/Backlog（非核心工艺流） |

## 3. 约束

- 只用冻结契约端点；任何新依赖的字段若不在契约表内，必须先补表（契约规则 1）。
- 行为对齐旧 WebUI 语义（undo 无可撤销时静默 no-op；undo/redo 有意使步骤缓存失效
  ——ADR-008；掩膜上传后 set_step 联动）。
- 旧 WebUI 在 React 过全部回归前不弃用、不删除（ADR-012）。

## 4. 关键设计

- **T1 撤销/重做**：Toolbar 新增「撤销/重做」；成功后 `undone/redone === true` 时
  重拉 timeline + bump previewGeneration（几何权威始终是 manifest.rev）；`false`
  时静默 no-op。变更 gate 与运行互斥。
- **T2 配方管理**：init 消费 `demo_recipes`/`recipes`；工具栏「配方」菜单：加载
  Demo（`/api/recipe/load`）、新建（`/api/recipe/new`）、保存（`/api/recipe/save`）、
  导出下载（`/api/recipe/export?scope=current`）、导入（`/api/recipe/import`）。
- **T3 步骤结构编辑**：ProcessFlowPane 增加上移/下移/复制/删除/重命名；
  `/api/recipe/{add,remove,duplicate,move,rename-step}`；结果 step list 整体替换。
- **T4 掩膜**：Exposure 类型步骤的参数面板显示当前 mask 与「上传掩膜」控件
  （multipart `/api/upload/mask`，成功后按嵌套 set_step 封套更新步骤）与预览图
  （`/api/mask/preview_step` binary → `<img>`）。
- **T5 收口**：对等清单核对（本文件 §2 全绿）、全量回归、生产式浏览器验收、
  文档；旧 UI 弃用决定留给所有者（单独评审）。

## 5. 任务划分

见 `docs/superpowers/plans/2026-08-31-m5-parity.md`。
