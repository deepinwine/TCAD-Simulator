# Process CAD Shell 集成实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 Process Flow、Parameters 和 3D Viewer 集成为固定三栏工作面，并补齐拖拽排序、步骤重命名、时间线、错误展示、性能基准和用户文档。

**架构：** 继续使用内嵌 HTML/CSS/JS 与现有 API，不引入新构建链。UI 只调用 Worker 提供的配方和快照操作；参数仍由 `ProcessStep.parameter_specs()` 驱动。桌面宽屏固定三栏，窄窗口允许折叠。

**技术栈：** 原生 HTML/CSS/JavaScript、现有 WebUI HTTP API、Python Worker、标准库 `unittest` 与 `urllib`。

---

### 任务 1：建立 CAD Shell 服务契约测试

**文件：**
- 创建：`tests/test_webui_cad_shell.py`

- [ ] **步骤 1：编写三栏 HTML 失败测试**

```python
import unittest

import tcad_simulator as tcad


class CadShellMarkupTests(unittest.TestCase):
    def test_three_columns_are_present(self):
        html = tcad._WEBUI_INDEX_HTML
        for element_id in ("process-flow-panel", "parameters-panel", "viewer-panel"):
            self.assertIn(f'id="{element_id}"', html)

    def test_desktop_grid_has_three_columns(self):
        css = tcad._WEBUI_STYLE_CSS
        expected = "grid-template-columns: minmax(260px, 300px) minmax(300px, 360px) minmax(420px, 1fr)"
        self.assertIn(expected, css)
```

- [ ] **步骤 2：编写步骤交互契约失败测试**

```python
class CadShellInteractionContractTests(unittest.TestCase):
    def test_recipe_items_support_drag_and_rename(self):
        source = tcad._WEBUI_SCRIPT_JS
        self.assertIn("item.draggable = true", source)
        self.assertIn("dragstart", source)
        self.assertIn("drop", source)
        self.assertIn("renameStep", source)

    def test_timeline_controls_exist(self):
        html = tcad._WEBUI_INDEX_HTML
        for element_id in ("timeline-prev", "timeline-next", "timeline-range"):
            self.assertIn(f'id="{element_id}"', html)
```

- [ ] **步骤 3：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_cad_shell`

预期：FAIL，缺少三栏 ID、拖拽和时间线控件。

- [ ] **步骤 4：Commit 测试**

```bash
git add tests/test_webui_cad_shell.py
git commit -m "test(CAD界面): 添加三栏与交互契约"
git push backup HEAD:codex/process-cad-shell
```

### 任务 2：实现固定三栏布局

**文件：**
- 修改：`tcad_simulator.py:80018-82766`
- 测试：`tests/test_webui_cad_shell.py`

- [ ] **步骤 1：重组主工作区 HTML**

```html
<main id="cad-workspace" class="cad-workspace">
  <section id="process-flow-panel" class="cad-panel cad-process-flow"></section>
  <section id="parameters-panel" class="cad-panel cad-parameters"></section>
  <section id="viewer-panel" class="cad-viewer"></section>
</main>
```

把现有 Recipe、Parameters 和 Viewer DOM 移入对应 section；保留原有 element ID，使事件绑定和 API 调用可增量迁移。History、Export、2D Slice 等次级工具保留在可折叠 drawer。

- [ ] **步骤 2：增加桌面 grid 与窄屏折叠**

```css
.cad-workspace {
  display: grid;
  grid-template-columns: minmax(260px, 300px) minmax(300px, 360px) minmax(420px, 1fr);
  min-height: 0;
  height: 100%;
}
.cad-panel { min-width: 0; min-height: 0; overflow: hidden; border-right: 1px solid var(--border); }
.cad-viewer { position: relative; min-width: 0; min-height: 0; }
@media (max-width: 1100px) {
  .cad-workspace { grid-template-columns: minmax(250px, 290px) minmax(360px, 1fr); }
  .cad-parameters.is-collapsed { display: none; }
}
```

- [ ] **步骤 3：删除 dock tab 对三大面板的互斥控制**

三大面板不再由同一 `activeDockTab` 显隐。次级 drawer 仍可复用 dock 机制。`Reset layout` 恢复三栏默认宽度和 drawer 关闭状态。

- [ ] **步骤 4：运行 markup 测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_cad_shell.CadShellMarkupTests
git add tcad_simulator.py tests/test_webui_cad_shell.py
git commit -m "feat(CAD界面): 重组三栏工艺工作区"
git push backup HEAD:codex/process-cad-shell
```

### 任务 3：实现拖拽排序与步骤重命名

**文件：**
- 修改：`tcad_simulator.py:69280-69320`
- 修改：`tcad_simulator.py:71920-71980`
- 修改：`tcad_simulator.py:88147-88310`
- 测试：`tests/test_webui_cad_shell.py`

- [ ] **步骤 1：增加 rename Worker 命令和 HTTP endpoint**

```python
if cmd == "recipe_rename_step":
    index = int(payload.get("index", -1))
    instance_name = str(payload.get("instance_name", "")).strip()
    if index < 0 or index >= len(recipe):
        return {"ok": False, "error": "Step index out of range"}
    if not instance_name or len(instance_name) > 80:
        return {"ok": False, "error": "Step name must contain 1-80 characters"}
    recipe[index].instance_name = instance_name
    _autosave_recipe()
    return {"ok": True, "result": _webui_serialize_step(recipe[index])}
```

HTTP 路径为 `POST /api/recipe/rename-step`，payload 保持 `{index, instance_name}`。

- [ ] **步骤 2：实现 drag source 与 drop target**

```javascript
item.draggable = true;
item.addEventListener('dragstart', event => {
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/tcad-step-index', String(idx));
});
item.addEventListener('dragover', event => event.preventDefault());
item.addEventListener('drop', async event => {
  event.preventDefault();
  const from = Number(event.dataTransfer.getData('text/tcad-step-index'));
  if (!Number.isInteger(from) || from === idx) return;
  await moveRecipeStep(from, idx);
});
```

`moveRecipeStep(from, to)` 调用现有 recipe move API；失败时重新获取 recipe 并显示错误，不在客户端猜测最终顺序。

- [ ] **步骤 3：实现双击重命名**

`renameStep(index, currentName)` 显示内联 input，Enter/blur 提交，Escape 取消。服务返回成功后更新 `state.recipe[index].instance_name`；参数摘要继续使用 `step.name` 作为类型。

- [ ] **步骤 4：运行交互契约和 Recipe 兼容测试**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_cad_shell.CadShellInteractionContractTests tests.test_process_cad_foundation.RecipeCompatibilityTests`

预期：所有测试 PASS。

- [ ] **步骤 5：Commit**

```bash
git add tcad_simulator.py tests/test_webui_cad_shell.py
git commit -m "feat(工艺流): 支持拖拽排序与步骤重命名"
git push backup HEAD:codex/process-cad-shell
```

### 任务 4：实现步骤时间线与 Previous/Next

**文件：**
- 修改：`tcad_simulator.py:56365-58114`
- 修改：`tcad_simulator.py:68985-70480`
- 修改：`tcad_simulator.py:80018-81010`
- 修改：`tcad_simulator.py:88310-88750`
- 测试：`tests/test_webui_cad_shell.py`

- [ ] **步骤 1：编写 snapshot manifest helper 测试**

```python
class TimelineStateTests(unittest.TestCase):
    def test_snapshot_manifest_marks_valid_dirty_and_current(self):
        result = tcad._snapshot_timeline_manifest(
            recipe_length=4,
            valid_snapshot_indices={0, 1},
            statuses=["done", "done", "dirty", "dirty"],
            current_index=1,
        )
        self.assertEqual([item["state"] for item in result], ["done", "current", "dirty", "dirty"])
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_cad_shell.TimelineStateTests`

预期：FAIL，helper 尚未定义。

- [ ] **步骤 3：增加 timeline manifest 和 restore command**

`timeline_get` 返回步骤 index、instance_name、runtime_status、snapshot_valid、current。`timeline_restore` 只允许恢复有效快照；Dirty/Ready/Error 无有效快照时返回结构化错误，不隐式重算。

- [ ] **步骤 4：绑定 Previous、Next 和 range**

Previous/Next 在有效快照之间移动；range 拖动只更新标签，change 时调用 restore。恢复成功后刷新 model summary、preview manifest 和步骤选中状态。

- [ ] **步骤 5：运行状态、回滚和 timeline 测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v \
  tests.test_process_cad_foundation.StepRuntimeStatusTests \
  tests.test_process_cad_foundation.StepTransactionTests \
  tests.test_webui_cad_shell.TimelineStateTests
git add tcad_simulator.py tests/test_webui_cad_shell.py
git commit -m "feat(时间线): 支持步骤快照前后回看"
git push backup HEAD:codex/process-cad-shell
```

### 任务 5：实现 Redo、步骤状态和结构化错误展示

**文件：**
- 修改：`tcad_simulator.py:35380-35440`
- 修改：`tcad_simulator.py:68985-70480`
- 修改：`tcad_simulator.py:80018-81010`
- 修改：`tcad_simulator.py:88147-88310`
- 测试：`tests/test_webui_cad_shell.py`

- [ ] **步骤 1：编写 Undo/Redo 栈转换测试**

```python
class HistoryStackTests(unittest.TestCase):
    def test_new_edit_clears_redo_stack(self):
        undo = ["s0"]
        redo = ["s2"]
        tcad._record_history_edit(undo, redo, "s1", max_items=20)
        self.assertEqual(undo, ["s0", "s1"])
        self.assertEqual(redo, [])

    def test_undo_moves_current_to_redo(self):
        undo = ["s0", "s1"]
        redo = []
        restored = tcad._history_undo(undo, redo, current="s2")
        self.assertEqual(restored, "s1")
        self.assertEqual(redo, ["s2"])
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_cad_shell.HistoryStackTests`

预期：FAIL，history helper 尚未定义。

- [ ] **步骤 3：在 Worker 增加 `redo_stack` 与 `redo` command**

每次新的配方修改或成功运行清空 redo；Undo 前把当前 recipe/model snapshot 推入 redo；Redo 前把当前状态推回 undo。两个栈都使用现有大数组 spill 与 20 项上限，不复制新的压缩实现。

- [ ] **步骤 4：渲染状态 badge 与错误详情**

步骤卡使用 `runtime_status` 设置 CSS class。Error 卡显示简短消息；点击后在参数栏顶部展示 `step_index`、`step_type`、`parameter_path`、用户消息、建议操作和 `rolled_back`。Run 按钮在 `running` 时禁用，其他 Viewer 交互保持可用。

- [ ] **步骤 5：绑定 Undo/Redo 并运行测试**

```bash
/opt/anaconda3/bin/python3 -m unittest -v \
  tests.test_webui_cad_shell.HistoryStackTests \
  tests.test_process_cad_foundation.StepTransactionTests
```

预期：所有测试 PASS。

- [ ] **步骤 6：Commit**

```bash
git add tcad_simulator.py tests/test_webui_cad_shell.py
git commit -m "feat(历史): 添加 Redo 与结构化步骤错误"
git push backup HEAD:codex/process-cad-shell
```

### 任务 6：增加可复现基准运行器

**文件：**
- 创建：`tools/run_process_cad_baseline.py`
- 测试：`tests/test_webui_cad_shell.py`

- [ ] **步骤 1：编写基准 CLI 失败测试**

```python
class BaselineRunnerTests(unittest.TestCase):
    def test_baseline_runner_writes_success_json(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.json"
            completed = subprocess.run(
                [sys.executable, "tools/run_process_cad_baseline.py", "--grid", "32", "--output", str(output)],
                text=True,
                capture_output=True,
                timeout=240,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["grid"], 32)
            self.assertEqual(set(payload["demos"]), {"Basic Trench", "Spacer Formation", "Bonding + Thinning"})
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_cad_shell.BaselineRunnerTests`

预期：FAIL，脚本文件不存在。

- [ ] **步骤 3：实现 CLI**

```python
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=int, default=128)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_baseline(grid_size=max(24, int(args.grid)))
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if result.get("ok") else 1
```

`run_baseline()` 对三个 demo 分别记录 `elapsed_s`、`peak_rss_mb`、`material_count`、`occupied_voxels`、`triangle_count` 和 `mesh_elapsed_s`。使用 `resource.getrusage` 记录进程峰值；macOS 的 `ru_maxrss` 直接按 bytes 转 MB，Linux 按 KiB 转 MB。

- [ ] **步骤 4：运行 32³ 快速测试与 128³ 正式基准**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_cad_shell.BaselineRunnerTests
TCAD_SKIP_QT=1 MPLBACKEND=Agg /opt/anaconda3/bin/python3 \
  tools/run_process_cad_baseline.py --grid 128 --output /tmp/tcad-cad-baseline.json
/opt/anaconda3/bin/python3 -m json.tool /tmp/tcad-cad-baseline.json
```

预期：测试 PASS；JSON `ok` 为 `true`，三个 demo 都包含时间、内存和网格统计。

- [ ] **步骤 5：Commit**

```bash
git add tools/run_process_cad_baseline.py tests/test_webui_cad_shell.py
git commit -m "test(性能): 添加 Process CAD 可复现基准"
git push backup HEAD:codex/process-cad-shell
```

### 任务 7：文档、浏览器验收与全量验证

**文件：**
- 修改：`README.md`
- 修改：`docs/ARCHITECTURE.md`
- 修改：`docs/WEBUI_RUNTIME.md`

- [ ] **步骤 1：更新用户入口与架构文档**

README 增加 Process CAD Shell 启动方式、三栏说明、三个 demo、标准视图、裁剪和 Recipe 兼容保证。ARCHITECTURE 记录 `UI → API → Worker → ProcessStep → ProcessModel → Snapshot/Mesh` 数据流。WEBUI_RUNTIME 记录 WebGL2/Host Render 状态、浏览器兼容和诊断步骤。

- [ ] **步骤 2：运行完整自动验证**

```bash
TCAD_PYCACHE_DIR=$(mktemp -d /tmp/tcad-cad-final-pycache.XXXXXX)
PYTHONPYCACHEPREFIX="$TCAD_PYCACHE_DIR" /opt/anaconda3/bin/python3 -m py_compile \
  tcad_simulator.py tools/docsite.py tools/split_tcad.py tools/run_process_cad_baseline.py
/opt/anaconda3/bin/python3 -m unittest -v \
  tests.test_process_cad_foundation \
  tests.test_process_cad_primitives \
  tests.test_process_cad_demos \
  tests.test_webui_viewer_contract \
  tests.test_webui_cad_shell
TCAD_SKIP_QT=1 MPLBACKEND=Agg /opt/anaconda3/bin/python3 \
  tools/run_process_cad_baseline.py --grid 128 --output /tmp/tcad-cad-final.json
git diff --check
```

预期：编译退出 0；全部测试结尾为 `OK`；基准退出 0；diff check 退出 0。

- [ ] **步骤 3：在浏览器逐项验收**

启动 WebUI，依次加载三个 demo。确认：默认 WebGL2；三栏同时可见；步骤可拖拽和重命名；参数自动保存并使后续状态 Dirty；Previous/Next 不重算；Undo/Redo 可逆；七个标准视图与双相机可用；三轴裁剪可同时启用并 invert；材料显隐不触发模型请求；失败步骤自动回滚并显示结构化错误。

- [ ] **步骤 4：Commit 文档并推送最终功能分支**

```bash
git add README.md docs/ARCHITECTURE.md docs/WEBUI_RUNTIME.md
git commit -m "docs(CAD界面): 补充使用与运行架构说明"
git push backup HEAD:codex/process-cad-shell
```

- [ ] **步骤 5：确认远程备份与本地提交一致**

```bash
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git ls-remote backup refs/heads/codex/process-cad-shell | awk '{print $1}')
printf 'local=%s\nremote=%s\n' "$LOCAL_HEAD" "$REMOTE_HEAD"
test "$LOCAL_HEAD" = "$REMOTE_HEAD"
```

预期：两个 SHA 完全相同，命令退出 0。
