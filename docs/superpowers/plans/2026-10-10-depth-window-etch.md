# 深度区间刻蚀实现计划

> **面向 AI 代理的工作者：** 使用 subagent-driven-development，逐任务 TDD，实现后依次进行规格与质量审查。先完成 `2026-10-10-step-display-visibility.md` 的任务 3、4，不并行改工艺行为。

**目标：** 从已有通道，在指定深度区间内按 0–100 方向性去除目标材料。

**架构：** 复用 Structure Etch、参数 schema、事务提交和显示来源清理。新增 Python 区间几何模块，React 只编辑参数，不产生体素或网格。

**技术栈：** Python、NumPy／SciPy，现有 ProcessModel；React、TypeScript、Three.js。

## 文件职责

- 新建 `structure_cad/depth_window_etch.py`：参数解析、冻结高度带、可达表面、受限扩展候选，禁止直接修改 model。
- 修改 `structure_cad/operations.py`：区间模式 preflight 与 construct 分流，复用减材 commit。
- 修改 `tcad_simulator.py`：Structure Etch 参数定义和模式相关字段元数据，保持普通模式默认。
- 修改 `recipe_planner/schema.py`：同一套参数规则和跨字段校验，不创建另一套配方协议。
- 新建 `tests/test_depth_window_etch.py`：解析、几何、预算与失败原子性。
- 新建 `tests/test_depth_window_etch_http.py`：现有步骤编辑／执行／导入导出／保存加载协议。
- 修改 `frontend/src/components/ParameterPanel.tsx` 及测试：仅显示当前模式和参考方式所需字段。
- 修改 `frontend/src/api/types.ts`、`schemas.ts`、`frontend/src/test/structureFactoryTemplates.json`：增量参数契约及真实工厂 fixture。
- 修改 `frontend/src/i18n/catalogs.ts`：中文／英文标签、区间截断、入口平面和可达通道解释。
- 修改 `docs/ARCHITECTURE_TARGET.md`、`docs/DECISIONS.md`：记录几何规则与兼容，不添加新执行端点。

## 任务 1：参数与高度带解析

- [ ] 在 `tests/test_depth_window_etch.py` 写失败测试：普通模式缺省、无活动字段依赖、两种参考方式等价、区间颠倒、非有限值、bool、超域、空区间、空开口。

```python
def test_directionality_endpoints_and_validation(self):
    for value in (0, 50, 100):
        self.assertEqual(parse_window_params({
            'etch_mode': 'Depth window', 'depth_reference': 'Opening plane',
            'start_depth_nm': 100, 'end_depth_nm': 200,
            'etch_distance_nm': 30, 'directionality_percent': value,
        }).directionality, value / 100)
    for value in (True, -1, 101, float('nan'), float('inf')):
        with self.assertRaises(ValueError):
            parse_window_params({
                'etch_mode': 'Depth window', 'depth_reference': 'Opening plane',
                'start_depth_nm': 100, 'end_depth_nm': 200,
                'etch_distance_nm': 30, 'directionality_percent': value,
            })
```

- [ ] 运行 `TCAD_SKIP_QT=1 MPLBACKEND=Agg /opt/anaconda3/bin/python3 -m unittest tests.test_depth_window_etch`，确认新增测试因解析行为不存在失败。
- [ ] 新模块定义不可变 `WindowParams`、`ResolvedWindow`，实现 `parse_window_params(params)` 与 `resolve_window(model, parsed)`。内部新字段统一为上述英文键；固定 Z 使用 `lower_z_nm`、`upper_z_nm`。普通模式值为 `Standard`，新模式值为 `Depth window`。
- [ ] 参考面由本步开始时开口内非空柱的最高实体上边界解析；冻结为一个值，范围用体素中心按半开区间选取。复用 domain 坐标，测试禁止半体素偏移或 µm／nm 混用。
- [ ] 新 ParameterSpec 增量定义；默认普通模式保持 depth 与 angle 旧结果。参数检查只验证活动字段，模式改变保留非活动草稿但不执行其值。`directionality_percent` 默认 0，区间初值 100–200 nm、距离 30 nm；初值越出小模型域时明确报错，不静默夹紧。
- [ ] 复跑解析测试、`tests.test_structure_cad`、`tests.test_structure_editor_http`、`tests.test_process_cad_foundation`；运行编译、diff check。小提交 `feat(刻蚀): 添加深度区间参数契约`，两阶段审查。

## 任务 2：已有通道与有界几何候选

- [ ] 写真实体素 fixture：开口内竖直通道、圆／矩形开口、多个入口、起伏表面、阻挡层、封闭空腔。所有例子直接比较体素，不只检查三角形数量。
- [ ] 用解析出的高度带，测试入口只有当前 mask 的顶面路径：模型侧边、封闭空腔不是入口；目标表面不接触可达空气时拒绝。
- [ ] 写候选行为测试，固定种子后整步仅使用一次距离预算：

```python
before = model.grid.copy()
candidate = window_etch_candidate(model, resolve_window(model, parsed))
outside = ~resolved.band_mask
np.testing.assert_array_equal(candidate[outside], before[outside])
np.testing.assert_array_equal(candidate[before != target_id], before[before != target_id])
np.testing.assert_array_equal(model.grid, before)
```

这里 `parsed`、`resolved`、`target_id` 来自同一 fixture 的解析结果；测试实际代码使用同一个 `resolved` 调用候选函数，不重复解析移动参考面。

- [ ] 跑测试确认红灯，最小实现 `accessible_surface(model, resolved)` 与 `window_etch_candidate(model, resolved)`。返回完整候选 grid，不原地写模型。用既有空气和掩膜确定入口连通域；通过非目标材料不能取得新的种子。
- [ ] 按规格的球加 -Z 线段扩展实现有界计算：球半径 `(1-a)*r`、线段长 `a*r`。测试 0、50、100 的向下／横向／向上距离、共同边界及网格精度容差；0 的球形和 100 的纯 -Z 不可共用标签却共用同一结果。
- [ ] 目标删除集合还要满足种子连通和高度带约束。不能跨阻挡层跳删同材；不能重设种子反复膨胀超出整步距离。验证距离增大不减少合法删材，增大方向性不扩大横向最大范围。
- [ ] 工作数组预算检查在分配前；不创建体素两两距离矩阵，也不生成与距离立方成比例的无界核。若现有 SciPy 距离／连通算子不能符合冻结面中心及阻挡规则，先上报具体偏差，不自行改批准的几何定义。
- [ ] 先让候选测试通过，再在 `operations.construct` 分流并复用 `commit(..., additions=None)`；新增直接调用与 execute 事务测试，删材 owner 清零，其他 owner 不变，无变化明确失败。
- [ ] 复跑新测试、来源测试及 Structure 相关测试，编译、grid128；小提交 `feat(刻蚀): 实现受限深度区间几何去除`，两阶段审查。

## 任务 3：兼容协议与会话状态

- [ ] HTTP 测试先失败：用既有 add/edit 接口编辑模式和区间，执行后逐体素验证；无专用区间执行端点。
- [ ] 测试导入导出、保存加载、旧无新字段配方、任意步骤类型切换；same index 类型替换保留 step_id，复制产生新 ID。
- [ ] 测试未知模式、非法区间、没有通道与预算失败：正式 grid、来源、快照、timeline 和会话绑定不部分发布，保存文件不被失败候选覆盖。
- [ ] preflight 不对当前最终模型执行工艺；结构相关检查在真实执行时取本步骤的输入结构，不用未来步骤的结果当参考。
- [ ] 修复实际兼容路径的最小差异，保留普通 Etch 的物理兼容路径，不把几何百分比映射为真实速率。
- [ ] 新端点数量保持不变；ARCHITECTURE_TARGET 记录现有 payload 扩展与对应命名测试，DECISIONS 记录区间受限几何规则。全量 AGENTS 基线、编译、grid128；小提交并两阶段审查。

## 任务 4：检查器与独立单位

- [ ] ParameterPanel 先写失败测试：普通模式只显示旧字段；区间模式只显示其参数；切换 Opening plane／Fixed Z 切换深度与 Z 标签，非活动值不阻塞保存。
- [ ] 增量支持后端模式相关参数元数据，不在前端复制几何算法。只读参考 Z 必须取后端值；尚未执行时明确标识未解析，不能猜测当前模型表面。
- [ ] 测试方向性滑块与数字同步、键盘、aria 标签、中英文、每个长度参数独立 nm／µm 转换和规范化提交。带边界截断、已有通道、最高开口平面说明均有中文与英文断言。
- [ ] 工厂 fixture 从实际 Python 工厂更新，仅改 Structure Etch 对应内容；旧普通参数测试断言不减弱。
- [ ] 运行 `npm test -- --run --maxWorkers=1 --no-file-parallelism`、`npm run typecheck`、`npm run build`。串行命令用于环境隔离，不修改测试 timeout 或断言。小提交并两阶段审查。

## 任务 5：验收与发布

- [ ] 浏览器创建 300 nm 通道；区间 100–200 nm、距离 30 nm、方向性 0；检查局部扩腔及 X/Y/Z 剖面，区间外不变。
- [ ] 对比方向性 100、固定 Z 等价区间；变换视角确认不是贴图或纯视图伪造。验证只读参考面与真实执行前参考一致。
- [ ] 重跑全部专项、AGENTS 基线、编译、grid128，以及前端全量测试／类型检查／构建；最终独立审查关闭所有 BLOCK。
- [ ] 经批准合并到 main，仅推 backup 的 deepinwine 仓库。更新服务前保存并核对当前用户配方；不因启动自动加载优先级丢失当前编辑。

## 自检与执行顺序

规格 1、2 对应任务 1、4；规格 3 对应任务 2；规格 4 对应任务 2、3；规格 5 对应任务 4；规格 6 对应任务 1–5。步骤显示计划不变，本计划在其交付后执行。当前没有任何区间刻蚀实现完成的声明。
