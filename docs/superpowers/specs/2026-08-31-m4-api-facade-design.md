# M4 Python API Facade 设计说明

- 日期：2026-08-31
- 状态：已实现（M4 交付于 `codex/m4-api-facade`，详见 `docs/ROADMAP_PROCESS_CAD.md`）
- 目标里程碑：M4 — Python API Facade
- 基线提交：`31ce391`（backup/main，M3 已合并）

## 1. 背景与目标

M1–M3 已交付：回归基线、React Shell、完整 Three.js 查看器。前端通过冻结的
M2 Compatibility API（HTTP）驱动现有 Worker/Session。M4 在 Python 侧建立**类型化
facade**，把同一套运行时能力（recipe / step / run / snapshot / geometry / materials）
包装为可独立测试、可被未来 FastAPI 服务复用的 Python API（ADR-013）。

## 2. 约束（宪法 + ADR）

- **冻结契约不动**：现有 `/api` 端点零改动；facade 是并行的新层。
- **facade 永不成为物理源**：只委托 `Recipe → PROCESS_STEP_FACTORIES →
  ProcessStep.execute(model) → ProcessModel`，不复制任何工艺算法。
- 新模块 `process_api/` 面向 Python 3.12+（当前环境 3.13.5）；`tcad_simulator.py`
  保持 3.10+ 兼容。
- 视图形状与冻结契约的 JSON 键名（camelCase）逐字段一致——facade 的序列化结果
  必须能被现有 React TS 类型直接消费，这是未来 FastAPI `/api/v2` 适配层的前置条件。
- 单文件 `tcad_simulator.py` 仍是权威源；facade 只做薄包装（strangler，ADR-013）。

## 3. 关键设计

### 3.1 包结构

```text
process_api/
├── __init__.py      # 公共导出
├── schemas.py       # 冻结契约视图的 dataclass 镜像 + camelCase JSON 序列化
├── errors.py        # ProcessCadError（code/step_index/parameter_path/suggestion）
└── facade.py        # ProcessCadFacade：会话级 typed API
```

schema 用标准库 dataclasses（零新依赖）；迁移到 Pydantic 时按同名字段平移。

### 3.2 Facade 语义

- `load_demo(name) / load_recipe_blob(blob)`：装载配方（demo 来自
  `load_demo_flows`）。
- `init() -> InitView`：recipe 视图 + model 摘要 + factories + materials + uiState。
- `set_step(index, params, enabled)`：参数编辑，当前及后续步骤级联 dirty（T2）。
- `run_step / run_to / run_all -> RunView`：执行并返回 typed 结果；revision 单调递增；
  失败抛 `ProcessCadError` 并按契约标记 error 状态（T2/T3）。
- `get_timeline / restore_timeline`：快照有效性 + 恢复（T3）。
- `preview_manifest / material_stl`：`get_material_surfaces` 的 typed 包装（T4）。
- FastAPI `/api/v2` 适配层（T5）：可选依赖、默认关闭、仅新增端点。

### 3.3 验证策略

- **parity 测试**：小网格下 facade 执行结果（occupied voxels、材料集合、三角数）
  与直接驱动 runtime 的基线方式逐项相等。
- **形状测试**：序列化 JSON 键名与冻结契约（frontend/src/api/types.ts）一致。
- 既有 183 项 Python 回归 + Golden 五流程保持全绿。

## 4. 任务划分

见 `docs/superpowers/plans/2026-08-31-m4-api-facade.md`。
