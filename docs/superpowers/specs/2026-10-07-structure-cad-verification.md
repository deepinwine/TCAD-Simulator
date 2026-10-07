# Structure CAD 交付验证

用户优先级：先输入参数生成半导体结构，暂停新增物理仿真。
实现范围：六种 Structure 步骤、版图资产复用、独立单位、双语构建入口。
实现与修复提交：`cd0de95` 至 `3e8a71e`；架构决策 ADR-027。

## 审查结论

独立规格审查：SPEC PASS。原阻塞（程序化版图隐式夹取尺寸）已关闭，
Structure CD/pitch 明确量化与校验，旧曝光默认行为保持。
独立质量审查：APPROVE。React/Python/Three.js 职责、Recipe 兼容、物理暂停、
版图资产、空间字段/缓存、canonical 后端、旧 Exposure、极值与验证八项边界均 PASS。
超大厚度错误及只读共址字段、HTTP 撤销/重做内容比较两个 NB 已关闭。
浏览器发现的材料编号回显问题已修复，并加入参数面板真实数据回归。

## 最终验证（2026-10-07）

Python 使用 `/opt/anaconda3/bin/python3`，环境 `TCAD_SKIP_QT=1 MPLBACKEND=Agg`，
`PYTHONPYCACHEPREFIX` 位于 `/tmp`。

- AGENTS 五模块加 `tests.test_structure_cad tests.test_structure_cad_http`：
  200 tests，OK，70.430 秒（五模块 186 项，结构专项 14 项）。
- `npm test -- --run`：24 文件、387 tests，全部通过。
- `npm run build`（含 `tsc --noEmit`）：通过。
- `py_compile tcad_simulator.py tools/*.py structure_cad/*.py recipe_planner/schema.py`：通过。
- `tools/run_process_cad_baseline.py --grid 128`：五个旧示例全部成功。
- 实际浏览器：载入结构示例，六步构建完成，三材料可见；材料正确回显；
  深度从 40 nm 修改为 30 nm，构建至刻蚀步骤成功并显示沟槽。

专项覆盖：不调用物理方法且时间不增加；尺寸、斜壁、底面、阻挡层/空洞；
非法/超域/只读字段失败原子性；精确资产 revision/SHA；版图预览与执行一致；
三材料 STL、快照与撤销/重做内容；语言切换与 Viewer 挂载保持。

## 局限

这是参数化体素几何构建，不是物理精确 TCAD 仿真。示例网格 5 nm，长度四舍五入
到最近网格，误差不超过半格；斜壁存在体素阶梯。仅顶面 +Z；不是共形沉积或
真实刻蚀速率模型。旧仿真配方仍保留，通过“结构构建示例”进入纯几何流程。
既有测试环境 jsdom canvas 提示与前端 bundle 大小警告不影响本次验证。
