# 八类结构工艺与步骤编辑实现计划

> 面向 AI 代理：使用 subagent-driven-development；按 TDD 与两阶段独立审查交付。

**目标：** 八类新增目录、右侧原子换类型、项目晶圆设置和新增参数化工艺。
**架构：** 保留 Recipe/factory/model 边界，复用几何模块及共享场；前端读 factory 元数据。
**技术栈：** React/TypeScript、Python/NumPy、Three.js。

## 任务 1：结构工艺与原子替换

文件：tcad_simulator.py、structure_cad/operations.py、tests/test_structure_cad.py、
tests/test_structure_editor_http.py；factory、候选校验、HTTP set_step、场与快照。

- [ ] 先写失败测试：新增氧化/外延/去胶/掺杂 factories、真实体素与 doping 场变化，
  无物理方法调用、时间不增加；极值失败保持所有空间字段。
- [ ] 运行 `TCAD_SKIP_QT=1 MPLBACKEND=Agg python3 -m unittest tests.test_structure_cad`，
  观察新 factories 缺失的预期失败。
- [ ] 按设计实现纯几何/场操作，使用 `_require_writable_spatial_volumes` 和共享缓存刷新。
  测试形如 `assert np.any(model.doping > 0)`、`assert np.array_equal(before, model.grid)`。
- [ ] HTTP 测试 `/api/step/set` 请求 `{index: 1, name: 'Structure Etch', params: ...}`，
  成功同索引替换、失败 recipe/timeline 不变、旧 set 不带 name 仍可编辑。
- [ ] detached factory candidate 完整预检后一次赋值并失效后续状态，原名称保持。
- [ ] 小型中文 commit，不推送。

## 任务 2：八类目录、右侧候选和项目设置

文件：frontend/src/components、state/AppStateContext.tsx、api、i18n/catalogs.ts。

- [ ] 失败测试固定八类目录（光刻/刻蚀/沉积/氧化/外延/去胶/CMP/掺杂），填充为沉积模式；
  晶圆入口在项目设置，配方底层初始化保留。
  项目设置从 `exportRecipe` 取完整服务端配方，仅修改初始化和 domain，使用已有
  `importRecipe` 原子应用；先确认会清空旧几何/快照，保留后续步骤与元数据。
- [ ] `npm test -- --run` 观察目录/类型选择控件缺失。
- [ ] 元数据驱动右侧内联换类型候选；复用 AddStepDialog 的表单逻辑及单位安全防护，
  右侧候选不是新增弹窗，原参数自动保存控件在候选编辑时隐藏。
  取消不发请求；确认一次 setStep，等待最新草稿队列，非法/失败不执行或丢原类型。
- [ ] 使用 factory 默认值，只迁移自定义名和兼容材料；不迁移 thickness→depth。
- [ ] 掺杂可视化复用服务端场数据，不在前端计算工艺，不伪造材料身份。
- [ ] 补测试 `expect(replace).not.toHaveBeenCalled()`（取消/非法）、成功索引保持，
  语言切换、相机和 Viewer 挂载保持；`npm run build` 类型检查。
- [ ] 中文小型提交；根代理记录契约、ADR 与验证。

## 任务 3：审查及交付

- [ ] 全量前端、AGENTS 五模块 + Structure/editor、py_compile、grid128 基准。
- [ ] 根代理浏览器验证八类目录、沉积换刻蚀、取消与构建可见差异。
- [ ] 独立规格审查；修复并复审后再独立质量审查（AGENTS §9）。
- [ ] 记录局限与结果；经用户既有授权合并 main、仅 push backup/main，更新 8800 页面。
