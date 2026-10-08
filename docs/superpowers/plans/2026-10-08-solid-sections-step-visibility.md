# 实体剖面与步骤眼睛实现计划

> 面向 AI 代理：使用 subagent-driven-development，顺序实现、规格审查后质量审查。

**目标：** 实体材料剖面，以及不修改正式配方的跳步重建预览。
**架构：** 截面复用 /api/slice；重建在独立 Python model 中进行，客户端只显示结果。
**技术栈：** 既有 Python/NumPy、React/TypeScript、Three.js。

## 前置条件

- [ ] 八类步骤编辑 Task 2 的 BLOCK-001 修复并通过两阶段审查。
- [ ] 真实掺杂显示独立任务完成，或明确在视图源切换时暂时关闭；禁止显示正式模型的场叠加隔离模型。

## 任务 1：真实材料截面封口

文件：frontend/src/api/types.ts、client.ts；新建 viewer/sectionTexture.ts 与测试；
修改 viewerRuntime.ts、ThreeViewer.tsx 与对应测试。

- [ ] 先定义并测试现有 GET /api/slice 客户端映射和 u16 严格解析，形状必须为两维正整数，
  dtype=u16，字节数等于 rows*columns*2，拒绝截断、超预算、无效 axis/index。
  示例断言：`expect(() => decodeMaterialSlice({...fixture, data_b64: ''})).toThrow()`。
- [ ] 运行 `npm test -- --run src/viewer/sectionTexture.test.ts src/api/client.test.ts`，
  确认行为测试失败，再实现材质 ID→RGBA 映射；空气 alpha=0、隐藏材质 alpha=0。
  示例：`expect(Array.from(pixelForAir)).toEqual([0, 0, 0, 0])`。
- [ ] 为 X/Y/Z 截面放置、体素中心、nm/µm 和网格 axis transpose 写固定小体素 fixture。
  切面 extent 使用 model domain，不以部分可见网格包围盒猜测整个网格坐标。
- [ ] 给 runtime 添加截面纹理平面，应用其他开启的 clippingPlanes，
  排除切面自身的裁剪误差；相机、原网格和正式状态不变。
- [ ] 测试快速滑动/模型刷新过期响应、空模型、边界、纹理和材质释放。
  ThreeViewer 测试断言 `expect(runtime.mount).toHaveBeenCalledTimes(1)`。
- [ ] 运行 `npm test -- --run`、`npm run typecheck`、`npm run build`，小型中文提交；
  独立 SPEC 与质量审查，修复阻断问题后再继续。

## 任务 2：隔离重建后端

文件：新建 structure_cad/visibility_preview.py 与 tests/test_structure_visibility_preview.py；
tcad_simulator.py 的 worker/HTTP 路由、tests/test_structure_editor_http.py；
docs/ARCHITECTURE_TARGET.md 和 docs/DECISIONS.md 加法契约。

- [ ] 写失败测试：隐藏沉积、刻蚀、去胶；相同材料不同步骤分别排除；
  正式 disabled 保留；截止点后步骤不执行；初始化不能隐藏。
  示例：`np.testing.assert_array_equal(formal.grid, before_grid)`，
  `self.assertEqual(formal.snapshot_state(), before_snapshot)` 对数组字段逐项比较。
- [ ] 运行 `env TCAD_SKIP_QT=1 MPLBACKEND=Agg /opt/anaconda3/bin/python3 -m unittest
  tests.test_structure_visibility_preview`，确认缺失行为红灯。
- [ ] 用 detached candidate factories 和既有 Structure 工艺执行构建隔离 model；
  先预检所有候选与 grid/voxel/内存预算，再执行，错误注明原步骤 index。
  不支持旧物理步骤时显式拒绝，不能调用物理求解或猜测替代。
- [ ] POST /api/structure/visibility_preview 请求 hidden_indices、through_index，
  返回 preview_token 和 model/source revision；token 只属于当前 session，最多一个活动结果。
  现有 manifest/STL/elements/slice 可选 preview_token 参数，无 token 的旧行为不变。
  recipe/model 变化失效 token，错误 token 不得回落到正式模型伪装成功。
- [ ] HTTP 测试配方、状态、timeline/history、正式 revision 和保存内容请求前后相同；
  token 跨 session 拒绝、过期拒绝、失败无候选泄漏。
- [ ] 运行 Structure/editor HTTP 专项、AGENTS 基线、compile，提交并两阶段审查。

## 任务 3：步骤眼睛与视图源

文件：ProcessFlowPane.tsx/test、AppStateContext.tsx/test、api client/types、
viewer meshLoader/ThreeViewer、i18n/catalogs.ts。

- [ ] 写失败测试：每个普通步骤有独立 eye button，点击不改变 selected index 或 enabled；
  初始化无眼睛；pending type candidate 阻止隐藏；新配方/结构编辑清空索引集合。
- [ ] 请求等待最新有效草稿保存完成，以当前正式截止点创建隔离预览。
  快速多次点击取消旧请求，使用 generation guard，错误保留可恢复正式视图。
  示例：`expect(api.setStep).not.toHaveBeenCalled()`，
  `expect(api.runAll).not.toHaveBeenCalled()`；眼睛不能用这两个接口实现。
- [ ] 统一传递 preview_token 给 meshes、真实 dopant points 和 sections，
  在来源切换时不能混用缓存，Viewer 不重挂、相机不重置。
- [ ] 全部恢复显示时立即切回正式模型，清除预览状态；提供“恢复正式结构”按钮。
  中文/英文复制、键盘操作、aria-pressed 和 loading/error 均有测试。
- [ ] 全量前端/typecheck/build + Python 回归，提交并两阶段审查。

## 任务 4：浏览器与交付

- [ ] 浏览器验证实心硅/真实孔洞、X/Y/Z 组合剖面、隐藏沉积和刻蚀、失败与恢复；
  对比操作前后正式配方导出、timeline 和 geometry revision 无变化。
- [ ] 运行 AGENTS compile、全量回归、grid128 基准，记录真实输出与明确限制。
- [ ] 最终审查无阻断后按既有授权合并并仅推 backup/main，更新 localhost:8800。
