# 结构编辑器交付验证

用户批准范围：左侧步骤、中间 3D、右侧参数和底部时间线；先配置再添加，
保存有效草稿后构建。保持参数化 Structure CAD，不新增物理求解。
基线：`89da158`。设计与执行计划见同日 structure-editor-ui 文档。

## 审查与修复

独立规格审查通过。中等窗口双侧最大栏宽裁剪问题已在 `8217367` 修复：
栏宽按实际容器耦合限制，缩窄时自动调整；Viewer 不重挂，参数草稿保留。
浏览器实测 1000 px、901 px 双侧 End 后，最右边界分别为 1000 px、901 px。

独立质量审查的数值溢出阻塞项已在 `98dbb14` 关闭：canonical/display 换算
异常变成字段错误，保留输入和单位，禁止提交；不改变共享单位转换的抛错契约。
浏览器输入 `1e308 µm` 显示错误且禁用确认，改回 `0.035 µm` 后恢复可提交。
HTTP 契约测试位置在 `0e02a5c` 补充，原 name-only 添加继续兼容。
新增文案在 `9afa650` 集中到对等中英文目录。最终独立质量审查：APPROVE，
React、Three.js、Python、Recipe 兼容链、HTTP 加法兼容、LayoutAdapter、可选
ViennaPS、canonical 单位与双语目录八项边界均 PASS，无待修阻塞项。

## 验证证据

Python 使用 `/opt/anaconda3/bin/python3`，设置 `TCAD_SKIP_QT=1 MPLBACKEND=Agg`，
`PYTHONPYCACHEPREFIX=/tmp/tcad-editor-final-cache`。

```sh
python3 -m unittest tests.test_process_cad_foundation tests.test_process_cad_primitives \
  tests.test_process_cad_demos tests.test_webui_viewer_contract tests.test_webui_cad_shell \
  tests.test_structure_editor_http tests.test_structure_cad tests.test_structure_cad_http
```

204 tests，OK，75.645 秒。后续修复只涉及前端和文档。
`py_compile tcad_simulator.py tools/*.py tests/test_structure_editor_http.py` 退出 0。
`tools/run_process_cad_baseline.py --grid 128` 退出 0，五个旧示例均成功。
最终 `npm test -- --run`：27 文件、410 tests，全部通过。
`npm run build`（含 `tsc --noEmit`）退出 0；`git diff --check` 退出 0。

浏览器操作验证：

- 编辑刻蚀深度至 30 nm，应用并构建到此步，前四步有有效快照，后续标记待构建。
- 新增沉积：Copper、`0.035 µm`，服务端保存为 35 nm；自定义名称保留。
- 取消配置不创建步骤；确认后自动选中新步骤，右侧出现对应材料和尺寸。
- 窄屏工具栏不再覆盖其他按钮，结构示例加载操作成功。
- 中等宽度面板限宽与极值输入的错误恢复均实测通过。

## 已知局限

结构仍为参数化体素几何，不是物理 TCAD；本次不改变算法精度或网格量化规则。
复杂旧步骤默认值保留；没有 factory template 时保持旧添加入口，不捏造 schema。
既有 jsdom canvas/navigation 提示及 bundle 大小警告为非阻塞项。
