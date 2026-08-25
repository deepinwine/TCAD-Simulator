# Process CAD WebGL Viewer 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 WebGL context 冲突，交付标准视图、Perspective/Orthographic 切换、X/Y/Z 独立裁剪和统一材料视觉，同时保留 Host Render 可解释降级。

**架构：** 真实 viewer canvas 只交给 `THREE.WebGLRenderer` 一次；能力探测使用临时 canvas。Viewer 在浏览器内共享每个材料的一份 `BufferGeometry`，相机、裁剪和材料显示不触发 Worker 重算。

**技术栈：** 原生 JavaScript、Three.js r145、现有 `.geom` manifest/API、Python 标准库 `unittest`。

---

### 任务 1：建立 Viewer 契约测试

**文件：**
- 创建：`tests/test_webui_viewer_contract.py`

- [ ] **步骤 1：编写 WebGL 初始化契约失败测试**

```python
import unittest

import tcad_simulator as tcad


class WebGLInitializationContractTests(unittest.TestCase):
    def test_capability_probe_does_not_accept_viewer_canvas(self):
        source = tcad._WEBUI_SCRIPT_JS
        self.assertIn("function webglCapability()", source)
        self.assertIn("document.createElement('canvas')", source)
        self.assertNotIn("function _webglAvailable(canvas)", source)

    def test_renderer_is_created_before_backend_is_marked_ready(self):
        source = tcad._WEBUI_SCRIPT_JS
        renderer_pos = source.index("new THREE.WebGLRenderer")
        ready_pos = source.index("state.viewerBackend = 'webgl'")
        self.assertLess(renderer_pos, ready_pos)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract.WebGLInitializationContractTests`

预期：FAIL，当前仍包含 `_webglAvailable(canvas)`。

- [ ] **步骤 3：Commit 测试**

```bash
git add tests/test_webui_viewer_contract.py
git commit -m "test(Viewer): 添加 WebGL 初始化契约"
git push backup HEAD:codex/process-cad-shell
```

### 任务 2：修复 WebGL2 初始化与显式降级

**文件：**
- 修改：`tcad_simulator.py:91960-92020`
- 修改：`tcad_simulator.py:93080-93170`
- 修改：`tcad_simulator.py:80884-81010`
- 测试：`tests/test_webui_viewer_contract.py`

- [ ] **步骤 1：以临时 canvas 替换真实 canvas 探测**

```javascript
function webglCapability() {
  const probe = document.createElement('canvas');
  try {
    const webgl2 = probe.getContext('webgl2', { failIfMajorPerformanceCaveat: true });
    if (webgl2) return { ok: true, version: 2, reason: '' };
    const webgl1 = probe.getContext('webgl', { failIfMajorPerformanceCaveat: true });
    if (webgl1) return { ok: true, version: 1, reason: '' };
    return { ok: false, version: 0, reason: 'No WebGL context available' };
  } catch (error) {
    return { ok: false, version: 0, reason: String(error) };
  }
}
```

- [ ] **步骤 2：让 `initViewer()` 原子化设置 backend**

```javascript
const capability = webglCapability();
if (!capability.ok) return initRemoteViewer(capability.reason);
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  state.viewerBackend = 'webgl';
  state.webglVersion = capability.version;
} catch (error) {
  try { if (renderer) renderer.dispose(); } catch (_) {}
  renderer = null;
  return initRemoteViewer(String(error));
}
```

- [ ] **步骤 3：给 Host Render 增加可见状态**

`initRemoteViewer(reason)` 写入 `state.viewerFallbackReason`；Viewer 状态条显示 `Host Render · <reason>`，并明确标记三维裁剪不可用，而不是只写 console。

- [ ] **步骤 4：运行契约与现有 WebUI 自测**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract.WebGLInitializationContractTests
TCAD_TMP=$(mktemp -d /tmp/tcad-viewer-selftest.XXXXXX)
cd "$TCAD_TMP"
TCAD_SKIP_QT=1 MPLBACKEND=Agg /opt/anaconda3/bin/python3 \
  /Users/jiajia/.config/superpowers/worktrees/TCAD-Simulator/codex/process-cad-shell/tcad_simulator.py \
  --webui-selftest --skip-video --skip-iterate --out "$TCAD_TMP/output"
```

预期：测试和 WebUI selftest 均退出 0。

- [ ] **步骤 5：Commit**

```bash
git add tcad_simulator.py tests/test_webui_viewer_contract.py
git commit -m "fix(Viewer): 避免 WebGL canvas 上下文冲突"
git push backup HEAD:codex/process-cad-shell
```

### 任务 3：实现标准视图与双相机

**文件：**
- 修改：`tcad_simulator.py:80884-81010`
- 修改：`tcad_simulator.py:93139-94030`
- 测试：`tests/test_webui_viewer_contract.py`

- [ ] **步骤 1：编写相机控制契约失败测试**

```python
class CameraContractTests(unittest.TestCase):
    def test_standard_views_and_two_cameras_are_defined(self):
        source = tcad._WEBUI_SCRIPT_JS
        for token in ("ISO", "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT"):
            self.assertIn(f"'{token}'", source)
        self.assertIn("PerspectiveCamera", source)
        self.assertIn("OrthographicCamera", source)
        self.assertIn("function setCameraMode", source)
        self.assertIn("function applyStandardView", source)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract.CameraContractTests`

预期：FAIL，缺少用户正交相机或标准视图函数。

- [ ] **步骤 3：创建并维护两个相机**

```javascript
perspectiveCamera = new THREE.PerspectiveCamera(50, 1, 0.001, 1000);
orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 1000);
camera = perspectiveCamera;

function setCameraMode(mode) {
  const previous = camera;
  camera = mode === 'orthographic' ? orthographicCamera : perspectiveCamera;
  camera.position.copy(previous.position);
  camera.quaternion.copy(previous.quaternion);
  camera.up.copy(previous.up);
  syncCameraScale(previous, camera, meshGroup);
  controls.object = camera;
  controls.update();
  requestWebglRender(0);
}
```

- [ ] **步骤 4：实现标准视图表**

```javascript
const STANDARD_VIEWS = {
  TOP:    { direction: [0, 0, 1], up: [0, 1, 0] },
  BOTTOM: { direction: [0, 0, -1], up: [0, 1, 0] },
  FRONT:  { direction: [0, -1, 0], up: [0, 0, 1] },
  BACK:   { direction: [0, 1, 0], up: [0, 0, 1] },
  LEFT:   { direction: [-1, 0, 0], up: [0, 0, 1] },
  RIGHT:  { direction: [1, 0, 0], up: [0, 0, 1] },
  ISO:    { direction: [1, -1, 0.8], up: [0, 0, 1] },
};
```

`applyStandardView(name)` 根据包围盒中心与对角线设置 camera position 和 controls target，然后调用现有 clip/ruler 更新函数。

- [ ] **步骤 5：运行测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract.CameraContractTests
git add tcad_simulator.py tests/test_webui_viewer_contract.py
git commit -m "feat(Viewer): 添加标准视图与正交相机"
git push backup HEAD:codex/process-cad-shell
```

### 任务 4：实现 X/Y/Z 独立裁剪

**文件：**
- 修改：`tcad_simulator.py:80884-81010`
- 修改：`tcad_simulator.py:94033-94766`
- 测试：`tests/test_webui_viewer_contract.py`

- [ ] **步骤 1：编写裁剪状态测试**

```python
class ClippingContractTests(unittest.TestCase):
    def test_each_axis_has_enabled_position_and_invert(self):
        source = tcad._WEBUI_SCRIPT_JS
        self.assertIn("clipPlanes3d", source)
        for axis in ("X", "Y", "Z"):
            self.assertIn(f"{axis}: {{ enabled: false, position: 0.5, invert: false }}", source)
        self.assertIn("function updateAxisClippingPlanes", source)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract.ClippingContractTests`

预期：FAIL，缺少三轴独立状态。

- [ ] **步骤 3：建立三轴状态和 plane 更新**

```javascript
const clipPlanes3d = {
  X: { enabled: false, position: 0.5, invert: false },
  Y: { enabled: false, position: 0.5, invert: false },
  Z: { enabled: false, position: 0.5, invert: false },
};

function updateAxisClippingPlanes(bounds) {
  const result = [];
  for (const axis of ['X', 'Y', 'Z']) {
    const axisState = clipPlanes3d[axis];
    if (!axisState.enabled) continue;
    const component = { X: 'x', Y: 'y', Z: 'z' }[axis];
    const normal = new THREE.Vector3(axis === 'X' ? 1 : 0, axis === 'Y' ? 1 : 0, axis === 'Z' ? 1 : 0);
    if (axisState.invert) normal.multiplyScalar(-1);
    const point = bounds.min[component] + axisState.position * (bounds.max[component] - bounds.min[component]);
    result.push(new THREE.Plane(normal, -normal[component] * point));
  }
  activeClippingPlanes = result;
  applyClippingPlanesToMaterials();
}
```

- [ ] **步骤 4：复用现有 cap 机制**

把 `_clearCutawayCaps` 与 cap texture 生成改为遍历 active plane；无法生成 cap 的材料仍保留 clipping plane。Host Render 下禁用控件并显示原因。

- [ ] **步骤 5：运行测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract.ClippingContractTests
git add tcad_simulator.py tests/test_webui_viewer_contract.py
git commit -m "feat(Viewer): 添加三轴独立裁剪面"
git push backup HEAD:codex/process-cad-shell
```

### 任务 5：让 MaterialVisual 驱动 Viewer 材质

**文件：**
- 修改：`tcad_simulator.py:56507-58333`
- 修改：`tcad_simulator.py:95569-95770`
- 测试：`tests/test_webui_viewer_contract.py`

- [ ] **步骤 1：编写 manifest 视觉字段测试**

```python
class MaterialManifestTests(unittest.TestCase):
    def test_material_visual_payload_has_all_render_fields(self):
        db = tcad.MaterialDatabase()
        visual = db.material_visual(db.id("Copper")).as_dict()
        self.assertEqual(
            set(visual),
            {"material_id", "display_name", "color", "opacity", "metallic", "roughness", "visible"},
        )
```

- [ ] **步骤 2：运行测试验证视觉字段完整**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract.MaterialManifestTests`

预期：计划 1 完成后 PASS；若字段不完整则 FAIL 并列出缺少字段。

- [ ] **步骤 3：在 preview manifest 返回 `visual`**

每个 `mesh_items` 记录增加 `visual: model.material_db.material_visual(mat_id, override).as_dict()`；旧的 `name` 和 `color` 字段继续保留一个兼容周期。

- [ ] **步骤 4：创建一次 geometry、按视觉字段创建材质**

实体材质使用 `MeshStandardMaterial`：`opacity`、`metalness`、`roughness` 来自视觉记录；xray front/back 共享同一 geometry。`visible=false` 直接设置 group visibility，不删除 geometry。

- [ ] **步骤 5：运行 Viewer 契约、编译与 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_webui_viewer_contract
TCAD_PYCACHE_DIR=$(mktemp -d /tmp/tcad-viewer-pycache.XXXXXX)
PYTHONPYCACHEPREFIX="$TCAD_PYCACHE_DIR" /opt/anaconda3/bin/python3 -m py_compile tcad_simulator.py
git diff --check
git add tcad_simulator.py tests/test_webui_viewer_contract.py
git commit -m "feat(Viewer): 使用 MaterialVisual 驱动材质显示"
git push backup HEAD:codex/process-cad-shell
```

### 任务 6：在真实浏览器完成 Viewer 冒烟验证

**文件：**
- 修改：`docs/WEBUI_RUNTIME.md`

- [ ] **步骤 1：启动隔离 WebUI**

```bash
TCAD_VIEW_DIR=$(mktemp -d /tmp/tcad-viewer-manual.XXXXXX)
TCAD_WEBUI_STORAGE="$TCAD_VIEW_DIR" TCAD_SKIP_QT=1 MPLBACKEND=Agg \
  /opt/anaconda3/bin/python3 -c \
  'import os, threading; from pathlib import Path; from tcad_simulator import WebUIServerManager; manager = WebUIServerManager(host="127.0.0.1", port=8766, storage_root=Path(os.environ["TCAD_WEBUI_STORAGE"])); manager.start(); print(manager.url, flush=True); threading.Event().wait()'
```

- [ ] **步骤 2：用浏览器检查控制台和实际交互**

检查清单：控制台不出现 `Canvas has an existing context of a different type`；状态条为 WebGL2；七个视图能定位模型；Perspective/Ortho 保持模型可见；X/Y/Z 可同时启用并分别 invert；材料显隐不产生 `/api/preview/manifest` 新请求。

- [ ] **步骤 3：记录验证步骤并 Commit**

在 `docs/WEBUI_RUNTIME.md` 写入启动命令、Viewer 状态含义和上述检查清单。

```bash
git add docs/WEBUI_RUNTIME.md
git commit -m "docs(Viewer): 记录 WebGL2 与裁剪验证流程"
git push backup HEAD:codex/process-cad-shell
```
