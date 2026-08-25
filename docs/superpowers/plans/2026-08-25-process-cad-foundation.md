# Process CAD 兼容与测试基础实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 建立 MaterialVisual、步骤实例名、运行状态、事务回滚和自包含 Recipe 测试，为后续工艺与 UI 开发提供稳定兼容层。

**架构：** 所有新增字段均为可选字段；`ProcessStep.name` 仍表示工厂类型，新增 `instance_name` 只用于显示。Worker 维护独立的步骤运行状态，并在修改/排序后从最早受影响位置失效；模型运行失败时恢复运行前快照。

**技术栈：** Python 3.13、dataclasses、NumPy、标准库 `unittest`、现有 Recipe migration 与 WebUI Worker。

---

### 任务 0：建立精确的生成物忽略规则

**文件：**
- 创建：`.gitignore`

- [ ] **步骤 1：验证当前生成物没有被忽略**

运行：`git check-ignore OrbitControls.js TCAD_Web_Data/ tcad_simulator_split/`

预期：退出码 1，说明仓库当前没有对应规则。

- [ ] **步骤 2：创建 `.gitignore`**

```gitignore
# Python runtime
__pycache__/
*.py[cod]

# TCAD runtime and self-tests
TCAD_Web_Data/
TCAD_Selftest_Output_*/

# Generated navigation view
tcad_simulator_split/

# Downloaded WebUI/docsite vendor
OrbitControls.js
STLLoader.js
three.js
three.min.js
tools/html_vendor/
```

- [ ] **步骤 3：验证规则只匹配已知生成物**

运行：`git check-ignore -v OrbitControls.js STLLoader.js TCAD_Web_Data/ tcad_simulator_split/ three.js three.min.js tools/html_vendor/`

预期：每个路径都显示 `.gitignore` 中的匹配行；`git check-ignore README.md tcad_simulator.py` 仍退出 1。

- [ ] **步骤 4：Commit**

```bash
git add .gitignore
git commit -m "chore(仓库): 忽略运行与拆分生成物"
git push backup HEAD:codex/process-cad-shell
```

### 任务 1：建立标准库测试入口

**文件：**
- 创建：`tests/__init__.py`
- 创建：`tests/test_process_cad_foundation.py`

- [ ] **步骤 1：创建空测试包**

```python
"""TCAD-Simulator regression tests."""
```

- [ ] **步骤 2：编写失败的 MaterialVisual 测试**

```python
import unittest

import tcad_simulator as tcad


class MaterialVisualTests(unittest.TestCase):
    def test_default_visual_inherits_physical_material(self):
        db = tcad.MaterialDatabase()
        silicon_id = db.id("Silicon")
        visual = db.material_visual(silicon_id)
        self.assertEqual(visual.material_id, silicon_id)
        self.assertEqual(visual.display_name, "Silicon")
        self.assertEqual(tuple(visual.color), tuple(db.material(silicon_id).color))
        self.assertEqual(visual.opacity, 1.0)
        self.assertTrue(visual.visible)

    def test_visual_override_is_clamped_without_mutating_material(self):
        db = tcad.MaterialDatabase()
        silicon_id = db.id("Silicon")
        original = tuple(db.material(silicon_id).color)
        visual = db.material_visual(
            silicon_id,
            {"display_name": "Device Si", "color": [2.0, -1.0, 0.5], "opacity": 1.4},
        )
        self.assertEqual(visual.display_name, "Device Si")
        self.assertEqual(visual.color, (1.0, 0.0, 0.5))
        self.assertEqual(visual.opacity, 1.0)
        self.assertEqual(tuple(db.material(silicon_id).color), original)
```

- [ ] **步骤 3：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation.MaterialVisualTests`

预期：FAIL，错误包含 `MaterialDatabase` 没有 `material_visual`。

- [ ] **步骤 4：Commit 测试骨架**

```bash
git add tests/__init__.py tests/test_process_cad_foundation.py
git commit -m "test(CAD基础): 添加材料视觉回归测试"
git push backup HEAD:codex/process-cad-shell
```

### 任务 2：实现 MaterialVisual 兼容层

**文件：**
- 修改：`tcad_simulator.py:5579-6349`
- 测试：`tests/test_process_cad_foundation.py`

- [ ] **步骤 1：在 `Material` 后定义不可变视觉记录**

```python
@dataclass(frozen=True)
class MaterialVisual:
    material_id: int
    display_name: str
    color: Tuple[float, float, float]
    opacity: float = 1.0
    metallic: float = 0.0
    roughness: float = 0.72
    visible: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "material_id": int(self.material_id),
            "display_name": str(self.display_name),
            "color": [float(v) for v in self.color],
            "opacity": float(self.opacity),
            "metallic": float(self.metallic),
            "roughness": float(self.roughness),
            "visible": bool(self.visible),
        }
```

- [ ] **步骤 2：在 `MaterialDatabase` 增加默认值与覆盖归一化**

```python
def material_visual(self, material_id: int, override: Optional[Dict[str, Any]] = None) -> MaterialVisual:
    material = self.material(int(material_id))
    raw = override if isinstance(override, dict) else {}

    def clamp01(value: Any, default: float) -> float:
        try:
            return float(np.clip(float(value), 0.0, 1.0))
        except Exception:
            return float(default)

    source_color = raw.get("color", material.color)
    try:
        color = tuple(clamp01(source_color[i], material.color[i]) for i in range(3))
    except Exception:
        color = tuple(float(v) for v in material.color)
    return MaterialVisual(
        material_id=int(material_id),
        display_name=str(raw.get("display_name") or material.name),
        color=(float(color[0]), float(color[1]), float(color[2])),
        opacity=clamp01(raw.get("opacity", 1.0), 1.0),
        metallic=clamp01(raw.get("metallic", 0.0), 0.0),
        roughness=clamp01(raw.get("roughness", 0.72), 0.72),
        visible=bool(raw.get("visible", True)),
    )
```

- [ ] **步骤 3：运行 MaterialVisual 测试验证通过**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation.MaterialVisualTests`

预期：2 个测试 PASS，结尾为 `OK`。

- [ ] **步骤 4：Commit**

```bash
git add tcad_simulator.py tests/test_process_cad_foundation.py
git commit -m "feat(材料): 添加统一 MaterialVisual 注册表"
git push backup HEAD:codex/process-cad-shell
```

### 任务 3：增加步骤实例名并保持 Recipe 类型兼容

**文件：**
- 修改：`tcad_simulator.py:18030-18051`
- 修改：`tcad_simulator.py:31049-31140`
- 修改：`tcad_simulator.py:31815-31960`
- 测试：`tests/test_process_cad_foundation.py`

- [ ] **步骤 1：编写旧配方与实例名 round-trip 测试**

```python
class RecipeCompatibilityTests(unittest.TestCase):
    def test_legacy_step_without_instance_name_keeps_factory_name(self):
        db = tcad.MaterialDatabase()
        step = tcad._webui_deserialize_step(
            {"name": "Deposition", "enabled": True, "params": {"material": "Silicon Dioxide"}},
            db,
        )
        self.assertEqual(step.name, "Deposition")
        self.assertEqual(step.instance_name, "Deposition")

    def test_instance_name_round_trip_does_not_change_factory_name(self):
        db = tcad.MaterialDatabase()
        step = tcad.PROCESS_STEP_FACTORIES["Etch"](db)
        step.instance_name = "Gate trench etch"
        restored = tcad._webui_deserialize_step(tcad._webui_serialize_step(step), db)
        self.assertEqual(restored.name, "Etch")
        self.assertEqual(restored.instance_name, "Gate trench etch")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation.RecipeCompatibilityTests`

预期：FAIL，错误包含 `instance_name` 不存在或未被序列化。

- [ ] **步骤 3：给 `ProcessStep` 增加兼容字段**

```python
class ProcessStep:
    name = "Process"

    def __init__(self, material_db: MaterialDatabase) -> None:
        self.material_db = material_db
        self.enabled = True
        self.params: Dict[str, Any] = {}
        self.instance_name = str(self.name)
```

保持每个已有子类调用 `super().__init__(material_db)`；若某个子类没有调用，则在其构造器中补上，不改变现有参数默认值。

- [ ] **步骤 4：在序列化和反序列化中增加可选 `instance_name`**

```python
payload["instance_name"] = str(getattr(step, "instance_name", step.name) or step.name)
```

```python
raw_instance_name = str(blob.get("instance_name") or blob.get("label") or step.name).strip()
step.instance_name = raw_instance_name or str(step.name)
```

迁移函数只补默认值，不改写 `name`；`name` 始终是 `PROCESS_STEP_FACTORIES` 的 key。

- [ ] **步骤 5：运行兼容测试与当前 Recipe 解析自测**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation.RecipeCompatibilityTests`

预期：2 个测试 PASS。

- [ ] **步骤 6：Commit**

```bash
git add tcad_simulator.py tests/test_process_cad_foundation.py
git commit -m "feat(配方): 支持兼容的步骤实例名称"
git push backup HEAD:codex/process-cad-shell
```

### 任务 4：实现步骤状态失效函数

**文件：**
- 修改：`tcad_simulator.py:35121-35430`
- 修改：`tcad_simulator.py:56755-58114`
- 测试：`tests/test_process_cad_foundation.py`

- [ ] **步骤 1：编写状态归一化与失效测试**

```python
class StepRuntimeStatusTests(unittest.TestCase):
    def test_invalidate_from_preserves_earlier_done_steps(self):
        statuses = ["done", "done", "done", "ready"]
        actual = tcad._invalidate_step_statuses(statuses, start_index=2, recipe_length=4)
        self.assertEqual(actual, ["done", "done", "dirty", "dirty"])

    def test_statuses_are_resized_to_recipe_length(self):
        actual = tcad._normalize_step_statuses(["done"], recipe_length=3)
        self.assertEqual(actual, ["done", "ready", "ready"])
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation.StepRuntimeStatusTests`

预期：FAIL，两个 helper 尚未定义。

- [ ] **步骤 3：实现纯函数 helper**

```python
_STEP_RUNTIME_STATES = frozenset({"ready", "dirty", "running", "done", "error"})


def _normalize_step_statuses(statuses: Any, recipe_length: int) -> List[str]:
    source = list(statuses) if isinstance(statuses, (list, tuple)) else []
    out: List[str] = []
    for index in range(max(0, int(recipe_length))):
        raw = str(source[index]).lower() if index < len(source) else "ready"
        out.append(raw if raw in _STEP_RUNTIME_STATES else "ready")
    return out


def _invalidate_step_statuses(statuses: Any, start_index: int, recipe_length: int) -> List[str]:
    out = _normalize_step_statuses(statuses, recipe_length)
    start = int(np.clip(int(start_index), 0, len(out)))
    for index in range(start, len(out)):
        out[index] = "dirty"
    return out
```

- [ ] **步骤 4：接入 Worker 修改路径**

在 `set_step`、insert、remove、move、duplicate 和 recipe load 成功后更新 `step_runtime_statuses`。参数修改从当前 index 失效；插入/删除/移动从最早受影响 index 失效；新配方全部为 `ready`。`get_recipe` 返回每个步骤的 `runtime_status`。

- [ ] **步骤 5：运行状态测试**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation.StepRuntimeStatusTests`

预期：2 个测试 PASS。

- [ ] **步骤 6：Commit**

```bash
git add tcad_simulator.py tests/test_process_cad_foundation.py
git commit -m "feat(执行状态): 增加步骤失效状态模型"
git push backup HEAD:codex/process-cad-shell
```

### 任务 5：为步骤执行增加事务回滚

**文件：**
- 修改：`tcad_simulator.py:56365-58114`
- 测试：`tests/test_process_cad_foundation.py`

- [ ] **步骤 1：编写失败回滚测试**

```python
class StepTransactionTests(unittest.TestCase):
    def test_transaction_restores_grid_after_exception(self):
        model = tcad.ProcessModel(tcad.MaterialDatabase(), grid_shape=(12, 12, 16), voxel_size_nm=5.0)
        before = model.snapshot_state(compression="dense")

        def mutate_then_fail():
            model.grid[:, :, 0] = 99
            raise ValueError("bad depth")

        result = tcad._run_model_transaction(model, mutate_then_fail)
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertTrue(np.array_equal(model.grid, before["grid"]))
        self.assertEqual(result["error_type"], "ValueError")
```

在文件顶部加入 `import numpy as np`。

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation.StepTransactionTests`

预期：FAIL，`_run_model_transaction` 尚未定义。

- [ ] **步骤 3：实现事务 helper**

```python
def _run_model_transaction(model: ProcessModel, operation: Callable[[], Any]) -> Dict[str, Any]:
    before = model.snapshot_state(compression="dense")
    try:
        value = operation()
        return {"ok": True, "value": value, "rolled_back": False}
    except Exception as exc:
        model.restore_state(before)
        return {
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "rolled_back": True,
        }
```

Worker 调用层补充 `step_index`、`instance_name`、`step_type`、`parameter_path` 和 `suggestion`；纯 helper 不依赖 UI。

- [ ] **步骤 4：接入单步与增量运行路径**

在每个步骤执行前将状态设为 `running`；事务成功后设为 `done` 并提交 revision/快照；失败后设为 `error`，不得推进 revision，不得覆盖上一个有效快照。

- [ ] **步骤 5：运行完整基础测试**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation`

预期：所有测试 PASS，结尾为 `OK`。

- [ ] **步骤 6：Commit**

```bash
git add tcad_simulator.py tests/test_process_cad_foundation.py
git commit -m "feat(执行): 增加步骤事务回滚与结构化错误"
git push backup HEAD:codex/process-cad-shell
```

### 任务 6：让 Recipe IO 自测使用仓库内自包含数据

**文件：**
- 修改：`tcad_simulator.py:100454-101371`
- 创建：`tests/fixtures/legacy_recipe_minimal.json`
- 测试：`tests/test_process_cad_foundation.py`

- [ ] **步骤 1：创建最小旧版 fixture**

```json
{
  "version": 1,
  "name": "Legacy Minimal",
  "steps": [
    {"name": "Initialize Wafer", "enabled": true, "params": {"material": "Silicon", "thickness_nm": 200.0}},
    {"name": "Deposition", "enabled": true, "params": {"material": "Silicon Dioxide", "thickness_nm": 20.0, "method": "ALD"}}
  ]
}
```

- [ ] **步骤 2：把 selftest 默认 fixture 解析为脚本相对路径**

```python
fixture_default = Path(__file__).resolve().parent / "tests" / "fixtures" / "legacy_recipe_minimal.json"
parser.add_argument("--recipe", default=str(fixture_default))
```

移除对 `SAQP_Thinking_Flow.json` 与 `tcad_simulator_2.19.py` 的默认硬依赖；只有显式传入参考文件时才执行跨版本比较。

- [ ] **步骤 3：增加 subprocess 自测**

```python
def test_recipe_io_selftest_is_self_contained(self):
    import os
    import subprocess
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        completed = subprocess.run(
            [sys.executable, tcad.__file__, "--recipe-io-selftest"],
            cwd=tmp,
            env={**os.environ, "TCAD_SKIP_QT": "1", "MPLBACKEND": "Agg"},
            text=True,
            capture_output=True,
            timeout=180,
        )
    self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
```

- [ ] **步骤 4：运行 Recipe IO 与完整基础测试**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_foundation`

预期：所有测试 PASS，Recipe IO 不依赖工作目录中的外部文件。

- [ ] **步骤 5：验证并 Commit**

```bash
git diff --check
git add tcad_simulator.py tests/test_process_cad_foundation.py tests/fixtures/legacy_recipe_minimal.json
git commit -m "test(配方): 改为自包含 Recipe IO 回归数据"
git push backup HEAD:codex/process-cad-shell
```
