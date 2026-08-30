# Process CAD 五流程 Golden Baseline 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 建立公开、与 WebUI 无关的示例流程注册表，新增 W Plug + CMP 与 Basic BEOL 两套可执行流程，并让 Golden 测试与基准运行器覆盖全部 5 套流程。

**架构：** `load_demo_flows(material_db)` 成为唯一流程定义入口，旧 `_webui_demo_recipes()` 仅作兼容包装。所有配方继续使用现有 `PROCESS_STEP_FACTORIES -> ProcessStep.execute(model) -> ProcessModel` 边界；新流程只组合现有 Etch、Deposition、Fill、Strip 和 CMP 原语。

**技术栈：** Python 3.10+、NumPy、现有 unittest、现有体素 `ProcessModel`、JSON 配方 blob。

**设计规格：** `docs/superpowers/specs/2026-08-30-process-cad-golden-flows-design.md`

---

## 文件职责

- `tcad_simulator.py`：公开流程注册表、5 套 canonical 配方及 WebUI 兼容包装。
- `tests/test_process_cad_demos.py`：注册表契约、逐步骤 checkpoint、两套新流程的 Golden 结构验收和 SciPy fallback。
- `tools/run_process_cad_baseline.py`：通过公开注册表运行 5 套流程，并输出新增流程的轻量语义检查。
- `tests/test_webui_cad_shell.py`：锁定 32³ CLI 基准报告包含 5 套流程。
- `README.md`：更新基准数量和公开加载入口说明。
- `docs/ROADMAP_PROCESS_CAD.md`：在所有验证通过后关闭 M1 五流程 Golden 项和对应 Backlog。

### 任务 1：建立公开流程注册边界

**文件：**

- 修改：`tests/test_process_cad_demos.py`
- 修改：`tcad_simulator.py`（定位 `_webui_demo_recipes` 与 Worker `demo_recipes` 初始化）

- [ ] **步骤 1：编写公开入口失败测试**

在 `DemoRecipeRegistryTests` 中新增测试，先只验证现有 3 套流程的公开入口、兼容包装与深度隔离：

```python
def test_public_registry_is_canonical_and_legacy_wrapper_is_isolated(self):
    database = tcad.MaterialDatabase()

    public = tcad.load_demo_flows(database)
    legacy = tcad._webui_demo_recipes(database)

    self.assertEqual(public, legacy)
    self.assertIsNot(public, legacy)
    public["Basic Trench"]["steps"][0]["params"]["thickness_nm"] = -1
    fresh = tcad.load_demo_flows(database)
    self.assertGreater(fresh["Basic Trench"]["steps"][0]["params"]["thickness_nm"], 0)
```

- [ ] **步骤 2：运行测试并确认正确红灯**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-registry-red \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_process_cad_demos.DemoRecipeRegistryTests.test_public_registry_is_canonical_and_legacy_wrapper_is_isolated -v
```

预期：FAIL，错误为 `AttributeError: module 'tcad_simulator' has no attribute 'load_demo_flows'`。

- [ ] **步骤 3：实现最小公开入口和兼容包装**

只将现有定义行从 `_webui_demo_recipes` 改名为 `load_demo_flows`；从局部 `_step()` 到 3 套配方的完整函数体保持不变。随后在该函数定义结束后添加兼容包装：

```diff
-def _webui_demo_recipes(material_db: MaterialDatabase) -> Dict[str, Dict[str, Any]]:
-    """Return fresh, portable definitions for the built-in Process CAD demos."""
+def load_demo_flows(material_db: MaterialDatabase) -> Dict[str, Dict[str, Any]]:
+    """Return fresh, portable definitions for the built-in Process CAD flows."""
```

```python
def _webui_demo_recipes(material_db: MaterialDatabase) -> Dict[str, Dict[str, Any]]:
    """Compatibility wrapper for callers that still use the legacy WebUI helper."""
    return load_demo_flows(material_db)
```

将 Worker 初始化中的：

```python
"demo_recipes": _webui_demo_recipes(material_db),
```

改为：

```python
"demo_recipes": load_demo_flows(material_db),
```

- [ ] **步骤 4：运行注册表与 demo 回归**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-registry-green \
  /opt/anaconda3/bin/python3 -m unittest tests.test_process_cad_demos -v
```

预期：现有 demo 测试全部 PASS。

- [ ] **步骤 5：提交公开入口**

```bash
git add tcad_simulator.py tests/test_process_cad_demos.py
git diff --cached --check
git commit -m "refactor(示例): 建立公开流程注册入口"
git push backup HEAD:refs/heads/zcode/process-cad-shell
```

### 任务 2：用 TDD 新增 W Plug + CMP

**文件：**

- 修改：`tests/test_process_cad_demos.py`
- 修改：`tcad_simulator.py`（定位 `load_demo_flows`）

- [ ] **步骤 1：扩展 checkpoint 和编写 W Plug 红灯测试**

先将模块级名称改为 4 套，确保 `setUpClass()` 会真实执行新流程；同时把原测试名 `test_registry_returns_three_canonical_portable_recipes` 改为 `test_registry_returns_canonical_portable_recipes`：

```python
DEMO_NAMES = (
    "Basic Trench", "Spacer Formation", "Bonding + Thinning", "W Plug + CMP",
)
```

将 `geometry_checkpoint()` 的材料集合扩展为：

```python
for material_name in (
    "Silicon",
    "Silicon Dioxide",
    "Photoresist",
    "Polysilicon",
    "Silicon Nitride",
    "Tungsten",
    "Copper",
    "Tantalum",
):
```

在注册表测试中要求第 4 个名称为 `W Plug + CMP`，并增加严格步骤序列：

```python
self.assertEqual(
    [step["name"] for step in demos["W Plug + CMP"]["steps"]],
    [
        "Initialize Wafer", "Deposition", "Spin Resist", "Mask Exposure",
        "Resist Develop", "Etch", "Strip", "Fill", "Deposition", "CMP",
    ],
)
```

在 `DemoHeadlessAcceptanceTests` 中新增：

```python
def test_w_plug_cmp_removes_overburden_and_keeps_contact_plugs(self):
    database, model, _elapsed, trace = self.runs["W Plug + CMP"]
    tungsten = database.id_for("Tungsten")
    silicon = database.id_for("Silicon")
    resist = database.id_for("Photoresist")
    fill = next(item for item in trace if item["instance_name"] == "Fill tungsten contacts")
    overburden = next(item for item in trace if item["instance_name"] == "Deposit tungsten overburden")
    polish = next(item for item in trace if item["instance_name"] == "Polish tungsten to oxide stop")

    self.assertGreater(fill["after"]["counts"]["Tungsten"], fill["before"]["counts"]["Tungsten"])
    self.assertTrue(overburden["after"]["full_planes"]["Tungsten"])
    self.assertLess(polish["after"]["counts"]["Tungsten"], polish["before"]["counts"]["Tungsten"])
    self.assertFalse(polish["after"]["full_planes"]["Tungsten"])
    self.assertFalse(np.any(model.grid == resist))
    self.assertFalse(np.any(np.all(model.grid == tungsten, axis=(0, 1))))
    self.assertLessEqual(int(model.height_map.max()) - int(model.height_map.min()), 1)

    coords = np.argwhere(model.grid == tungsten)
    lowest = coords[coords[:, 2] == coords[:, 2].min()]
    self.assertTrue(any(int(model.grid[x, y, z - 1]) == silicon for x, y, z in lowest if z > 0))
```

- [ ] **步骤 2：运行 W Plug 测试并确认正确红灯**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-wplug-red \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_process_cad_demos.DemoRecipeRegistryTests.test_demo_sequences_express_the_designed_process_order \
  tests.test_process_cad_demos.DemoHeadlessAcceptanceTests.test_w_plug_cmp_removes_overburden_and_keeps_contact_plugs -v
```

预期：FAIL，注册表缺少 `W Plug + CMP`。

- [ ] **步骤 3：实现 contact mask 与 W Plug 配方**

在 `load_demo_flows()` 中创建 4 个分离方孔：

```python
contact_mask = np.zeros((mask_size, mask_size), dtype=np.uint8)
for x0 in (7, 21):
    for y0 in (7, 21):
        contact_mask[x0:x0 + 4, y0:y0 + 4] = 1
```

新增以下完整的 10 步 `w_plug_steps`：

```python
w_plug_steps = [
    _step("Initialize Wafer", "300 nm contact silicon", {"thickness_nm": 300.0}),
    _step(
        "Deposition", "Deposit contact dielectric",
        {"material": "Silicon Dioxide", "thickness": 100.0, "method": "CVD", "coverage": "Full wafer"},
    ),
    _step("Spin Resist", "Contact photoresist", {"thickness_nm": 40.0}),
    _step(
        "Mask Exposure", "Expose four contacts",
        {"advanced_enable": 1, "mask_mode": "Custom", "mask_name": "Four contacts", "dose": 80.0},
        custom_mask=contact_mask.tolist(), mask_name="Four contacts",
    ),
    _step(
        "Resist Develop", "Open contact resist",
        {"time": 60.0, "rate": 300.0, "contrast": 3.0, "threshold": 10.0},
    ),
    _step(
        "Etch", "Etch contact dielectric",
        {"material": "Silicon Dioxide", "chemistry": "Dry", "time": 60.0,
         "rate_override": 1200.0, "selectivity": 20.0, "sidewall": 90.0},
    ),
    _step("Strip", "Strip contact resist", {"materials": "Photoresist"}),
    _step(
        "Fill", "Fill tungsten contacts",
        {"material": "Tungsten", "max_depth_nm": 100.0, "direction": "top", "include_sealed": False},
    ),
    _step(
        "Deposition", "Deposit tungsten overburden",
        {"material": "Tungsten", "thickness": 30.0, "method": "CVD", "coverage": "Full wafer"},
    ),
    _step(
        "CMP", "Polish tungsten to oxide stop",
        {"target": 400.0, "pressure": 4.0, "time": 60.0, "preston": 0.5,
         "selectivity_mode": "Manual",
         "selectivity_pairs": [{"material": "Tungsten", "ratio": 1.0}]},
    ),
]
```

将新流程作为第 4 个条目追加到注册表返回值，`domain` 使用现有公共 `domain` 的深拷贝。

- [ ] **步骤 4：运行 W Plug 专项和完整 demo 测试**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-wplug-green \
  /opt/anaconda3/bin/python3 -m unittest tests.test_process_cad_demos -v
```

预期：W Plug 新测试与原 3 套流程全部 PASS。

- [ ] **步骤 5：提交 W Plug 流程**

```bash
git add tcad_simulator.py tests/test_process_cad_demos.py
git diff --cached --check
git commit -m "feat(示例): 添加钨塞与 CMP Golden 流程"
git push backup HEAD:refs/heads/zcode/process-cad-shell
```

### 任务 3：用 TDD 新增 Basic BEOL

**文件：**

- 修改：`tests/test_process_cad_demos.py`
- 修改：`tcad_simulator.py`（定位 `load_demo_flows`）

- [ ] **步骤 1：编写 BEOL 序列与最终结构红灯测试**

将 canonical 名称扩展为全部 5 套，并断言 Basic BEOL 序列：

```python
DEMO_NAMES = (
    "Basic Trench", "Spacer Formation", "Bonding + Thinning",
    "W Plug + CMP", "Basic BEOL",
)

self.assertEqual(
    [step["name"] for step in demos["Basic BEOL"]["steps"]],
    [
        "Initialize Wafer", "Deposition", "Spin Resist", "Mask Exposure",
        "Resist Develop", "Etch", "Strip", "Deposition", "Fill",
        "Deposition", "CMP",
    ],
)
```

新增 Golden 测试：

```python
def test_basic_beol_leaves_two_planar_copper_lines_with_tantalum_liner(self):
    database, model, _elapsed, trace = self.runs["Basic BEOL"]
    copper = database.id_for("Copper")
    tantalum = database.id_for("Tantalum")
    resist = database.id_for("Photoresist")
    liner = next(item for item in trace if item["instance_name"] == "Deposit tantalum barrier")
    fill = next(item for item in trace if item["instance_name"] == "Fill copper lines")
    overburden = next(item for item in trace if item["instance_name"] == "Electroplate copper overburden")
    polish = next(item for item in trace if item["instance_name"] == "Polish copper to oxide stop")

    self.assertGreater(liner["after"]["counts"]["Tantalum"], liner["before"]["counts"]["Tantalum"])
    self.assertGreater(fill["after"]["counts"]["Copper"], fill["before"]["counts"]["Copper"])
    self.assertGreater(overburden["after"]["counts"]["Copper"], overburden["before"]["counts"]["Copper"])
    self.assertLess(polish["after"]["counts"]["Copper"], polish["before"]["counts"]["Copper"])
    self.assertGreater(np.count_nonzero(model.grid == tantalum), 0)
    self.assertFalse(np.any(model.grid == resist))
    self.assertFalse(np.any(np.all(model.grid == copper, axis=(0, 1))))
    self.assertFalse(np.any(np.all(model.grid == tantalum, axis=(0, 1))))
    self.assertLessEqual(int(model.height_map.max()) - int(model.height_map.min()), 1)

    copper_xy = np.any(model.grid == copper, axis=2)
    occupied_x = np.flatnonzero(np.any(copper_xy, axis=1))
    runs = [run for run in np.split(occupied_x, np.where(np.diff(occupied_x) != 1)[0] + 1) if run.size]
    self.assertEqual(len(runs), 2)
```

- [ ] **步骤 2：运行 Basic BEOL 测试并确认正确红灯**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-beol-red \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_process_cad_demos.DemoRecipeRegistryTests.test_demo_sequences_express_the_designed_process_order \
  tests.test_process_cad_demos.DemoHeadlessAcceptanceTests.test_basic_beol_leaves_two_planar_copper_lines_with_tantalum_liner -v
```

预期：FAIL，注册表缺少 `Basic BEOL`。

- [ ] **步骤 3：实现 line mask 与 Basic BEOL 配方**

创建两条分离线：

```python
beol_line_mask = np.zeros((mask_size, mask_size), dtype=np.uint8)
beol_line_mask[7:11, :] = 1
beol_line_mask[21:25, :] = 1
```

新增以下完整的 11 步 `beol_steps`：

```python
beol_steps = [
    _step("Initialize Wafer", "300 nm BEOL silicon", {"thickness_nm": 300.0}),
    _step(
        "Deposition", "Deposit interlayer dielectric",
        {"material": "Silicon Dioxide", "thickness": 100.0, "method": "CVD", "coverage": "Full wafer"},
    ),
    _step("Spin Resist", "Metal line photoresist", {"thickness_nm": 40.0}),
    _step(
        "Mask Exposure", "Expose two metal lines",
        {"advanced_enable": 1, "mask_mode": "Custom", "mask_name": "Two metal lines", "dose": 80.0},
        custom_mask=beol_line_mask.tolist(), mask_name="Two metal lines",
    ),
    _step(
        "Resist Develop", "Open metal line resist",
        {"time": 60.0, "rate": 300.0, "contrast": 3.0, "threshold": 10.0},
    ),
    _step(
        "Etch", "Etch oxide line trenches",
        {"material": "Silicon Dioxide", "chemistry": "Dry", "time": 60.0,
         "rate_override": 600.0, "selectivity": 20.0, "sidewall": 90.0},
    ),
    _step("Strip", "Strip metal line resist", {"materials": "Photoresist"}),
    _step(
        "Deposition", "Deposit tantalum barrier",
        {"material": "Tantalum", "thickness": 10.0, "method": "PVD",
         "coverage": "Full wafer", "directionality": 0.8},
    ),
    _step(
        "Fill", "Fill copper lines",
        {"material": "Copper", "max_depth_nm": 70.0, "direction": "top", "include_sealed": False},
    ),
    _step(
        "Deposition", "Electroplate copper overburden",
        {"material": "Copper", "thickness": 30.0, "method": "Electroplate", "coverage": "Full wafer"},
    ),
    _step(
        "CMP", "Polish copper to oxide stop",
        {"target": 400.0, "pressure": 4.0, "time": 90.0, "preston": 0.5,
         "selectivity_mode": "Manual",
         "selectivity_pairs": [
             {"material": "Copper", "ratio": 1.0},
             {"material": "Tantalum", "ratio": 1.0},
         ]},
    ),
]
```

将流程作为第 5 个条目追加到注册表返回值，`domain` 使用现有公共 `domain` 的深拷贝。

- [ ] **步骤 4：运行全部 5 套流程及 SciPy fallback**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-beol-green \
  /opt/anaconda3/bin/python3 -m unittest tests.test_process_cad_demos -v
```

预期：全部 PASS；`test_all_demos_execute_without_scipy_ndimage` 实际遍历 5 套流程。

- [ ] **步骤 5：提交 Basic BEOL 流程**

```bash
git add tcad_simulator.py tests/test_process_cad_demos.py
git diff --cached --check
git commit -m "feat(示例): 添加基础 BEOL Golden 流程"
git push backup HEAD:refs/heads/zcode/process-cad-shell
```

### 任务 4：接入五流程基准并关闭 M1 文档

**文件：**

- 修改：`tests/test_webui_cad_shell.py`
- 修改：`tools/run_process_cad_baseline.py`
- 修改：`README.md`
- 修改：`docs/ROADMAP_PROCESS_CAD.md`

- [ ] **步骤 1：先把 CLI 基准契约扩展到 5 套流程**

将 `test_baseline_runner_writes_success_json` 的名称和材料要求改为：

```python
expected_names = {
    "Basic Trench", "Spacer Formation", "Bonding + Thinning",
    "W Plug + CMP", "Basic BEOL",
}
self.assertEqual(set(payload["demos"]), expected_names)
required_materials = {
    "Basic Trench": {"Silicon", "Silicon Dioxide"},
    "Spacer Formation": {"Silicon", "Silicon Nitride"},
    "Bonding + Thinning": {"Silicon", "Silicon Dioxide"},
    "W Plug + CMP": {"Silicon", "Silicon Dioxide", "Tungsten"},
    "Basic BEOL": {"Silicon", "Silicon Dioxide", "Copper", "Tantalum"},
}
```

- [ ] **步骤 2：运行 CLI 测试并确认正确红灯**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-baseline-red \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_webui_cad_shell.BaselineRunnerTests.test_baseline_runner_writes_success_json -v
```

预期：FAIL，实际报告仍只有 3 套流程。

- [ ] **步骤 3：改用公开注册表并添加新增流程语义检查**

在 runner 中：

```python
DEMO_NAMES = (
    "Basic Trench", "Spacer Formation", "Bonding + Thinning",
    "W Plug + CMP", "Basic BEOL",
)
```

将 `_run_demo()` 的加载改为：

```python
recipe = tcad.load_demo_flows(database)[name]
```

在 `_semantic_checks()` 中追加：

```python
elif name == "W Plug + CMP":
    tungsten = database.id_for("Tungsten")
    checks.update({
        "silicon_present": "Silicon" in material_names,
        "oxide_present": "Silicon Dioxide" in material_names,
        "tungsten_plugs_present": "Tungsten" in material_names,
        "resist_stripped": "Photoresist" not in material_names,
        "no_tungsten_blanket": not bool(np.any(np.all(model.grid == tungsten, axis=(0, 1)))),
        "planar_surface": int(model.height_map.max()) - int(model.height_map.min()) <= 1,
    })
elif name == "Basic BEOL":
    copper = database.id_for("Copper")
    tantalum = database.id_for("Tantalum")
    checks.update({
        "silicon_present": "Silicon" in material_names,
        "oxide_present": "Silicon Dioxide" in material_names,
        "copper_lines_present": "Copper" in material_names,
        "tantalum_liner_present": "Tantalum" in material_names,
        "resist_stripped": "Photoresist" not in material_names,
        "no_copper_blanket": not bool(np.any(np.all(model.grid == copper, axis=(0, 1)))),
        "no_tantalum_blanket": not bool(np.any(np.all(model.grid == tantalum, axis=(0, 1)))),
        "planar_surface": int(model.height_map.max()) - int(model.height_map.min()) <= 1,
    })
```

- [ ] **步骤 4：运行 32³ CLI 测试并校准关系断言**

运行：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-baseline-green \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_webui_cad_shell.BaselineRunnerTests.test_baseline_runner_writes_success_json -v
```

预期：PASS。若模型离散化令某个关系断言失败，只能调整配方参数或改为等价的关系断言；不得删除材料、CMP 或拓扑验收。

- [ ] **步骤 5：更新 README 和 ROADMAP**

在 `README.md` 中将 “three demo recipes” 改为 “five named Process CAD flows”，并说明 `load_demo_flows(material_db)` 是 WebUI、Golden 测试和 baseline 的共享入口。

在 `docs/ROADMAP_PROCESS_CAD.md` 中：

- 将 M1 状态改为完成；
- 将 `W Plug + CMP`、`Basic BEOL` 标记为 ✅；
- 记录公开 registry 已落地；
- 从 Backlog 删除已完成的 UI 无关加载入口条目；
- 不改 M2–M12 顺序或架构决策。

- [ ] **步骤 6：运行完整验证门**

运行项目基线测试：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-full \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_process_cad_foundation \
  tests.test_process_cad_primitives \
  tests.test_process_cad_demos \
  tests.test_webui_viewer_contract \
  tests.test_webui_cad_shell -v
```

运行编译与文本检查：

```bash
env PYTHONPYCACHEPREFIX=/tmp/tcad-m1-compile \
  /opt/anaconda3/bin/python3 -m py_compile tcad_simulator.py tools/*.py
git diff --check
```

从 `tcad_simulator._WEBUI_SCRIPT_JS` 提取完整 JavaScript 并交给 `node --check`，预期 exit 0。

运行正式基准：

```bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m1-baseline \
  /opt/anaconda3/bin/python3 tools/run_process_cad_baseline.py \
  --grid 128 --output /tmp/tcad-process-cad-five-flow-baseline.json
```

预期：exit 0，JSON 顶层 `ok` 为 `true`，包含 5 套流程且每套所有 `checks` 为 `true`。

- [ ] **步骤 7：自审、提交和 backup 核验**

```bash
git diff --check
git status --short
git add tools/run_process_cad_baseline.py tests/test_webui_cad_shell.py README.md docs/ROADMAP_PROCESS_CAD.md
git diff --cached --check
git commit -m "test(M1): 锁定五流程 Golden 基线"
git push backup HEAD:refs/heads/zcode/process-cad-shell
git rev-parse HEAD
git ls-remote backup refs/heads/zcode/process-cad-shell
```

最终必须确认：本地 HEAD 与 backup SHA 一致，工作树无跟踪文件改动，`origin` 未被推送。
