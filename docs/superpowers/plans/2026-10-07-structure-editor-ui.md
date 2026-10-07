# 结构编辑工作区实现计划

> 使用 subagent-driven-development：一个端到端实现任务，规格审查后质量审查。

目标：用户知道每步是什么、哪里编辑、修改后如何生成结构。
架构：React 展示/编辑现有 schema，Python 原子添加候选；Three.js 仅渲染。

## Task 1：完整编辑闭环

文件：新增 components/stepPresentation.ts 及测试、AddStepDialog.tsx 及测试、
WorkspaceLayout.tsx 及测试；修改 App、ProcessFlowPane、ParameterPanel、
StepStructureBar、Toolbar、styles、i18n、AppStateContext 及对应测试；
API types/client/parser 与最小 Python init/recipe_add 扩展、HTTP专项。

- [ ] TDD 先测 numeric SiO2 + thickness80 展示“沉积 · SiO₂ · 80 nm”，旧标题失败；
  `npm test -- --run src/components/stepPresentation.test.ts`，实现展示helper后绿。
- [ ] 测全部草稿保存后 runUntil，以及保存失败/invalid 禁止执行；用现有 saveQueue
  及 mutationGate 实现 `applyAndBuildSelected()`，不自行绕过互斥。
- [ ] 新增配置取消/校验/一次创建的失败测试，再扩展 optional init模板与add params；
  服务器用现有 schema validator 校验 before append，不新增路由、不改算法。
- [ ] 表单复用 parameter schema/单位转换；类型可选、关键字段有说明、名字可填。
  中文与英文均可用；保持旧name-only API调用兼容。
- [ ] 先测三栏顺序、键盘分隔调宽、Viewer不卸载，再实现 responsive WorkspaceLayout；
  分隔条 aria role separator + 值与keyboard、上下限，拖动使用pointercapture。
- [ ] 参数检查器加入编辑提示、状态与apply/build动作；工具栏主操作紧凑，
  次要配方操作可展开。不得删除已有mask/导入/导出/undo/redo/语言操作。
- [ ] `npm test -- --run`、`npm run build`、Python新增HTTP及Structure专项，全部绿后小提交。

## Task 2：交付验证

- [ ] 独立规格审查，修全部阻塞，再质量审查按AGENTS §9。
- [ ] AGENTS五模块+Structure专项、py_compile、grid128基准、前端全量/typecheck/build。
- [ ] 浏览器实际添加/修改/应用构建并确认三维更新，记录验证与局限。
- [ ] 审查APPROVE后合并main，push backup/main并核对远端SHA；保留用户原有文件。
