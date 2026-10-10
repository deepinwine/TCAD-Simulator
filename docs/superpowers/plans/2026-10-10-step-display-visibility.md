# 步骤眼睛纯显示实现计划

> 面向 AI 代理：使用 subagent-driven-development；顺序实现、规格审查、质量审查。

**目标：** 按步骤隐藏当前剩余实体，点击不执行工艺。
**架构：** 正常构建记录 owner；Python 只读输出按 owner/material 分组的封闭显示网格
与来源截面；React 保存隐藏 step_id 集合，Three.js 更新可见性。
**技术栈：** 现有 Python/NumPy/网格提取、React/TypeScript、Three.js。

## 任务 1：来源记录与稳定身份（已提交，须完成审查）

文件：`structure_cad/display_provenance.py`、`structure_cad/operations.py`、
`recipe_planner/schema.py`、`tcad_simulator.py`、`tests/test_structure_display_provenance.py`。

- [x] 审查 `6ca6896..788c531`：显式新增区域、同材步骤、减材清理、旧来源未知、
  snapshot/spill/rollback、保存加载稳定 UUID、展示序列化不修改 identity。
- [x] 运行 `TCAD_SKIP_QT=1 MPLBACKEND=Agg /opt/anaconda3/bin/python3 -m unittest
  tests.test_structure_display_provenance tests.test_structure_cad`，预期全部通过。
- [x] 规格与质量审查无 BLOCK 后进入任务 2；不能用前端 material ID 隐藏代替来源。

任务 1 验证记录：质量审查独立运行 53 项来源与结构测试通过（14.981 秒）；
实现回归运行 252 项测试通过（99.221 秒）。损坏来源加载的模型与会话发布顺序、
实际恢复步骤绑定和解压前预算检查已修复并复审通过。尚未合并或更新正式服务。

## 任务 2：只读步骤显示数据

创建 `structure_cad/display_geometry.py`、`tests/test_structure_display_geometry.py`、
`tests/test_structure_display_http.py`；修改 worker/HTTP 路由及 API 契约文档。

- [ ] 先写小型真实 fixture：两次同材沉积，后续刻蚀；分组键为 `(owner_id, mat_id)`，
  每个非空分组单独封闭；unknown owner 也有网格但不能绑定到猜测步骤。
  对每个分组验证返回坐标、体积及 shared boundary，删除区域不在任何输出中。
  核心断言：`np.testing.assert_array_equal(model.grid, before_grid)`。
- [ ] 跑新测试，确认因缺少显示数据行为而失败，再复用既有网格提取与二进制编码，
  不在前端造几何、不修改 canonical GeometryScene 的材料聚合契约。
- [ ] 新增 GET `/api/structure/display/manifest`：revision、domain、owner→step_id、
  当前实体计数、分组网格摘要与不可用原因；GET `/api/structure/display/mesh`：
  按 revision、owner_id、mat_id 读取二进制显示网格；GET `/api/structure/display/slice`：
  同轴同索引的材料 u16 与 owner u32，按既有三轴方向排列。
- [ ] revision 不匹配明确拒绝；未知分组、错误 method、跨会话数据、空模型有测试。
  预算至少限制网格数、总三角形及二进制缓存字节；不截断伪装成功。
  按 model revision 缓存，重复读取不重新提取；旧正式端点保持原行为。
- [ ] HTTP 比较前后 recipe、grid、snapshot、timeline、revision 和保存文件一致；
  实测未调用 execute。新端点同提交入 ARCHITECTURE_TARGET 表和命名 HTTP 测试套件。
- [ ] 跑专项、AGENTS 基线、compile、grid128 基准；小提交后两阶段审查。

## 任务 3：眼睛按钮与渲染过滤

修改 `frontend/src/components/ProcessFlowPane.tsx`、API client/types/schemas、
`frontend/src/state/AppStateContext.tsx`、viewer meshLoader/runtime/materialSections、
`frontend/src/i18n/catalogs.ts` 及其测试；独立新增 `viewer/stepVisibility.ts` 测试。

- [ ] TDD：独立 eye button 不嵌入步骤选择按钮；点击不改 selected/enabled，
  初始化无眼睛，无剩余实体或来源未知禁用并解释；中英文、键盘与 aria-pressed 对等。
- [ ] 来源网格准备完成前禁用眼睛，数据错误保留可恢复正式视图，不能显示假成功。
  状态以 stable step_id 存储，不用数组 index；载入新配方清空，结构变化清除失效身份。
- [ ] 网格、拾取、材质透明度与剖面同时应用隐藏来源；材质隐藏仍叠加生效。
  对眼睛动作断言 `expect(api.runAll).not.toHaveBeenCalled()` 与
  `expect(api.setStep).not.toHaveBeenCalled()`，同 revision 不下载或重新提取网格。
- [ ] 保留 camera/Viewer 实例；异步 generation/abort、revision cache key、
  空数据、快速刷新与 GPU 资源释放都有回归。
- [ ] 运行 `npm test -- --run`、`npm run typecheck`、`npm run build`，两阶段审查。

## 任务 4：浏览器验收与发布

- [ ] 同材两次沉积分开隐藏，隐藏外层后内层不缺面；刻蚀结果不被恢复。
- [ ] X/Y/Z 与组合剖面来源一致；相机不重置；无执行请求；错误可恢复正式显示。
- [ ] fresh Python/前端回归、compile、grid128、最终审查，记录限制与真实输出。
- [ ] 按所有者授权合并并仅 push backup/main；更新本地服务前保存并核对当前配方。
