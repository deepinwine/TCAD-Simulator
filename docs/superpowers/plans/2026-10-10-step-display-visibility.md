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

- [x] 先写小型真实 fixture：两次同材沉积，后续刻蚀；分组键为 `(owner_id, mat_id)`，
  每个非空分组单独封闭；unknown owner 也有网格但不能绑定到猜测步骤。
  对每个分组验证返回坐标、体积及 shared boundary，删除区域不在任何输出中。
  核心断言：`np.testing.assert_array_equal(model.grid, before_grid)`。
- [x] 跑新测试，确认因缺少显示数据行为而失败，再复用既有网格提取与二进制编码，
  不在前端造几何、不修改 canonical GeometryScene 的材料聚合契约。
- [x] 新增 GET `/api/structure/display/manifest`：revision、domain、owner→step_id、
  当前实体计数、分组网格摘要与不可用原因；GET `/api/structure/display/mesh`：
  按 revision、owner_id、mat_id 读取二进制显示网格；GET `/api/structure/display/slice`：
  同轴同索引的材料 u16 与 owner u32，按既有三轴方向排列。
- [x] revision 不匹配明确拒绝；未知分组、错误 method、跨会话数据、空模型有测试。
  预算至少限制网格数、总三角形及二进制缓存字节；不截断伪装成功。
  按 model revision 缓存，重复读取不重新提取；旧正式端点保持原行为。
- [x] HTTP 比较前后 recipe、grid、snapshot、timeline、revision 和保存文件一致；
  实测未调用 execute。新端点同提交入 ARCHITECTURE_TARGET 表和命名 HTTP 测试套件。
- [x] 跑专项、AGENTS 基线、compile、grid128 基准；小提交后两阶段审查。

任务 2 验证记录：实现提交 `ce94f1f`，预算预检修复 `26b9b1`；两阶段审查均
APPROVE。质量审查独立运行 27 项显示与 M2 契约测试通过（15.405 秒），主代理
独立运行 19 项专项、完整生命周期与文档一致性测试通过（4.563 秒）。实现侧运行
187 项 AGENTS 基线、82 项结构与桥接回归、编译及 128³ 五个流程基准通过；
预算修复后重新跑 19 项专项与契约检查，未重复全量基准。前端按钮尚未接入，
正式服务未重启，尚未合并或推送；发布在任务 4 验收后进行。

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

## 2026-10-11 验收与复审记录

任务 3 实现范围为 `a57bab7..48f77f6`。独立规格审查发现切片请求失败后，
眼睛可能重新请求切片；`9359b48` 修复并通过定向复审。质量审查提出来源身份
及累计网格预算两项防御性建议，`48f77f6` 补齐 UUID、uint32、唯一性、映射、
累计三角形／字节预算及下载长度校验。最终 SPEC、QUALITY 均为 APPROVE，
无剩余 BLOCK 或 NB。任务 1、2 的既有双阶段审查结论保持有效。

主代理在最终代码上独立运行：

- `npm test -- --run --maxWorkers=1 --no-file-parallelism`：35 个文件，613 项
  通过，18.79 秒。串行执行用于隔离此前并行工作进程停顿，不修改断言或超时。
- `npm run typecheck`、`npm run build` 通过；最终补丁实现者重新运行同命令
  通过。现有 jsdom canvas/navigation 提示与构建 chunk 大小警告仍存在。
- AGENTS 五模块加显示来源、网格、HTTP 三模块：231 项通过，86.772 秒。
- `py_compile tcad_simulator.py tools/*.py` 和 `git diff --check` 通过。
- `run_process_cad_baseline.py --grid 128`：五个流程全部成功，退出 0。

隔离浏览器服务使用独立临时目录与 8812 端口，未重启正式服务。真实双层同材
沉积及圆孔刻蚀配方验证了分别隐藏、下层封闭表面、刻蚀孔保留、恢复显示、
Y 实体剖面、X/Y/Z 组合及材料显隐叠加。零请求、相机 identity/pose、失败恢复
由实际 runtime/section manager 的专项测试验证，未把截图当成请求次数证据。

显示数据首次准备仍有内存与网格生成成本；眼睛操作仅本地过滤。旧未知来源
保持可见且不可隐藏。此验收不宣称已实现深度区间刻蚀，也未更新正式服务。
发布前确认 deepinwine 远端 main 为 `6ca6896`；推送结果另以实际 Git 输出核对。
