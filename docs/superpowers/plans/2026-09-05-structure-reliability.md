# 结构生成可靠性修复计划

> 使用 subagent-driven-development，逐项测试和审查。用户已授权实现全部审查项，并在验证后合并、推送 deepinwine 的 main。

目标：关闭 2026-09-05 审查的 BLOCK-001 至 BLOCK-010，保持 ProcessStep/ProcessModel 兼容协议。
架构：真实 ParameterSpec 是输入约束来源；worker 保持服务器权威状态；不支持的几何/工艺明确失败。前端渲染后端输出，不计算工艺物理。
技术栈：Python、React/TypeScript、Three.js、可选 ViennaPS。

## 验证记录（2026-09-08）

前端、配方、demo、Hybrid 与 DRAM 实现已完成并分块提交。前端 265 项测试、
typecheck/build 通过；Python 全仓 488 项通过（2 项可选依赖跳过），规定的
183 项基线通过，grid=128 的五流程基准全部通过。

最终审查追加的导入原子性和指定掩膜缺失问题已修复：两个 worker 导入入口与
facade 共用候选构建；发布前完成反序列化、掩膜读取和模型分配。相关 28 项专项
测试通过，全仓 488 项复跑通过；最终复审结果以本次提交及交付报告为准。
DRAM 的固定掩膜仅保证 grid=64，其他分辨率明确拒绝。

## 1. 前端故障恢复（独立子任务）

文件：frontend/src/viewer/{meshLoader,ThreeViewer,viewerRuntime}、state/{AppStateContext,appReducer}、components/RecipeAssistant 及对应测试。
- [ ] 测试 manifest 失败可见；SiO2 首次失败后同 revision 重试成功；部分下载不缓存为完整结果。
- [ ] 测试 Run All 前两步成功第三步失败后同步 timeline/revision/preview，保留步骤错误。
- [ ] 测试 assistant 显示 validation.errors/top-level warnings；导入失败保留输入，成功后清空。
- [ ] 实现并运行 vitest 与 tsc；独立规格审查后代码质量审查。

## 2. 配方契约与生成

文件：recipe_planner/{parser,normalizer,validator,llm_planner,schema}.py、tcad_simulator.py、process_api/http.py、tests/test_recipe_reliability.py。
- [ ] 锁定 `在硅衬底上沉积100nm氧化硅` => 初始化+沉积、`0.1 um` =>100nm、`填W并CMP` =>两个动作、空/非法参数拒绝。
- [ ] 从 parameter_specs 导出 schema；明确兼容 thickness_nm→thickness、cd_nm→critical_dimension；depth_nm 不转换成无单位时间。
- [ ] 校验类型、枚举、材料、有限值、未知字段和前置步骤；主/备用解析接口统一调用 planner。
- [ ] 配方导入原子校验，避免半导入；保留现有兼容字段。
- [ ] 运行 unittest tests.test_recipe_reliability tests.test_recipe_planner tests.test_m31_llm_planner。

## 3. Demo 与域验收

文件：demos/flows.py、tcad_simulator.py 的 load_demo_flows、tests/test_m34_demos.py、tests/test_process_cad_demos.py。
- [ ] 去掉吞异常；让每个 demo 所有步骤成功，验证目标材料/窗口/沟槽/侧墙，拒绝纯衬底假成功。
- [ ] 修正真实参数、域余量、掩膜和工艺顺序；复用已验证的核心 primitives。
- [ ] 将高级 demo 接入唯一注册入口，并确保解析与导入可用。

## 4. Hybrid 状态边界

文件：process_backend/{hybrid,viennaps_backend}.py、geometry_scene/bridge.py、tests/test_m18_review_fixes.py、tests/test_m25_import.py。
- [ ] 测试 height_map 为占据层数、空列0；复用 ProcessModel 重建。
- [ ] 提取失败不能继续使用旧 canonical 切换；执行与恢复原子。
- [ ] 无法保留横向图形、断层或非闭合几何时明确拒绝；不把平面重建标作无损转换。
- [ ] 主 UI 明确当前执行引擎与可用性，通过已有契约提供可验证的模式路由；不支持步骤显式处理。

## 5. DRAM 可重放示例

文件：examples/run_dram_bl.py、examples/dram_narrow_bl_wide_active.json、tests/test_dram_reliability.py。
- [ ] 引入已提交示例而保留旧工作树未提交修改。
- [ ] 正式 ProcessStep 执行 JSON，正确配置物理域；保存真实每步快照。
- [ ] 实际量测 BL 数量/宽度、Active Si 宽度/高度、材料/连通性，验证输出而非输入常量。

## 6. 回归、审查与发布

- [ ] 更新 ADR/ROADMAP 与修复记录，说明真实能力和限制。
- [ ] 全部 Python unittest、前端 vitest/typecheck/build、py_compile、diff --check。
- [ ] tools/run_process_cad_baseline.py --grid 128 --output /tmp/tcad-structure-baseline.json。
- [ ] 独立最终审查并修复发现；分块提交，main 快进，git push backup main，核对远端 SHA。
