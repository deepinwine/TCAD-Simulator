# Process CAD 五流程 Golden Baseline 设计

**日期：** 2026-08-30

**里程碑：** M1 Existing Runtime Regression Baseline

**状态：** 已获所有者批准（方案 A）

## 1. 目标

在不新增工艺原语、不改变现有物理模型的前提下，完成 M1 规定的 5 套具名流程：

1. Basic Trench；
2. Spacer Formation；
3. Bonding + Thinning；
4. W Plug + CMP；
5. Basic BEOL。

同时建立一个与 WebUI 无关的公开流程注册入口，让 WebUI、无头 Golden 测试和基准运行器消费同一份配方定义。新增流程是用于锁定当前快速体素后端行为的回归夹具，不宣称具备经晶圆厂标定的工艺精度。

## 2. 范围与非目标

### 2.1 本次范围

- 新增公开函数 `load_demo_flows(material_db)`，每次返回可独立修改的 5 套完整配方 blob。
- 保留 `_webui_demo_recipes(material_db)` 作为兼容包装，返回与公开函数等价的新鲜数据。
- WebUI 示例菜单展示全部 5 套流程。
- `tests/test_process_cad_demos.py` 对新增流程做逐步骤行为验证和最终结构验收。
- `tools/run_process_cad_baseline.py` 改用公开入口并运行全部 5 套流程。
- 更新 M1 路线图状态和基准说明。

### 2.2 非目标

- 不新增或重写 Etch、Deposition、Fill、CMP 等原语。
- 不抽离 `tcad_simulator.py` 中的工艺实现，也不提前建设 M4 Python facade。
- 不引入 React、FastAPI、数据库或新的外部依赖。
- 不把 Golden 验收写成固定体素总数；验收关注拓扑、材料关系和步骤前后变化。
- 不把简化流程描述成可直接用于制造的工艺卡。

## 3. 架构

### 3.1 单一数据源

```text
load_demo_flows(MaterialDatabase)
        ├── WebUI /api/init demo_recipes
        ├── tests/test_process_cad_demos.py
        ├── tools/run_process_cad_baseline.py
        └── _webui_demo_recipes() 兼容包装
```

`load_demo_flows()` 延续现有配方 JSON 结构：顶层包含 `name`、`description`、`domain` 和 `steps`；步骤包含 `name`、`instance_name`、`enabled`、完整默认参数与覆盖参数。Mask Exposure 仍可携带内嵌 `custom_mask`。返回值不得包含 `runtime_status`，并且每次调用都必须深度隔离。

`_webui_demo_recipes()` 不再维护第二份流程定义，只调用公开函数。这样既保留现有内部调用兼容性，又让基准和 Golden 测试停止依赖私有 WebUI helper。

### 3.2 兼容边界

- 现有 3 套流程的名称、顺序、步骤和参数保持不变。
- 新流程追加在注册表末尾，顺序固定为 `W Plug + CMP`、`Basic BEOL`。
- 现有 recipe import/export 与 `_webui_deserialize_step()` 数据格式不变。
- Worker 的 `/api/init` 响应结构不变，只增加 `demo_recipes` 映射中的条目。
- `_webui_demo_recipes()` 继续可调用，避免下游私有依赖立即断裂。

## 4. 流程设计

所有流程沿用 `64 × 64 × 96`、`10 nm` voxel、单 worker 的演示域。掩模使用 `32 × 32` 二值阵列，由现有曝光步骤缩放到模型横截面。

### 4.1 W Plug + CMP

该流程演示接触介质开孔、钨塞填充、钨过镀和以氧化物为停止层的 CMP：

1. Initialize Wafer：生成 `300 nm` Silicon。
2. Deposition：全片 CVD 沉积 `100 nm` Silicon Dioxide 作为接触介质层。
3. Spin Resist：涂覆正胶。
4. Mask Exposure：使用 4 个分离方形开口的 contact mask。
5. Resist Develop：打开接触孔图形。
6. Etch：各向异性刻蚀 `100 nm` Silicon Dioxide，孔底到达 Silicon。
7. Strip：去除 Photoresist。
8. Fill：从 top 方向以 Tungsten 填充外部连通接触孔，深度上限 `100 nm`。
9. Deposition：全片 CVD 增加约 `30 nm` Tungsten 过镀层，为 CMP 提供真实可移除材料。
10. CMP：目标高度 `400 nm`，选择性列表只允许 Tungsten 去除，Silicon Dioxide 作为停止层。

Golden 语义：

- 接触孔刻蚀步骤减少氧化物且不刻蚀 Silicon；
- Fill 步骤增加 Tungsten，且钨与孔底 Silicon 相邻；
- 过镀步骤在场区形成 Tungsten 顶层；
- CMP 减少 Tungsten、清除场区过镀，但保留分离的孔内钨塞；
- 最终顶面平坦，Tungsten 不构成全片材料层，Photoresist 为零。

### 4.2 Basic BEOL

该流程采用简化的单层镶嵌互连，演示线槽、Ta 阻挡层、Cu 填充和 CMP：

1. Initialize Wafer：生成 `300 nm` Silicon。
2. Deposition：全片 CVD 沉积 `100 nm` Silicon Dioxide 作为层间介质。
3. Spin Resist：涂覆正胶。
4. Mask Exposure：使用两条分离的贯穿线条掩模。
5. Resist Develop：打开线槽图形。
6. Etch：在 Silicon Dioxide 中刻蚀约 `60 nm` 的线槽，不贯穿介质层。
7. Strip：去除 Photoresist。
8. Deposition：PVD 沉积约 `10 nm` Tantalum，作为简化阻挡层。
9. Fill：从 top 方向以 Copper 填充线槽中的外部连通空隙。
10. Deposition：Electroplate 增加约 `30 nm` Copper 过镀层。
11. CMP：目标高度 `400 nm`，允许 Copper 与 Tantalum 去除，Silicon Dioxide 作为停止层。

Golden 语义：

- 氧化物线槽只出现在掩模线条区域，介质层仍隔离 Copper 与 Silicon；
- Tantalum 在铜填充前出现，并在槽内保留可观察体素；
- Fill 和过镀步骤均增加 Copper；
- CMP 减少 Copper 和场区阻挡层，最终不含全片 Copper/Tantalum 顶层；
- 最终顶面为氧化物与两条分离 Copper 线的平坦组合，Photoresist 为零。

## 5. 数据与执行流

1. 调用者构造 `MaterialDatabase`。
2. `load_demo_flows()` 通过现有 `PROCESS_STEP_FACTORIES` 补齐每个步骤的默认参数，再叠加流程覆盖值。
3. 调用者按现有路径用 `_webui_deserialize_step()` 恢复 `ProcessStep`。
4. 步骤按顺序执行；测试在每一步前后采集材料计数、全片 Z 平面、顶面高度和必要的材料邻接关系。
5. WebUI 继续通过 `/api/init` 获取同一 blob；基准运行器使用公开入口直接无头执行。

注册表只负责生成可移植配方，不持有模型、worker、快照或运行时状态。任何步骤参数错误仍由现有反序列化、步骤验证和事务边界处理。

## 6. 测试策略

### 6.1 注册表契约

- 精确断言 5 个名称及稳定顺序。
- 验证每个步骤均可经现有 factory 反序列化。
- 验证新旧入口内容等价但对象深度隔离。
- 验证 Worker `/api/init` 暴露同一注册表。

### 6.2 逐步骤 Golden 验收

- 扩展 checkpoint 材料集合，记录 Tungsten、Copper、Tantalum。
- 对 W Plug + CMP 检查氧化物开孔、钨填充、过镀、CMP 去除和最终孔底邻接。
- 对 Basic BEOL 检查线槽深度、Ta 先于 Cu、Cu 填充/过镀、CMP 去除和最终双线拓扑。
- 关系断言根据 `voxel_size_nm` 和掩模形态计算，不依赖固定材料总数或绝对 Z 坐标。
- 在 `_scipy_ndimage = None` 的 fallback 路径执行全部 5 套流程，至少验证运行成功和关键材料存在。

### 6.3 基准

- 基准运行器从 `load_demo_flows()` 获取流程。
- `DEMO_NAMES` 扩展到 5 套，并为新增流程添加轻量语义检查。
- 正式验证继续使用固定 `640 nm` 物理域和 `128³` 网格；报告格式保持兼容，只增加两个 `demos` 条目。
- M1 仍以全部流程语义检查通过为成功条件，不设置脆弱的绝对耗时阈值。

## 7. 文档与提交边界

- README 的基准说明从 3 套更新为 5 套，并说明公开注册入口。
- `docs/ROADMAP_PROCESS_CAD.md` 在实现和验证完成后将 M1 五流程标为完成；不改变 M2 及后续架构决策。
- 实现采用 TDD：先提交能证明公开入口和新增流程缺失的红灯测试，再提交最小生产实现，最后提交基准与文档收尾。
- 所有提交只推送 `backup/zcode/process-cad-shell`；不得推送 `origin`，不得自行合并到 `main`。

## 8. 完成标准

以下条件全部满足才可宣称 M1 Golden Baseline 完成：

1. 5 套流程都能从公开入口生成并完成 headless 执行；
2. 两套新流程的逐步骤与最终 Golden 语义全部通过；
3. 现有 3 套流程及 SciPy fallback 无回归；
4. 基准运行器在 `128³` 上完成 5 套流程并返回 `ok: true`；
5. AGENTS.md 规定的完整 unittest、`py_compile`、JavaScript 语法检查和 `git diff --check` 全部通过；
6. 工作提交与 backup 远端 SHA 一致，origin 未被推送。
