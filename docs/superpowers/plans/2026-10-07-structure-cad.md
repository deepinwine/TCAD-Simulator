# 参数化结构构建实现计划

> 按 subagent-driven-development 完成实现、规格审查、质量审查和集成。

目标：交付纯几何结构配方及浏览器可用入口。
架构：ProcessStep 加法扩展；Python 构建体素候选；React 使用既有接口；Three.js 渲染。

## Task 1：几何构建与界面闭环

文件：新增 `structure_cad/operations.py`（几何操作）、`structure_cad/__init__.py`、
`structure_cad/recipes.py`（fresh demo）、`tests/test_structure_cad.py`、
`tests/test_structure_cad_http.py`。修改 `tcad_simulator.py`（六个 Step、factory、公共
demo 注册及 Exposure mask resolution helper）、`recipe_planner/schema.py`（新
Pattern 的掩膜校验）、前端 Toolbar、i18n、ParameterPanel（新文案），并新增针对测试。

- [ ] 先加入几何尺寸测试：5 nm 网格下20 nm沉积=4层、15 nm刻蚀=3层、非目标材料
  阻挡、沉积越界保持原数组、侧壁底部开口小于顶部、Fill保持已有材料、Planarize高度。
- [ ] 运行新增测试，确认因缺少 Structure factory 或几何实现失败。
- [ ] 实现 `deposit(model, material, thickness_nm, coverage)`、
  `etch(model, material, depth_nm, sidewall_angle_deg)`、`fill(model, material, height_nm)`、
  `planarize(model, height_nm)`，以候选数组和已校验更新发布，维护字段及缓存。
- [ ] Structure Pattern 继承 ExposureStep 以复用服务注入、文件加载、序列化与资产事务。
  从 ExposureStep 提取 `_resolve_mask_override(model)` 保持原execute行为与metrics；
  Pattern execute只调用 mask reader 和 `_generate_mask_density >= 0.5`，直接设置开口。
- [ ] 六个 factory 中 Wafer仅材料/厚度；Deposit材料/厚度/coverage；Etch材料/深度/角度；
  Fill材料/高度；Planarize高度。长度spec明确dimension/canonical_unit/display_units。
- [ ] 公共demo registry加入 `Structure CAD — Trench`，调整精确registry断言增加这一项，
  不降低其他测试断言；示例本身按spec参数固定。
- [ ] 加入HTTP端到端测试，验证导入、asset保存绑定Pattern、执行、manifest/STL、失败原子性。
- [ ] 前端增加示例入口及纯Structure配方构建说明/按钮翻译；沿用现有API与draft gate。
  参数文案中英文均可读，新参数仍可逐字段选单位。按钮测试验证导入真实demo blob。
- [ ] 运行新增Python测试、前端全量/typecheck/build及既有Exposure回归；小粒度中文提交。

## Task 2：审查、验证与交付

- [ ] 独立规格审查：逐条核对设计验收；发现问题由实现者按TDD修复。
- [ ] 独立质量审查：完整diff按AGENTS §9审查，所有BLOCK修复后复审。
- [ ] 执行AGENTS五模块回归、py_compile、grid128五demo基准、结构专项及前端全量。
- [ ] 浏览器试运行结构示例，检查结构与版图编辑入口，记录网格分辨率局限。
- [ ] 记录测试和审查证据，合并main，只推backup/main，核验本地与远端SHA。
