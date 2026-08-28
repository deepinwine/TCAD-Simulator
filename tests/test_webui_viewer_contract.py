import json
import re
import subprocess
import unittest

import tcad_simulator as tcad


def _extract_function(name, next_name):
    pattern = re.compile(
        rf"function {re.escape(name)}\([^\n]*\) \{{.*?\n\}}\n\nfunction {re.escape(next_name)}\(",
        re.DOTALL,
    )
    match = pattern.search(tcad._WEBUI_SCRIPT_JS)
    if not match:
        raise AssertionError(f"could not extract JavaScript function {name}")
    text = match.group(0)
    return text[: text.rfind(f"\n\nfunction {next_name}(")]


def _run_node(source):
    proc = subprocess.run(
        ["node", "-e", source],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"node contract failed ({proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def _camera_contract_source():
    source = tcad._WEBUI_SCRIPT_JS
    start = source.find("const STANDARD_VIEWS =")
    end = source.find("\nfunction webglCapability()", start)
    if start < 0 or end < 0:
        raise AssertionError("could not extract camera contract source")
    return source[start:end]


def _axis_clipping_contract_source():
    source = tcad._WEBUI_SCRIPT_JS
    start = source.find("const CLIP_AXES =")
    end = source.find("\nfunction _cutawayCapOpacity()", start)
    if start < 0 or end < 0:
        raise AssertionError("could not extract axis clipping contract source")
    return source[start:end]


class WebGLCapabilityContractTests(unittest.TestCase):
    def test_probe_uses_a_temporary_canvas_and_prefers_webgl2(self):
        self.assertNotIn("_webglAvailable", tcad._WEBUI_SCRIPT_JS)
        capability = _extract_function("webglCapability", "_autoFallbackEnabled")
        result = _run_node(
            f"""
const calls = [];
const actualViewerCanvas = {{
  getContext() {{ throw new Error('the real viewer canvas was probed'); }}
}};
const document = {{
  createElement(tag) {{
    if (tag !== 'canvas') throw new Error('unexpected element');
    return {{
      getContext(kind) {{
        calls.push(kind);
        return kind === 'webgl2' ? {{ version: 2 }} : null;
      }}
    }};
  }}
}};
{capability}
const value = webglCapability();
console.log(JSON.stringify({{ value, calls }}));
"""
        )

        self.assertEqual(result["value"], {"ok": True, "version": 2, "reason": ""})
        self.assertEqual(result["calls"], ["webgl2"])

    def test_probe_falls_back_to_webgl1_and_reports_probe_errors(self):
        capability = _extract_function("webglCapability", "_autoFallbackEnabled")
        result = _run_node(
            f"""
let mode = 'webgl1';
const calls = [];
const document = {{
  createElement() {{
    return {{
      getContext(kind) {{
        calls.push(`${{mode}}:${{kind}}`);
        if (mode === 'throw') throw new Error('controlled probe failure');
        return (mode === 'webgl1' && kind === 'webgl') ? {{ version: 1 }} : null;
      }}
    }};
  }}
}};
{capability}
const webgl1 = webglCapability();
mode = 'throw';
const failed = webglCapability();
console.log(JSON.stringify({{ webgl1, failed, calls }}));
"""
        )

        self.assertEqual(result["webgl1"], {"ok": True, "version": 1, "reason": ""})
        self.assertFalse(result["failed"]["ok"])
        self.assertEqual(result["failed"]["version"], 0)
        self.assertIn("controlled probe failure", result["failed"]["reason"])
        self.assertEqual(result["calls"][:2], ["webgl1:webgl2", "webgl1:webgl"])


class ViewerInitializationContractTests(unittest.TestCase):
    def test_renderer_failure_falls_back_without_probing_the_real_canvas(self):
        normalize_reason = _extract_function(
            "_normalizeViewerFallbackReason", "_updateViewerBackendUI"
        )
        init_viewer = _extract_function("initViewer", "formatLenNm")
        result = _run_node(
            f"""
const events = [];
const actualCanvas = {{
  getContext() {{ throw new Error('real canvas getContext must not be called'); }},
  getBoundingClientRect() {{ return {{ width: 640, height: 480 }}; }}
}};
const state = {{ viewerReady: false, viewerBackend: 'remote', forceRender: null }};
const window = {{ THREE: null, devicePixelRatio: 1, addEventListener() {{}} }};
const THREE = window.THREE = {{
  WebGLRenderer: function () {{ events.push('renderer'); throw new Error('controlled renderer failure'); }},
  STLLoader: function () {{}},
  Object3D: {{ DEFAULT_UP: {{ set() {{}} }} }}
}};
let renderer = null, scene = null, camera = null, meshGroup = null, loader = null, controls = null;
function $(id) {{ if (id !== 'viewer-canvas') throw new Error(`unexpected ${{id}}`); return actualCanvas; }}
function webglCapability() {{ events.push('capability'); return {{ ok: true, version: 2, reason: '' }}; }}
function getClientPerf() {{ return {{ onDemand: false, antialias: true, dprCap: 1, damping: false }}; }}
function getRenderQuality() {{ return 'high'; }}
function _autoFallbackEnabled() {{ return true; }}
function initRemoteViewer(reason) {{ events.push(`remote:${{reason}}`); state.viewerBackend = 'remote'; state.viewerReady = true; }}
function showNotification() {{}}
function requestWebglRender() {{}}
function updateRuler3d() {{}}
function _updateViewerBackendUI() {{}}
{normalize_reason}
{init_viewer}
initViewer();
console.log(JSON.stringify({{ events, state, rendererIsNull: renderer === null }}));
"""
        )

        self.assertEqual(result["events"][:2], ["capability", "renderer"])
        self.assertTrue(result["events"][2].startswith("remote:"))
        self.assertIn("controlled renderer failure", result["events"][2])
        self.assertEqual(result["state"]["viewerBackend"], "remote")
        self.assertTrue(result["state"]["viewerReady"])
        self.assertTrue(result["rendererIsNull"])

    def test_backend_becomes_webgl_only_after_renderer_succeeds(self):
        self.assertRegex(tcad._WEBUI_SCRIPT_JS, r"viewerBackend:\s*'pending'")
        init_viewer = _extract_function("initViewer", "formatLenNm")
        result = _run_node(
            f"""
const events = [];
const actualCanvas = {{
  getContext() {{ throw new Error('real canvas getContext must not be called directly'); }},
  getBoundingClientRect() {{ return {{ width: 640, height: 480 }}; }}
}};
const state = {{ viewerReady: false, viewerBackend: 'pending', viewerFallbackReason: 'old', forceRender: null }};
const window = {{ devicePixelRatio: 1, addEventListener(kind) {{ events.push(`listen:${{kind}}`); }} }};
function Node() {{ this.position = {{ set() {{}} }}; }}
Node.prototype.add = function () {{}};
function Camera(kind) {{
  this.kind = kind;
  this.up = {{ set() {{}} }};
  this.position = {{ set() {{}} }};
  this.updateProjectionMatrix = function () {{}};
}}
const THREE = window.THREE = {{
  WebGLRenderer: function () {{
    events.push(`renderer:backend=${{state.viewerBackend}}`);
    this.domElement = actualCanvas;
    this.capabilities = {{ isWebGL2: false }};
    this.shadowMap = {{}};
    this.info = {{}};
    this.setPixelRatio = function () {{}};
    this.setClearColor = function () {{}};
    this.setSize = function () {{}};
    this.dispose = function () {{ events.push('dispose'); }};
  }},
  STLLoader: function () {{}},
  Object3D: {{ DEFAULT_UP: {{ set() {{}} }} }},
  Scene: function () {{ this.add = function () {{}}; }},
  Color: function () {{}},
  PerspectiveCamera: function () {{ events.push('perspective-camera'); Camera.call(this, 'perspective'); }},
  OrthographicCamera: function () {{ events.push('orthographic-camera'); Camera.call(this, 'orthographic'); }},
  Group: function () {{}},
  HemisphereLight: Node,
  DirectionalLight: Node,
  AmbientLight: Node,
  OrbitControls: function (object) {{
    events.push(`controls:${{object.kind}}`);
    this.object = object;
    this.addEventListener = function () {{}};
  }},
  ACESFilmicToneMapping: 1,
  sRGBEncoding: 2,
  SRGBColorSpace: 3
}};
let renderer = null, scene = null, camera = null, perspectiveCamera = null, orthographicCamera = null, meshGroup = null, loader = null, controls = null;
let cameraMode = 'perspective';
let _viewerResizeHandler = null;
function $(id) {{ if (id !== 'viewer-canvas') throw new Error(`unexpected ${{id}}`); return actualCanvas; }}
function webglCapability() {{ events.push('capability'); return {{ ok: true, version: 2, reason: '' }}; }}
function getClientPerf() {{ return {{ onDemand: false, antialias: true, dprCap: 1, damping: false }}; }}
function getRenderQuality() {{ return 'high'; }}
function _autoFallbackEnabled() {{ return true; }}
function initRemoteViewer(reason) {{ throw new Error(`unexpected remote fallback: ${{reason}}`); }}
function showNotification() {{}}
function requestWebglRender() {{}}
function updateRuler3d() {{}}
function applySliceViewOffset3d() {{}}
function _updateViewerBackendUI() {{ events.push('backend-ui'); }}
{_camera_contract_source()}
{init_viewer}
initViewer();
console.log(JSON.stringify({{
  events,
  state,
  dualCameras: !!perspectiveCamera && !!orthographicCamera,
  activeIsPerspective: camera === perspectiveCamera,
  controlsOwnsActive: !!controls && controls.object === camera,
  cameraMode
}}));
"""
        )

        self.assertIn("renderer:backend=pending", result["events"])
        self.assertEqual(result["state"]["viewerBackend"], "webgl")
        self.assertEqual(result["state"]["viewerWebglVersion"], 1)
        self.assertEqual(result["state"]["viewerFallbackReason"], "")
        self.assertTrue(result["state"]["viewerReady"])
        self.assertTrue(result["dualCameras"])
        self.assertTrue(result["activeIsPerspective"])
        self.assertTrue(result["controlsOwnsActive"])
        self.assertEqual(result["cameraMode"], "perspective")

    def test_post_renderer_initialization_failures_are_atomic(self):
        normalize_reason = _extract_function(
            "_normalizeViewerFallbackReason", "_updateViewerBackendUI"
        )
        init_viewer = _extract_function("initViewer", "formatLenNm")
        result = _run_node(
            f"""
let state, window, THREE;
let renderer, scene, camera, perspectiveCamera, orthographicCamera, meshGroup, loader, controls, _viewerResizeHandler;
let _webglAnimActive, _webglNeedRender, _webglRenderTimer;
let events, listeners, failAt, actualCanvas;

function Node() {{ this.position = {{ set() {{}} }}; }}
Node.prototype.add = function () {{}};
function $(_id) {{ return actualCanvas; }}
function webglCapability() {{ return {{ ok: true, version: 2, reason: '' }}; }}
function getClientPerf() {{ return {{ onDemand: false, antialias: true, dprCap: 1, damping: false }}; }}
function getRenderQuality() {{ return 'high'; }}
function _autoFallbackEnabled() {{ return true; }}
function showNotification() {{}}
function applySliceViewOffset3d() {{}}
function scheduleCaptureView3d() {{}}
function updateRuler3d() {{}}
function _updateViewerBackendUI() {{}}
function disposeObject3DDeep() {{ events.push('scene-dispose'); }}
function initRemoteViewer(reason) {{
  events.push(`remote:${{reason}}`);
  state.viewerBackend = 'remote';
  state.viewerWebglVersion = 0;
  state.viewerFallbackReason = reason;
  state.viewerReady = true;
}}
function requestWebglRender() {{
  if (failAt === 'first-render') throw new Error('controlled first render failure');
}}

{normalize_reason}
{init_viewer}

function runCase(which) {{
  failAt = which;
  events = [];
  listeners = new Set();
  state = {{ viewerReady: false, viewerBackend: 'pending', viewerWebglVersion: 0, viewerFallbackReason: '', forceRender: null }};
  renderer = scene = camera = meshGroup = loader = controls = _viewerResizeHandler = null;
  perspectiveCamera = {{ stale: true }};
  orthographicCamera = {{ stale: true }};
  _webglAnimActive = true;
  _webglNeedRender = true;
  _webglRenderTimer = null;
  actualCanvas = {{
    getContext() {{ throw new Error('real canvas must not be probed'); }},
    getBoundingClientRect() {{ return {{ width: 640, height: 480 }}; }}
  }};
  window = {{
    devicePixelRatio: 1,
    THREE: null,
    addEventListener(kind, fn) {{ if (kind === 'resize') listeners.add(fn); }},
    removeEventListener(kind, fn) {{ if (kind === 'resize') listeners.delete(fn); }}
  }};
  THREE = window.THREE = {{
    WebGLRenderer: function () {{
      this.domElement = actualCanvas;
      this.capabilities = {{ isWebGL2: false }};
      this.shadowMap = {{}};
      this.info = {{}};
      this.setPixelRatio = function () {{}};
      this.setClearColor = function () {{}};
      this.setSize = function () {{}};
      this.dispose = function () {{ events.push('renderer-dispose'); }};
      this.forceContextLoss = function () {{ events.push('renderer-force-loss'); }};
    }},
    STLLoader: function () {{}},
    Object3D: {{ DEFAULT_UP: {{ set() {{}} }} }},
    Scene: function () {{
      if (failAt === 'scene') throw new Error('controlled scene failure');
      this.add = function () {{}};
    }},
    Color: function () {{}},
    PerspectiveCamera: function () {{
      this.up = {{ set() {{}} }};
      this.position = {{ set() {{}} }};
      this.updateProjectionMatrix = function () {{}};
    }},
    OrthographicCamera: function () {{
      this.up = {{ set() {{}} }};
      this.position = {{ set() {{}} }};
      this.updateProjectionMatrix = function () {{}};
    }},
    Group: function () {{}},
    HemisphereLight: Node,
    DirectionalLight: Node,
    AmbientLight: Node,
    OrbitControls: function () {{
      this.addEventListener = function () {{}};
      this.dispose = function () {{ events.push('controls-dispose'); }};
    }},
    ACESFilmicToneMapping: 1,
    sRGBEncoding: 2,
    SRGBColorSpace: 3
  }};

  initViewer();
  return {{
    events: events.slice(),
    listenerCount: listeners.size,
    refsCleared: [renderer, scene, camera, perspectiveCamera, orthographicCamera, meshGroup, loader, controls, _viewerResizeHandler].every((v) => v === null),
    state: {{ ...state }}
  }};
}}

const sceneFailure = runCase('scene');
const lateFailure = runCase('first-render');
console.log(JSON.stringify({{ sceneFailure, lateFailure }}));
"""
        )

        for name in ("sceneFailure", "lateFailure"):
            with self.subTest(case=name):
                case = result[name]
                self.assertIn("renderer-dispose", case["events"])
                self.assertIn("renderer-force-loss", case["events"])
                self.assertTrue(any(item.startswith("remote:") for item in case["events"]))
                self.assertEqual(case["listenerCount"], 0)
                self.assertTrue(case["refsCleared"])
                self.assertEqual(case["state"]["viewerBackend"], "remote")
                self.assertEqual(case["state"]["viewerWebglVersion"], 0)
                self.assertTrue(case["state"]["viewerReady"])
        self.assertNotIn("controls-dispose", result["sceneFailure"]["events"])
        self.assertIn("controls-dispose", result["lateFailure"]["events"])

    def test_remote_status_is_visible_and_webgl_only_cutaway_is_disabled(self):
        normalize_reason = _extract_function(
            "_normalizeViewerFallbackReason", "_updateViewerBackendUI"
        )
        update_ui = _extract_function("_updateViewerBackendUI", "_remoteCaptureView")
        result = _run_node(
            f"""
const elements = {{
  'viewer-backend-status': {{ textContent: '', hidden: true, title: '' }},
  'viewer-hint': {{ textContent: '', style: {{ display: 'none' }} }},
  'slice-cutaway-toggle': {{ disabled: false, checked: true, title: '' }},
  'slice-cutaway-toggle-wrap': {{ title: '', dataset: {{}}, setAttribute(k, v) {{ this[k] = v; }} }}
}};
const state = {{ viewerBackend: 'remote', viewerFallbackReason: '<b>GPU failed</b>' }};
function $(id) {{ return elements[id] || null; }}
{normalize_reason}
{update_ui}
_updateViewerBackendUI();
console.log(JSON.stringify({{ elements, state }}));
"""
        )

        status = result["elements"]["viewer-backend-status"]
        self.assertFalse(status["hidden"])
        self.assertEqual(status["textContent"], "Host Render · <b>GPU failed</b>")
        self.assertIn("Host Render", result["elements"]["viewer-hint"]["textContent"])
        self.assertIn("<b>GPU failed</b>", result["elements"]["viewer-hint"]["textContent"])
        cutaway = result["elements"]["slice-cutaway-toggle"]
        self.assertTrue(cutaway["disabled"])
        self.assertFalse(cutaway["checked"])
        self.assertIn("GPU failed", cutaway["title"])


class CameraContractTests(unittest.TestCase):
    @staticmethod
    def _node_prelude():
        return r"""
class Vector3 {
  constructor(x = 0, y = 0, z = 0) { this.set(x, y, z); }
  set(x, y, z) { this.x = Number(x); this.y = Number(y); this.z = Number(z); return this; }
  copy(v) { return this.set(v.x, v.y, v.z); }
  clone() { return new Vector3(this.x, this.y, this.z); }
  sub(v) { this.x -= v.x; this.y -= v.y; this.z -= v.z; return this; }
  addScaledVector(v, s) { this.x += v.x * s; this.y += v.y * s; this.z += v.z * s; return this; }
  multiplyScalar(s) { this.x *= s; this.y *= s; this.z *= s; return this; }
  length() { return Math.hypot(this.x, this.y, this.z); }
  normalize() { const n = this.length() || 1; return this.multiplyScalar(1 / n); }
  distanceTo(v) { return Math.hypot(this.x - v.x, this.y - v.y, this.z - v.z); }
}
class Box3 {
  constructor(min = null, max = null) {
    this.min = min ? min.clone() : new Vector3(Infinity, Infinity, Infinity);
    this.max = max ? max.clone() : new Vector3(-Infinity, -Infinity, -Infinity);
  }
  makeEmpty() {
    this.min.set(Infinity, Infinity, Infinity);
    this.max.set(-Infinity, -Infinity, -Infinity);
    return this;
  }
  setFromObject(obj) {
    this.makeEmpty();
    if (obj && obj.__box) this.union(new Box3(obj.__box.min, obj.__box.max));
    return this;
  }
  isEmpty() { return this.max.x < this.min.x || this.max.y < this.min.y || this.max.z < this.min.z; }
  clone() { return new Box3(this.min, this.max); }
  applyMatrix4() { return this; }
  union(box) {
    this.min.set(Math.min(this.min.x, box.min.x), Math.min(this.min.y, box.min.y), Math.min(this.min.z, box.min.z));
    this.max.set(Math.max(this.max.x, box.max.x), Math.max(this.max.y, box.max.y), Math.max(this.max.z, box.max.z));
    return this;
  }
  getCenter(out) {
    return out.set((this.min.x + this.max.x) / 2, (this.min.y + this.max.y) / 2, (this.min.z + this.max.z) / 2);
  }
  getSize(out) {
    return out.set(this.max.x - this.min.x, this.max.y - this.min.y, this.max.z - this.min.z);
  }
}
function makeCamera(kind) {
  return {
    kind,
    isPerspectiveCamera: kind === 'perspective',
    isOrthographicCamera: kind === 'orthographic',
    position: new Vector3(), up: new Vector3(0, 0, 1), quaternion: { copy() { return this; } },
    fov: 50, zoom: 1, aspect: 1, left: -1, right: 1, top: 1, bottom: -1,
    near: 0.001, far: 1000, projectionUpdates: 0,
    updateProjectionMatrix() { this.projectionUpdates += 1; },
    lookAt(v) { this.lookTarget = v.clone(); }
  };
}
const THREE = { Vector3, Box3 };
const window = { THREE };
let perspectiveCamera = makeCamera('perspective');
let orthographicCamera = makeCamera('orthographic');
let camera = perspectiveCamera;
let cameraMode = 'perspective';
let meshGroup = {
  children: [{}],
  __box: { min: new Vector3(2, 4, 6), max: new Vector3(10, 14, 18) },
  updateMatrixWorld() {},
  traverseVisible(fn) {
    fn({
      geometry: { boundingBox: new Box3(this.__box.min, this.__box.max) },
      matrixWorld: null
    });
  }
};
const controls = {
  object: camera,
  target: new Vector3(),
  updates: 0,
  update() { this.updates += 1; }
};
const state = { viewerBackend: 'webgl', viewerMode: '3d', _viewApplying: false };
const elements = {};
function $(id) { return elements[id] || null; }
function requestWebglRender() {}
function applySliceViewOffset3d() {}
function updateRuler3d() {}
function scheduleCaptureView3d() {}
function _normalizeViewerFallbackReason(value) { return String(value || 'WebGL unavailable'); }
"""

    def test_seven_standard_views_fit_real_bounds_with_finite_pose(self):
        result = _run_node(
            self._node_prelude()
            + _camera_contract_source()
            + r"""
const results = {};
for (const name of ['ISO', 'TOP', 'BOTTOM', 'FRONT', 'BACK', 'LEFT', 'RIGHT']) {
  if (!applyStandardView(name)) throw new Error(`view ${name} was rejected`);
  results[name] = {
    position: [camera.position.x, camera.position.y, camera.position.z],
    up: [camera.up.x, camera.up.y, camera.up.z],
    target: [controls.target.x, controls.target.y, controls.target.z],
    near: camera.near,
    far: camera.far
  };
}
console.log(JSON.stringify(results));
"""
        )

        center = [6, 9, 12]
        expected_signs = {
            "TOP": [0, 0, 1], "BOTTOM": [0, 0, -1],
            "FRONT": [0, -1, 0], "BACK": [0, 1, 0],
            "LEFT": [-1, 0, 0], "RIGHT": [1, 0, 0],
            "ISO": [1, -1, 1],
        }
        for name, pose in result.items():
            with self.subTest(view=name):
                values = pose["position"] + pose["up"] + pose["target"] + [pose["near"], pose["far"]]
                self.assertTrue(all(isinstance(value, (int, float)) for value in values))
                self.assertEqual(pose["target"], center)
                self.assertGreater(pose["near"], 0)
                self.assertGreater(pose["far"], pose["near"])
                delta = [pose["position"][i] - center[i] for i in range(3)]
                for component, sign in zip(delta, expected_signs[name]):
                    if sign == 0:
                        self.assertAlmostEqual(component, 0, places=8)
                    else:
                        self.assertGreater(component * sign, 0)
        iso_delta = [result["ISO"]["position"][i] - center[i] for i in range(3)]
        self.assertAlmostEqual(iso_delta[1] / iso_delta[0], -1.0, places=8)
        self.assertAlmostEqual(iso_delta[2] / iso_delta[0], 0.8, places=8)

    def test_camera_bounds_ignore_hidden_geometry_and_use_three_r145_world_bounds(self):
        result = _run_node(
            r"""
const THREE = require('./three.js');
let perspectiveCamera = null, orthographicCamera = null, camera = null, controls = null;
let cameraMode = 'perspective', meshGroup = null;
const state = { viewerBackend: 'webgl' };
function $() { return null; }
function requestWebglRender() {}
function applySliceViewOffset3d() {}
function updateRuler3d() {}
function scheduleCaptureView3d() {}
"""
            + _camera_contract_source()
            + r"""
function compact(bounds) {
  return {
    center: bounds.center.toArray(),
    size: bounds.size.toArray(),
    radius: bounds.radius
  };
}

const root = new THREE.Group();
const near = new THREE.Mesh(new THREE.BoxGeometry(2, 4, 6));
near.position.set(4, 5, 6);
root.add(near);

const farHidden = new THREE.Mesh(new THREE.BoxGeometry(40, 40, 40));
farHidden.position.set(1000, 1000, 1000);
farHidden.visible = false;
root.add(farHidden);

const hiddenParent = new THREE.Group();
hiddenParent.visible = false;
const hiddenChild = new THREE.Mesh(new THREE.BoxGeometry(30, 30, 30));
hiddenChild.position.set(-900, -900, -900);
hiddenParent.add(hiddenChild);
root.add(hiddenParent);

const visibleOnly = compact(_viewerCameraBounds(root));
const empty = compact(_viewerCameraBounds(new THREE.Group()));
const pointGeometry = new THREE.BufferGeometry();
pointGeometry.setAttribute('position', new THREE.Float32BufferAttribute([7, 8, 9], 3));
const degenerate = compact(_viewerCameraBounds(new THREE.Mesh(pointGeometry)));
near.position.set(Infinity, 0, 0);
const invalid = compact(_viewerCameraBounds(root));
console.log(JSON.stringify({ visibleOnly, empty, degenerate, invalid, revision: THREE.REVISION }));
"""
        )

        self.assertEqual(result["revision"], "145")
        self.assertEqual(result["visibleOnly"]["center"], [4, 5, 6])
        self.assertEqual(result["visibleOnly"]["size"], [2, 4, 6])
        for key in ("empty", "degenerate", "invalid"):
            with self.subTest(case=key):
                self.assertEqual(result[key]["center"], [0, 0, 0])
                self.assertEqual(result[key]["size"], [1, 1, 1])
                self.assertAlmostEqual(result[key]["radius"], 3 ** 0.5 / 2)

    def test_projection_switch_preserves_visible_scale_and_controls_object(self):
        result = _run_node(
            self._node_prelude()
            + _camera_contract_source()
            + r"""
controls.target.set(6, 9, 12);
perspectiveCamera.position.set(6, -11, 12);
const before = viewerVisibleHalfHeight(perspectiveCamera, controls.target);
const toOrtho = setCameraMode('orthographic');
const orthoScale = viewerVisibleHalfHeight(camera, controls.target);
const orthoOwnsControls = controls.object === orthographicCamera;
const toPerspective = setCameraMode('perspective');
const after = viewerVisibleHalfHeight(camera, controls.target);
console.log(JSON.stringify({ before, orthoScale, after, toOrtho, toPerspective, orthoOwnsControls, perspectiveOwnsControls: controls.object === perspectiveCamera }));
"""
        )

        self.assertTrue(result["toOrtho"])
        self.assertTrue(result["toPerspective"])
        self.assertTrue(result["orthoOwnsControls"])
        self.assertTrue(result["perspectiveOwnsControls"])
        self.assertAlmostEqual(result["orthoScale"] / result["before"], 1, delta=0.03)
        self.assertAlmostEqual(result["after"] / result["before"], 1, delta=0.03)

    def test_resize_updates_both_camera_projections(self):
        result = _run_node(
            self._node_prelude()
            + _camera_contract_source()
            + r"""
orthographicCamera.top = 3;
orthographicCamera.bottom = -3;
const before = [perspectiveCamera.projectionUpdates, orthographicCamera.projectionUpdates];
_resizeViewerCameras(900, 450);
console.log(JSON.stringify({
  perspectiveAspect: perspectiveCamera.aspect,
  orthoAspect: (orthographicCamera.right - orthographicCamera.left) / (orthographicCamera.top - orthographicCamera.bottom),
  updates: [perspectiveCamera.projectionUpdates - before[0], orthographicCamera.projectionUpdates - before[1]]
}));
"""
        )

        self.assertAlmostEqual(result["perspectiveAspect"], 2)
        self.assertAlmostEqual(result["orthoAspect"], 2)
        self.assertEqual(result["updates"], [1, 1])

    def test_viewer_mode_resize_entry_updates_both_camera_frustums(self):
        resize_cameras = _extract_function(
            "_resizeViewerCameras", "_setCameraClipRange"
        )
        set_mode = _extract_function("setViewerMode", "sliceInsetReservedCssPx")
        result = _run_node(
            r"""
function makeCamera(kind) {
  return {
    kind,
    isOrthographicCamera: kind === 'orthographic',
    aspect: 1,
    left: -3,
    right: 3,
    top: 3,
    bottom: -3,
    projectionUpdates: 0,
    updateProjectionMatrix() { this.projectionUpdates += 1; }
  };
}
let perspectiveCamera = makeCamera('perspective');
let orthographicCamera = makeCamera('orthographic');
let camera = orthographicCamera;
const state = { viewerMode: '2d', viewerBackend: 'webgl', previewStyle: 'solid', materials: [], meshes: new Map() };
const canvas = { style: {}, getBoundingClientRect() { return { width: 900, height: 450 }; } };
function $(id) { return id === 'viewer-canvas' ? canvas : null; }
const renderer = { sizes: [], setSize(w, h, css) { this.sizes.push([w, h, css]); } };
const calls = [];
function requestAnimationFrame(fn) { fn(); }
function applySliceViewOffset3d() { calls.push('slice-offset'); }
function drawSliceFromCache() {}
function _elementLegendVisible() {}
function syncSliceControls() {}
function applySliceOverlayUI() {}
function applySlice2dMultiUI() {}
function updateRuler3d() {}
function renderLegend() {}
function applyPreviewStyle() {}
function refreshSlice() {}
function refreshPreview() {}
"""
            + resize_cameras
            + set_mode
            + r"""
setViewerMode('3d', false);
console.log(JSON.stringify({
  perspectiveAspect: perspectiveCamera.aspect,
  orthoAspect: (orthographicCamera.right - orthographicCamera.left) / (orthographicCamera.top - orthographicCamera.bottom),
  orthoHalfHeight: (orthographicCamera.top - orthographicCamera.bottom) / 2,
  updates: [perspectiveCamera.projectionUpdates, orthographicCamera.projectionUpdates],
  sizes: renderer.sizes,
  calls
}));
"""
        )

        self.assertEqual(result["perspectiveAspect"], 2)
        self.assertEqual(result["orthoAspect"], 2)
        self.assertEqual(result["orthoHalfHeight"], 3)
        self.assertEqual(result["updates"], [1, 1])
        self.assertEqual(result["sizes"], [[900, 450, False]])
        self.assertEqual(result["calls"], ["slice-offset"])

    def test_slice_offset_entry_syncs_full_frustum_before_touching_active_camera(self):
        resize_cameras = _extract_function(
            "_resizeViewerCameras", "_setCameraClipRange"
        )
        source = tcad._WEBUI_SCRIPT_JS
        offset_start = source.find("function applySliceViewOffset3d(")
        offset_end = source.find("function syncSliceControls(", offset_start)
        if offset_start < 0 or offset_end < 0:
            self.fail("could not extract applySliceViewOffset3d")
        apply_offset = source[offset_start:offset_end]
        result = _run_node(
            r"""
const events = [];
function makeCamera(kind) {
  return {
    kind,
    aspect: 1,
    left: -5,
    right: 5,
    top: 5,
    bottom: -5,
    updateProjectionMatrix() { events.push(`update:${this.kind}`); },
    clearViewOffset() { events.push(`clear:${this.kind}`); },
    setViewOffset(...args) { events.push(`set:${this.kind}:${args.join(',')}`); }
  };
}
let perspectiveCamera = makeCamera('perspective');
let orthographicCamera = makeCamera('orthographic');
let camera = orthographicCamera;
let reserve = 0;
let rect = { width: 800, height: 400 };
const state = { viewerBackend: 'webgl', viewerMode: '3d', sliceOverlay: false };
const canvas = { getBoundingClientRect() { return rect; } };
function $(id) { return id === 'viewer-canvas' ? canvas : null; }
function sliceInsetReservedCssPx() { return reserve; }
"""
            + resize_cameras
            + apply_offset
            + r"""
function snapshot(label) {
  return {
    label,
    perspectiveAspect: perspectiveCamera.aspect,
    orthoAspect: (orthographicCamera.right - orthographicCamera.left) / (orthographicCamera.top - orthographicCamera.bottom),
    orthoHalfHeight: (orthographicCamera.top - orthographicCamera.bottom) / 2,
    events: events.splice(0)
  };
}

applySliceViewOffset3d();
const noOverlay = snapshot('no-overlay');

state.sliceOverlay = true;
rect = { width: 900, height: 300 };
reserve = 0;
applySliceViewOffset3d();
const noReserve = snapshot('no-reserve');

rect = { width: 800, height: 400 };
reserve = 100;
applySliceViewOffset3d();
const withOverlay = snapshot('with-overlay');
console.log(JSON.stringify({ noOverlay, noReserve, withOverlay }));
"""
        )

        self.assertEqual(result["noOverlay"]["perspectiveAspect"], 2)
        self.assertEqual(result["noOverlay"]["orthoAspect"], 2)
        self.assertEqual(
            result["noOverlay"]["events"],
            ["update:perspective", "update:orthographic", "clear:orthographic"],
        )
        self.assertEqual(result["noReserve"]["perspectiveAspect"], 3)
        self.assertEqual(result["noReserve"]["orthoAspect"], 3)
        self.assertEqual(
            result["noReserve"]["events"],
            ["update:perspective", "update:orthographic", "clear:orthographic"],
        )
        self.assertAlmostEqual(result["withOverlay"]["perspectiveAspect"], 2.25)
        self.assertAlmostEqual(result["withOverlay"]["orthoAspect"], 2.25)
        self.assertEqual(result["withOverlay"]["orthoHalfHeight"], 5)
        self.assertEqual(
            result["withOverlay"]["events"],
            [
                "update:perspective",
                "update:orthographic",
                "set:orthographic:900,400,100,0,800,400",
            ],
        )

    def test_remote_disables_camera_controls_and_webgl_restores_them(self):
        normalize_reason = _extract_function(
            "_normalizeViewerFallbackReason", "_updateViewerBackendUI"
        )
        update_ui = _extract_function("_updateViewerBackendUI", "_remoteCaptureView")
        result = _run_node(
            f"""
const ids = ['viewer-camera-mode', 'viewer-view-iso', 'viewer-view-top', 'viewer-view-bottom', 'viewer-view-front', 'viewer-view-back', 'viewer-view-left', 'viewer-view-right'];
const elements = {{
  'viewer-backend-status': {{ textContent: '', hidden: true, title: '' }},
  'viewer-hint': {{ textContent: '', style: {{ display: 'none' }} }},
  'slice-cutaway-toggle': {{ disabled: false, checked: true, title: '' }},
  'slice-cutaway-toggle-wrap': {{ title: '', dataset: {{}}, setAttribute(k, v) {{ this[k] = v; }} }}
}};
for (const id of ids) elements[id] = {{ disabled: false, title: `original:${{id}}`, dataset: {{}}, setAttribute(k, v) {{ this[k] = v; }} }};
const state = {{ viewerBackend: 'remote', viewerMode: '3d', viewerFallbackReason: 'GPU unavailable' }};
function $(id) {{ return elements[id] || null; }}
{normalize_reason}
{update_ui}
_updateViewerBackendUI();
const remote = ids.map((id) => ({{ disabled: elements[id].disabled, title: elements[id].title, aria: elements[id]['aria-disabled'] }}));
state.viewerBackend = 'webgl';
_updateViewerBackendUI();
const webgl = ids.map((id) => ({{ disabled: elements[id].disabled, title: elements[id].title, aria: elements[id]['aria-disabled'] }}));
console.log(JSON.stringify({{ remote, webgl }}));
"""
        )

        self.assertTrue(all(item["disabled"] for item in result["remote"]))
        self.assertTrue(all("Host Render" in item["title"] for item in result["remote"]))
        self.assertTrue(all(item["aria"] == "true" for item in result["remote"]))
        self.assertTrue(all(not item["disabled"] for item in result["webgl"]))
        self.assertTrue(all(item["title"].startswith("original:") for item in result["webgl"]))
        self.assertTrue(all(item["aria"] == "false" for item in result["webgl"]))

    def test_camera_control_events_dispatch_mode_and_standard_view(self):
        bind_controls = _extract_function(
            "bindViewerCameraControls", "webglCapability"
        )
        result = _run_node(
            f"""
const calls = [];
function makeElement(value = '') {{
  return {{
    value,
    dataset: {{}},
    listeners: {{}},
    addEventListener(kind, fn) {{ this.listeners[kind] = fn; }}
  }};
}}
const elements = {{
  'viewer-camera-mode': makeElement('perspective'),
  'viewer-view-iso': makeElement(),
  'viewer-view-top': makeElement()
}};
elements['viewer-view-iso'].dataset.standardView = 'ISO';
elements['viewer-view-top'].dataset.standardView = 'TOP';
function $(id) {{ return elements[id] || null; }}
function setCameraMode(mode) {{ calls.push(`mode:${{mode}}`); return true; }}
function applyStandardView(name) {{ calls.push(`view:${{name}}`); return true; }}
{bind_controls}
bindViewerCameraControls();
elements['viewer-camera-mode'].value = 'orthographic';
elements['viewer-camera-mode'].listeners.change();
elements['viewer-view-iso'].listeners.click();
elements['viewer-view-top'].listeners.click();
console.log(JSON.stringify({{ calls }}));
"""
        )

        self.assertEqual(
            result["calls"],
            ["mode:orthographic", "view:ISO", "view:TOP"],
        )
        self.assertRegex(
            tcad._WEBUI_INDEX_HTML,
            r'id="viewer-camera-controls"[^>]+aria-label="[^"]+"',
        )
        for suffix in ("iso", "top", "bottom", "front", "back", "left", "right"):
            self.assertRegex(
                tcad._WEBUI_INDEX_HTML,
                rf'id="viewer-view-{suffix}"[^>]+aria-label="[^"]+"',
            )

    def test_capture_and_restore_preserve_projection_mode_and_legacy_views(self):
        capture = _extract_function("captureView3dNow", "scheduleCaptureView3d")
        apply_view = _extract_function("applyView3d", "centerObjectAtOrigin")
        result = _run_node(
            self._node_prelude()
            + _camera_contract_source()
            + capture
            + apply_view
            + r"""
camera = orthographicCamera;
cameraMode = 'orthographic';
controls.object = camera;
camera.position.set(9, -3, 7);
camera.up.set(0, 0, 1);
camera.zoom = 1.75;
controls.target.set(2, 4, 6);
captureView3dNow();
const saved = JSON.parse(JSON.stringify(state.view3d));

camera = perspectiveCamera;
cameraMode = 'perspective';
controls.object = camera;
const restored = applyView3d(saved);
const restoredMode = cameraMode;
const restoredOwnsControls = controls.object === orthographicCamera;
const restoredPosition = [camera.position.x, camera.position.y, camera.position.z];

const legacy = { pos: [1, 2, 3], target: [4, 5, 6], up: [0, 0, 1], zoom: 1 };
const legacyRestored = applyView3d(legacy);
console.log(JSON.stringify({
  saved,
  restored,
  restoredMode,
  restoredOwnsControls,
  restoredPosition,
  legacyRestored,
  legacyMode: cameraMode,
  legacyPosition: [camera.position.x, camera.position.y, camera.position.z]
}));
"""
        )

        self.assertEqual(result["saved"]["cameraMode"], "orthographic")
        self.assertTrue(result["restored"])
        self.assertEqual(result["restoredMode"], "orthographic")
        self.assertTrue(result["restoredOwnsControls"])
        self.assertEqual(result["restoredPosition"], [9, -3, 7])
        self.assertTrue(result["legacyRestored"])
        self.assertEqual(result["legacyMode"], "orthographic")
        self.assertEqual(result["legacyPosition"], [1, 2, 3])

    def test_fresh_camera_roundtrip_restores_orthographic_visible_scale(self):
        capture = _extract_function("captureView3dNow", "scheduleCaptureView3d")
        apply_view = _extract_function("applyView3d", "centerObjectAtOrigin")
        result = _run_node(
            self._node_prelude()
            + _camera_contract_source()
            + capture
            + apply_view
            + r"""
camera = orthographicCamera;
cameraMode = 'orthographic';
controls.object = camera;
camera.left = -40;
camera.right = 40;
camera.top = 20;
camera.bottom = -20;
camera.zoom = 2;
camera.position.set(9, -3, 7);
camera.up.set(0, 0, 1);
controls.target.set(2, 4, 6);
const before = viewerVisibleHalfHeight(camera, controls.target);
captureView3dNow();
const saved = JSON.parse(JSON.stringify(state.view3d));

perspectiveCamera = makeCamera('perspective');
perspectiveCamera.aspect = 2.5;
orthographicCamera = makeCamera('orthographic');
camera = perspectiveCamera;
cameraMode = 'perspective';
controls.object = camera;
controls.target.set(0, 0, 0);

const restored = applyView3d(saved);
const after = viewerVisibleHalfHeight(camera, controls.target);
console.log(JSON.stringify({
  before,
  saved,
  restored,
  after,
  cameraMode,
  target: [controls.target.x, controls.target.y, controls.target.z],
  activeIsFreshOrtho: camera === orthographicCamera,
  controlsOwnsFreshOrtho: controls.object === orthographicCamera,
  frustum: [camera.left, camera.right, camera.top, camera.bottom, camera.zoom]
}));
"""
        )

        self.assertEqual(result["before"], 10)
        self.assertEqual(result["saved"].get("orthographicVisibleHalfHeight"), 10)
        self.assertTrue(result["restored"])
        self.assertEqual(result["cameraMode"], "orthographic")
        self.assertEqual(result["target"], [2, 4, 6])
        self.assertTrue(result["activeIsFreshOrtho"])
        self.assertTrue(result["controlsOwnsFreshOrtho"])
        self.assertAlmostEqual(result["after"], 10, places=8)
        self.assertEqual(result["frustum"], [-25, 25, 10, -10, 1])

    def test_top_view_roundtrip_preserves_zero_z_up_on_fresh_cameras(self):
        capture = _extract_function("captureView3dNow", "scheduleCaptureView3d")
        apply_view = _extract_function("applyView3d", "centerObjectAtOrigin")
        result = _run_node(
            self._node_prelude()
            + _camera_contract_source()
            + capture
            + apply_view
            + r"""
setCameraMode('orthographic');
if (!applyStandardView('TOP')) throw new Error('TOP view rejected');
captureView3dNow();
const saved = JSON.parse(JSON.stringify(state.view3d));

perspectiveCamera = makeCamera('perspective');
perspectiveCamera.aspect = 2;
orthographicCamera = makeCamera('orthographic');
camera = perspectiveCamera;
cameraMode = 'perspective';
controls.object = camera;
controls.target.set(0, 0, 0);

const restored = applyView3d(saved);
const restoredUp = [camera.up.x, camera.up.y, camera.up.z];
const invalidRestored = applyView3d({ ...saved, up: [NaN, Infinity] });
const invalidUp = [camera.up.x, camera.up.y, camera.up.z];
console.log(JSON.stringify({
  savedUp: saved.up,
  restored,
  restoredUp,
  cameraMode,
  target: [controls.target.x, controls.target.y, controls.target.z],
  controlsOwnsActive: controls.object === camera,
  activeIsFreshOrtho: camera === orthographicCamera,
  invalidRestored,
  invalidUp
}));
"""
        )

        self.assertEqual(result["savedUp"], [0, 1, 0])
        self.assertTrue(result["restored"])
        self.assertEqual(result["restoredUp"], [0, 1, 0])
        self.assertEqual(result["cameraMode"], "orthographic")
        self.assertEqual(result["target"], [6, 9, 12])
        self.assertTrue(result["controlsOwnsActive"])
        self.assertTrue(result["activeIsFreshOrtho"])
        self.assertTrue(result["invalidRestored"])
        self.assertEqual(result["invalidUp"], [0, 0, 1])

    def test_remote_apply_ignores_orthographic_scale_metadata(self):
        remote_apply = _extract_function("remoteApplyView", "remoteResetView")
        remote_payload = _extract_function(
            "remoteCameraPayload", "_remoteDesiredGbufferSize"
        )
        result = _run_node(
            r"""
const state = {};
const remoteOrbit = { theta: 0, phi: 0, radius: 1, target: [0, 0, 0], up: [0, 0, 1] };
const events = [];
function _remoteCaptureView() { events.push('capture'); }
function scheduleRemoteRender(highRes, delay) { events.push(`render:${highRes}:${delay}`); }
"""
            + remote_apply
            + remote_payload
            + r"""
const ok = remoteApplyView({
  pos: [12, 4, 6],
  target: [2, 4, 6],
  up: [0, 1, 0],
  cameraMode: 'orthographic',
  orthographicVisibleHalfHeight: 10
});
const payload = remoteCameraPayload();
const appliedUp = remoteOrbit.up.slice();
const invalidOk = remoteApplyView({ pos: [12, 4, 6], target: [2, 4, 6], up: [NaN, Infinity] });
const invalidUp = remoteOrbit.up.slice();
console.log(JSON.stringify({ ok, remoteOrbit, payload, appliedUp, invalidOk, invalidUp, events }));
"""
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["remoteOrbit"]["target"], [2, 4, 6])
        self.assertEqual(result["remoteOrbit"]["radius"], 10)
        self.assertEqual(result["appliedUp"], [0, 1, 0])
        self.assertEqual(result["payload"]["up"], [0, 1, 0])
        self.assertTrue(result["invalidOk"])
        self.assertEqual(result["invalidUp"], [0, 0, 1])
        self.assertEqual(
            result["events"],
            ["capture", "render:true:30", "capture", "render:true:30"],
        )

    def test_host_camera_basis_preserves_zero_and_falls_back_for_invalid_up(self):
        basis = _extract_function("_remoteCameraBasis", "_remoteProjectToGbuf")
        result = _run_node(
            basis
            + r"""
const norm = (v) => Math.hypot(v[0], v[1], v[2]);
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const metrics = (name, value) => ({
  name,
  finite: [...value.pos, ...value.fwd, ...value.right, ...value.up].every(Number.isFinite),
  pos: value.pos,
  norms: [norm(value.fwd), norm(value.right), norm(value.up)].map((v) => Number.isFinite(v) ? v : -999),
  dots: [dot(value.fwd, value.right), dot(value.fwd, value.up), dot(value.right, value.up)].map((v) => Number.isFinite(v) ? v : -999)
});
const directions = [
  ['+X', [1, 0, 0]], ['-X', [-1, 0, 0]],
  ['+Y', [0, 1, 0]], ['-Y', [0, -1, 0]],
  ['+Z', [0, 0, 1]], ['-Z', [0, 0, -1]],
  ['near+X', [1, 1e-10, -2e-10]], ['near-X', [-1, 1e-10, 2e-10]],
  ['near+Y', [2e-10, 1, -1e-10]], ['near-Y', [-2e-10, -1, 1e-10]],
  ['near+Z', [1e-10, -2e-10, 1]], ['near-Z', [-1e-10, 2e-10, -1]]
];
const cases = [];
for (const [axis, fwd] of directions) {
  const pos = fwd.map((v) => -10 * v);
  const variants = [
    ['zero', [0, 0, 0]],
    ['parallel', fwd.slice()],
    ['anti-parallel', fwd.map((v) => -v)],
    ['invalid', [NaN, Infinity, undefined]]
  ];
  for (const [kind, up] of variants) {
    cases.push(metrics(`${axis}:${kind}`, _remoteCameraBasis({ pos, target: [0, 0, 0], up })));
  }
}
const malformedCameras = [
  ['invalid-pos', { pos: [Infinity, NaN, -Infinity], target: [0, 0, 0], up: [0, 1, 0] }],
  ['string-infinity-pos', { pos: ['Infinity', '-Infinity', undefined], target: [0, 0, 0], up: [0, 1, 0] }],
  ['invalid-target', { pos: [0, 0, 5], target: [NaN, Infinity, '-Infinity'], up: [0, 1, 0] }],
  ['missing-components', { pos: [], target: [], up: [0, 1, 0] }],
  ['missing-pos-target', { up: [0, 1, 0] }],
  ['coincident-pos-target', { pos: [4, 5, 6], target: [4, 5, 6], up: [0, 1, 0] }]
];
for (const [name, cam] of malformedCameras) {
  cases.push(metrics(name, _remoteCameraBasis(cam)));
}
const validYUp = _remoteCameraBasis({ pos: [0, 0, 10], target: [0, 0, 0], up: [0, 1, 0] });
const defaultCamera = _remoteCameraBasis({ up: [0, 1, 0] });
console.log(JSON.stringify({
  cases,
  validYUp,
  defaultCamera
}));
"""
        )

        for case in result["cases"]:
            with self.subTest(case=case["name"]):
                self.assertTrue(case["finite"])
                for value in case["norms"]:
                    self.assertAlmostEqual(value, 1.0, places=8)
                for value in case["dots"]:
                    self.assertAlmostEqual(value, 0.0, places=8)
        self.assertEqual(result["validYUp"]["right"], [1, 0, 0])
        self.assertEqual(result["validYUp"]["up"], [0, 1, 0])
        self.assertEqual(result["defaultCamera"]["pos"], [0, 0, 1])
        self.assertEqual(result["defaultCamera"]["fwd"], [0, 0, -1])


class AxisClippingContractTests(unittest.TestCase):
    @staticmethod
    def _node_prelude():
        return r"""
globalThis.window = {};
const THREE = require('./three.js');
globalThis.window.THREE = THREE;
const state = {
  viewerBackend: 'webgl',
  viewerMode: '3d',
  clipPlanes3d: {
    X: { enabled: false, position: 0.5, invert: false },
    Y: { enabled: false, position: 0.5, invert: false },
    Z: { enabled: false, position: 0.5, invert: false }
  },
  meshes: new Map(),
  sliceCutaway: false,
  sliceAxis: 'X',
  sliceIndex: 7,
  sliceLast: { axis: 'X', index: 7, marker: '2d-cache' },
  sliceOverlay: false,
  model: { voxel_size_nm: 1000 },
  previewRev: 11
};
let renderer = { localClippingEnabled: false };
let meshGroup = new THREE.Group();
let meshCenterOffset = new THREE.Vector3(0, 0, 0);
let elementPointsGroup = null;
let activeClippingPlanes = [];
let activeAxisClippingBounds = null;
let activeAxisClippingMeta = {};
let cutawayPlaneCount = 0;
let cutawayCapsGroup = null;
let cutawayCapMesh1 = null;
let cutawayCapMesh2 = null;
let cutawayCapMat1 = null;
let cutawayCapMat2 = null;
let cutawayCapTex1 = null;
let cutawayCapTex2 = null;
let axisClippingCapMode = 'none';
let axisClippingCapKey = '';
const elements = {};
const events = [];
function $(id) { return elements[id] || null; }
function requestWebglRender() { events.push('render'); }
function scheduleUiStatePersist(delay) { events.push(`persist:${delay}`); }
function _clearCutawayCaps() { events.push('clear-caps'); }
function _ensureSingleAxisClippingCap(axis) { events.push(`single-cap:${axis}`); return true; }
function _normalizeViewerFallbackReason(value) { return String(value || 'WebGL unavailable'); }
function axisMax() { return 9; }
function _sanitizeSliceAxis(axis) { return ['X', 'Y', 'Z'].includes(String(axis).toUpperCase()) ? String(axis).toUpperCase() : 'Z'; }
function clampInt(value, lo, hi) { return Math.max(lo, Math.min(hi, parseInt(value, 10) || 0)); }
"""

    def test_three_axes_use_visible_world_bounds_clamp_and_invert(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
const visibleMaterial = new THREE.MeshBasicMaterial();
const visible = new THREE.Mesh(new THREE.BoxGeometry(8, 20, 6), visibleMaterial);
visible.position.set(6, 20, 6);
meshGroup.add(visible);
const hidden = new THREE.Mesh(new THREE.BoxGeometry(100, 100, 100), new THREE.MeshBasicMaterial());
hidden.position.set(1000, 1000, 1000);
hidden.visible = false;
meshGroup.add(hidden);
state.clipPlanes3d.X = { enabled: true, position: -0.5, invert: false };
state.clipPlanes3d.Y = { enabled: true, position: 0.25, invert: true };
state.clipPlanes3d.Z = { enabled: true, position: 1.5, invert: false };
const ok = updateAxisClippingPlanes(false);
console.log(JSON.stringify({
  ok,
  revision: THREE.REVISION,
  bounds: {
    min: activeAxisClippingBounds.min.toArray(),
    max: activeAxisClippingBounds.max.toArray()
  },
  planes: activeClippingPlanes.map((plane) => ({
    normal: plane.normal.toArray(),
    constant: plane.constant
  })),
  materialPlaneCount: visibleMaterial.clippingPlanes.length,
  rendererEnabled: renderer.localClippingEnabled,
  positions: {
    X: state.clipPlanes3d.X.position,
    Y: state.clipPlanes3d.Y.position,
    Z: state.clipPlanes3d.Z.position
  }
}));
"""
        )

        self.assertEqual(result["revision"], "145")
        self.assertTrue(result["ok"])
        self.assertEqual(result["bounds"], {"min": [2, 10, 3], "max": [10, 30, 9]})
        self.assertEqual(result["planes"][0], {"normal": [1, 0, 0], "constant": -2})
        self.assertEqual(result["planes"][1], {"normal": [0, -1, 0], "constant": 15})
        self.assertEqual(result["planes"][2], {"normal": [0, 0, 1], "constant": -9})
        self.assertEqual(result["materialPlaneCount"], 3)
        self.assertTrue(result["rendererEnabled"])
        self.assertEqual(result["positions"], {"X": 0, "Y": 0.25, "Z": 1})

    def test_plane_transitions_deduplicate_materials_and_refresh_new_meshes(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
const shared = new THREE.MeshBasicMaterial();
const second = new THREE.MeshBasicMaterial();
const first = new THREE.Mesh(new THREE.BoxGeometry(4, 4, 4), [shared, second, shared]);
meshGroup.add(first);
state.clipPlanes3d.X.enabled = true;
updateAxisClippingPlanes(false);
const one = {
  renderer: renderer.localClippingEnabled,
  shared: shared.clippingPlanes.length,
  second: second.clippingPlanes.length,
  sameArray: shared.clippingPlanes === second.clippingPlanes
};
state.clipPlanes3d.Y.enabled = true;
updateAxisClippingPlanes(false);
const two = [shared.clippingPlanes.length, second.clippingPlanes.length];
const newcomerMaterial = new THREE.MeshBasicMaterial();
const newcomer = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), newcomerMaterial);
newcomer.position.set(3, 0, 0);
meshGroup.add(newcomer);
applyAxisClippingAfterMeshRefresh(false);
const refreshed = newcomerMaterial.clippingPlanes.length;
state.clipPlanes3d.X.enabled = false;
state.clipPlanes3d.Y.enabled = false;
updateAxisClippingPlanes(false);
console.log(JSON.stringify({
  one,
  two,
  refreshed,
  zero: {
    renderer: renderer.localClippingEnabled,
    shared: shared.clippingPlanes,
    second: second.clippingPlanes,
    newcomer: newcomerMaterial.clippingPlanes,
    activeCount: activeClippingPlanes.length
  }
}));
"""
        )

        self.assertEqual(result["one"], {"renderer": True, "shared": 1, "second": 1, "sameArray": True})
        self.assertEqual(result["two"], [2, 2])
        self.assertEqual(result["refreshed"], 2)
        self.assertEqual(
            result["zero"],
            {"renderer": False, "shared": None, "second": None, "newcomer": None, "activeCount": 0},
        )

    def test_controls_dispatch_only_the_target_axis_and_restore_after_remote(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
function makeElement(value = '') {
  return {
    value,
    checked: false,
    disabled: false,
    title: '',
    textContent: '',
    dataset: {},
    listeners: {},
    addEventListener(kind, fn) {
      if (!this.listeners[kind]) this.listeners[kind] = [];
      this.listeners[kind].push(fn);
    },
    setAttribute(key, value2) { this[key] = value2; }
  };
}
for (const axis of ['x', 'y', 'z']) {
  elements[`clip-${axis}-enabled`] = makeElement();
  elements[`clip-${axis}-position`] = makeElement('0.5');
  elements[`clip-${axis}-value`] = makeElement('0.5');
  elements[`clip-${axis}-invert`] = makeElement();
}
elements['axis-clipping-status'] = makeElement();
elements['slice-cutaway-toggle'] = makeElement();
elements['slice-cutaway-toggle-wrap'] = makeElement();
bindAxisClippingControls();
bindAxisClippingControls();
elements['clip-y-position'].value = '0.8';
elements['clip-y-position'].listeners.input[0]();
elements['clip-z-invert'].checked = true;
elements['clip-z-invert'].listeners.change[0]();
elements['clip-x-enabled'].checked = true;
elements['clip-x-enabled'].listeners.change[0]();
const afterEvents = JSON.parse(JSON.stringify(state.clipPlanes3d));
state.viewerBackend = 'remote';
state.viewerFallbackReason = 'GPU unavailable';
syncAxisClippingControlsUI();
const remoteDisabled = ['x', 'y', 'z'].every((axis) =>
  ['enabled', 'position', 'value', 'invert'].every((suffix) => elements[`clip-${axis}-${suffix}`].disabled)
);
const preservedRemoteState = JSON.parse(JSON.stringify(state.clipPlanes3d));
state.viewerBackend = 'webgl';
syncAxisClippingControlsUI();
const restored = ['x', 'y', 'z'].every((axis) =>
  ['enabled', 'position', 'value', 'invert'].every((suffix) => !elements[`clip-${axis}-${suffix}`].disabled)
);
console.log(JSON.stringify({
  afterEvents,
  remoteDisabled,
  preservedRemoteState,
  restored,
  listenerCounts: Object.fromEntries(Object.entries(elements)
    .filter(([id]) => id.startsWith('clip-'))
    .map(([id, el]) => [id, Object.values(el.listeners).reduce((n, list) => n + list.length, 0)])),
  status: elements['axis-clipping-status'].textContent
}));
"""
        )

        self.assertEqual(result["afterEvents"]["X"], {"enabled": True, "position": 0.5, "invert": False})
        self.assertEqual(result["afterEvents"]["Y"], {"enabled": False, "position": 0.8, "invert": False})
        self.assertEqual(result["afterEvents"]["Z"], {"enabled": False, "position": 0.5, "invert": True})
        self.assertTrue(result["remoteDisabled"])
        self.assertEqual(result["preservedRemoteState"], result["afterEvents"])
        self.assertTrue(result["restored"])
        self.assertTrue(all(count == 1 for count in result["listenerCounts"].values()))

    def test_single_axis_keeps_cap_but_multi_axis_clears_resources(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
meshGroup.add(new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial()));
state.clipPlanes3d.Z.enabled = true;
updateAxisClippingPlanes(false);
const singleMode = axisClippingCapMode;
state.clipPlanes3d.X.enabled = true;
updateAxisClippingPlanes(false);
const multiMode = axisClippingCapMode;
const multiEvents = events.slice();
state.clipPlanes3d.X.enabled = false;
state.clipPlanes3d.Z.enabled = false;
updateAxisClippingPlanes(false);
console.log(JSON.stringify({ singleMode, multiMode, multiEvents, finalMode: axisClippingCapMode, events }));
"""
        )

        self.assertEqual(result["singleMode"], "single")
        self.assertEqual(result["multiMode"], "multi-disabled")
        self.assertIn("single-cap:Z", result["multiEvents"])
        self.assertIn("clear-caps", result["multiEvents"])
        self.assertEqual(result["finalMode"], "none")

    def test_runtime_cleanup_removes_planes_caps_and_material_references(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
const material = new THREE.MeshBasicMaterial();
meshGroup.add(new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), material));
state.clipPlanes3d.X.enabled = true;
updateAxisClippingPlanes(false);
const before = { count: activeClippingPlanes.length, renderer: renderer.localClippingEnabled };
resetAxisClippingRuntime();
console.log(JSON.stringify({
  before,
  after: {
    count: activeClippingPlanes.length,
    renderer: renderer.localClippingEnabled,
    materialPlanes: material.clippingPlanes,
    bounds: activeAxisClippingBounds,
    metaKeys: Object.keys(activeAxisClippingMeta),
    capMode: axisClippingCapMode
  },
  stateStillSerializable: state.clipPlanes3d
}));
"""
        )

        self.assertEqual(result["before"], {"count": 1, "renderer": True})
        self.assertEqual(
            result["after"],
            {"count": 0, "renderer": False, "materialPlanes": None, "bounds": None, "metaKeys": [], "capMode": "none"},
        )
        self.assertEqual(result["stateStillSerializable"]["X"]["enabled"], True)

    def test_cap_index_uses_world_plane_position_without_mutating_slice_ui(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
meshCenterOffset.set(10, 20, 50);
axisMax = () => 99;
const partialDomainMesh = new THREE.Mesh(
  new THREE.BoxGeometry(2, 2, 20),
  new THREE.MeshBasicMaterial()
);
partialDomainMesh.position.z = 30;
meshGroup.add(partialDomainMesh);
meshCenterOffset.set(0, 0, 0);
state.clipPlanes3d.Z = { enabled: true, position: 0.5, invert: false };
updateAxisClippingPlanes(false);
const partialDomain = {
  min: activeAxisClippingBounds.min.z,
  max: activeAxisClippingBounds.max.z,
  point: activeAxisClippingMeta.Z.point,
  index: _axisClippingSliceIndex('Z')
};
state.clipPlanes3d.Z.enabled = false;
meshGroup.remove(partialDomainMesh);
meshCenterOffset.set(10, 20, 50);
activeAxisClippingMeta = {
  X: { point: 20, invert: false },
  Y: { point: 10, invert: false },
  Z: { point: -20, invert: false }
};
const indices = {
  X: _axisClippingSliceIndex('X'),
  Y: _axisClippingSliceIndex('Y'),
  Z: _axisClippingSliceIndex('Z')
};
const normal = _axisClippingCapNormal('Z').toArray();
activeAxisClippingMeta.Z.invert = true;
state.clipPlanes3d.Z.invert = true;
const inverted = _axisClippingSliceIndex('Z');
const invertedNormal = _axisClippingCapNormal('Z').toArray();
activeAxisClippingMeta.X.point = -1000;
const low = _axisClippingSliceIndex('X');
activeAxisClippingMeta.X.point = 1000;
const high = _axisClippingSliceIndex('X');
const before = { axis: state.sliceAxis, index: state.sliceIndex, last: state.sliceLast };
_setAxisClippingState('Z', { enabled: true, position: 0.73, invert: true }, 0);
const after = { axis: state.sliceAxis, index: state.sliceIndex, last: state.sliceLast };
console.log(JSON.stringify({ partialDomain, indices, normal, inverted, invertedNormal, low, high, before, after }));
"""
        )

        self.assertEqual(result["partialDomain"], {"min": 20, "max": 40, "point": 30, "index": 30})
        self.assertEqual(result["indices"], {"X": 30, "Y": 30, "Z": 30})
        self.assertEqual(result["normal"], [0, 0, 1])
        self.assertEqual(result["inverted"], 30)
        self.assertEqual(result["invertedNormal"], [0, 0, -1])
        self.assertEqual(result["low"], 0)
        self.assertEqual(result["high"], 99)
        self.assertEqual(result["after"], result["before"])

    def test_dedicated_cap_fetch_works_without_slice_overlay_and_rejects_stale_response(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
class FakeAbortController {
  constructor() { this.signal = { aborted: false }; }
  abort() { this.signal.aborted = true; }
}
window.AbortController = FakeAbortController;
axisMax = () => 99;
const pending = [];
function apiGet(path, timeout, extra) {
  return new Promise((resolve) => pending.push({ path, timeout, signal: extra && extra.signal, resolve }));
}
function _b64ToBytes() { return new Uint8Array([1, 0, 2, 0, 3, 0, 4, 0]); }
const rendered = [];
function _axisClippingRenderCapSlice(slice) { rendered.push({ axis: slice.axis, index: slice.index, data: Array.from(slice.data) }); return true; }

(async () => {
  state.clipPlanes3d.Z.enabled = true;
  activeAxisClippingMeta = { Z: { point: 30, position: 0.3, invert: false } };
  axisClippingCapMode = 'single';
  const first = _requestAxisClippingCapSlice('Z');
  activeAxisClippingMeta.Z.point = 40;
  const second = _requestAxisClippingCapSlice('Z');
  const firstWasAborted = pending[0].signal.aborted;
  pending[0].resolve({ ok: true, result: { axis: 'Z', index: 30, shape: [2, 2], data_b64: 'ignored' } });
  await first;
  const renderedAfterStale = rendered.slice();
  pending[1].resolve({ ok: true, result: { axis: 'Z', index: 40, shape: [2, 2], data_b64: 'ignored' } });
  await second;
  const requestsBeforeInvert = pending.length;
  state.clipPlanes3d.Z.invert = true;
  activeAxisClippingMeta.Z.invert = true;
  const inverted = await _requestAxisClippingCapSlice('Z');
  const requestsAfterInvert = pending.length;
  state.previewRev = 12;
  const revised = _requestAxisClippingCapSlice('Z');
  const requestsAfterRevision = pending.length;
  pending[2].resolve({ ok: true, result: { axis: 'Z', index: 40, shape: [2, 2], data_b64: 'ignored' } });
  await revised;
  console.log(JSON.stringify({
    paths: pending.map((item) => item.path),
    firstWasAborted,
    renderedAfterStale,
    rendered,
    requestsBeforeInvert,
    requestsAfterInvert,
    requestsAfterRevision,
    inverted,
    sliceOverlay: state.sliceOverlay,
    sliceAxis: state.sliceAxis,
    sliceIndex: state.sliceIndex,
    sliceLast: state.sliceLast,
    cacheKey: axisClippingCapSliceKey,
    clearedOldCaps: events.filter((event) => event === 'clear-caps').length
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        )

        self.assertIn("axis=Z", result["paths"][0])
        self.assertIn("index=30", result["paths"][0])
        self.assertIn("index=40", result["paths"][1])
        self.assertTrue(result["firstWasAborted"])
        self.assertEqual(result["renderedAfterStale"], [])
        self.assertEqual(result["rendered"][-1]["index"], 40)
        self.assertEqual(result["requestsAfterInvert"], result["requestsBeforeInvert"])
        self.assertEqual(result["requestsAfterRevision"], result["requestsAfterInvert"] + 1)
        self.assertTrue(result["inverted"])
        self.assertFalse(result["sliceOverlay"])
        self.assertEqual(result["sliceAxis"], "X")
        self.assertEqual(result["sliceIndex"], 7)
        self.assertEqual(result["sliceLast"]["marker"], "2d-cache")
        self.assertIn("rev=12", result["cacheKey"])
        self.assertEqual(result["clearedOldCaps"], 3)

    def test_multi_axis_disable_and_fallback_abort_and_clear_dedicated_cap_cache(self):
        result = _run_node(
            self._node_prelude()
            + _axis_clipping_contract_source()
            + r"""
class FakeAbortController {
  constructor() { this.signal = { aborted: false }; }
  abort() { this.signal.aborted = true; }
}
window.AbortController = FakeAbortController;
axisMax = () => 99;
const pending = [];
function apiGet(path, timeout, extra) {
  return new Promise((resolve) => pending.push({ path, signal: extra && extra.signal, resolve }));
}
function _b64ToBytes() { return new Uint8Array([1, 0]); }
const rendered = [];
function _axisClippingRenderCapSlice(slice) { rendered.push(slice.index); return true; }

(async () => {
  state.clipPlanes3d.X.enabled = true;
  activeAxisClippingMeta = { X: { point: 2, position: 0.2, invert: false } };
  axisClippingCapMode = 'single';
  const first = _requestAxisClippingCapSlice('X');
  const firstSignal = pending[0].signal;
  state.clipPlanes3d.Y.enabled = true;
  _updateAxisClippingCapPolicy(['X', 'Y']);
  const multiCleared = { aborted: firstSignal.aborted, slice: axisClippingCapSlice, key: axisClippingCapSliceKey };
  pending[0].resolve({ ok: true, result: { axis: 'X', index: 2, shape: [1, 1], data_b64: 'ignored' } });
  await first;

  state.clipPlanes3d.Y.enabled = false;
  activeAxisClippingMeta = { X: { point: 3, position: 0.3, invert: false } };
  axisClippingCapMode = 'single';
  const second = _requestAxisClippingCapSlice('X');
  const secondSignal = pending[1].signal;
  state.viewerBackend = 'remote';
  resetAxisClippingRuntime();
  const fallbackCleared = { aborted: secondSignal.aborted, slice: axisClippingCapSlice, key: axisClippingCapSliceKey };
  pending[1].resolve({ ok: false, error: 'late controlled failure' });
  await second;
  console.log(JSON.stringify({ multiCleared, fallbackCleared, rendered, requestCount: pending.length }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        )

        self.assertEqual(result["multiCleared"], {"aborted": True, "slice": None, "key": ""})
        self.assertEqual(result["fallbackCleared"], {"aborted": True, "slice": None, "key": ""})
        self.assertEqual(result["rendered"], [])
        self.assertEqual(result["requestCount"], 2)


if __name__ == "__main__":
    unittest.main()
