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
const THREE = window.THREE = {{
  WebGLRenderer: function () {{
    events.push(`renderer:backend=${{state.viewerBackend}}`);
    this.domElement = actualCanvas;
    this.capabilities = {{ isWebGL2: true }};
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
  PerspectiveCamera: function () {{ this.up = {{ set() {{}} }}; this.position = {{ set() {{}} }}; this.updateProjectionMatrix = function () {{}}; }},
  Group: function () {{}},
  HemisphereLight: Node,
  DirectionalLight: Node,
  AmbientLight: Node,
  ACESFilmicToneMapping: 1,
  sRGBEncoding: 2,
  SRGBColorSpace: 3
}};
let renderer = null, scene = null, camera = null, meshGroup = null, loader = null, controls = null;
let _viewerResizeHandler = null;
function $(id) {{ if (id !== 'viewer-canvas') throw new Error(`unexpected ${{id}}`); return actualCanvas; }}
function webglCapability() {{ events.push('capability'); return {{ ok: true, version: 1, reason: '' }}; }}
function getClientPerf() {{ return {{ onDemand: false, antialias: true, dprCap: 1, damping: false }}; }}
function getRenderQuality() {{ return 'high'; }}
function _autoFallbackEnabled() {{ return true; }}
function initRemoteViewer(reason) {{ throw new Error(`unexpected remote fallback: ${{reason}}`); }}
function showNotification() {{}}
function requestWebglRender() {{}}
function updateRuler3d() {{}}
function applySliceViewOffset3d() {{}}
function _updateViewerBackendUI() {{ events.push('backend-ui'); }}
{init_viewer}
initViewer();
console.log(JSON.stringify({{ events, state }}));
"""
        )

        self.assertIn("renderer:backend=pending", result["events"])
        self.assertEqual(result["state"]["viewerBackend"], "webgl")
        self.assertEqual(result["state"]["viewerWebglVersion"], 2)
        self.assertEqual(result["state"]["viewerFallbackReason"], "")
        self.assertTrue(result["state"]["viewerReady"])

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


if __name__ == "__main__":
    unittest.main()
