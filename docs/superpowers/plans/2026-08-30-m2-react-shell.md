# M2 React Shell 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（- [ ]）语法来跟踪进度。

**目标：** 在 frontend/ 建立高密度 React Shell，通过冻结的 M2 Compatibility API 操作现有 Session/Worker，并提供真实可拖拽的最小 Three.js Viewer。

**架构：** Vite 开发服务器代理 /api；生产构建由现有 Python WebUI 在 /studio/ 同源提供，旧根页面保持不变。React Context + reducer 管理 UI 和服务端状态副本，所有工艺仍由现有 ProcessStep/ProcessModel 执行；Three.js 只加载 manifest/STL 并负责显示。

**技术栈：** React 19.2、TypeScript 7、Vite 8、Three.js r185、Vitest 4、React Testing Library、Python unittest、现有 WebUI HTTP/Worker。

---

## 文件结构

### 新建

- frontend/package.json：Node 依赖与验证脚本。
- frontend/package-lock.json：锁定可复现依赖。
- frontend/tsconfig.json：严格 TypeScript 配置。
- frontend/vite.config.ts：/studio/ base、API proxy、Vitest。
- frontend/index.html：React 挂载入口。
- frontend/src/main.tsx：浏览器入口。
- frontend/src/App.tsx：应用编排与高密度 Shell。
- frontend/src/styles.css：三栏、Timeline、状态和窄屏折叠样式。
- frontend/src/test/setup.ts：jest-dom 与测试清理。
- frontend/src/api/types.ts：客户端实际消费的领域类型。
- frontend/src/api/schemas.ts：unknown 到领域类型的 runtime guard。
- frontend/src/api/client.ts：JSON/binary 请求、Cookie、取消和错误标准化。
- frontend/src/state/appReducer.ts：纯 reducer 和初始状态。
- frontend/src/state/AppStateContext.tsx：状态 provider 和异步 actions。
- frontend/src/components/Toolbar.tsx：运行操作和全局状态。
- frontend/src/components/ProcessFlowPane.tsx：步骤选择与状态。
- frontend/src/components/ParameterPanel.tsx：通用参数表单和 draft。
- frontend/src/components/TimelineBar.tsx：快照导航。
- frontend/src/components/ErrorNotice.tsx：结构化错误。
- frontend/src/components/StatusBadge.tsx：Ready/Dirty/Running/Done/Error。
- frontend/src/viewer/meshLoader.ts：manifest/STL 下载与 stale guard。
- frontend/src/viewer/fitCamera.ts：纯 Box3 相机适配计算。
- frontend/src/viewer/ThreeViewer.tsx：renderer、OrbitControls 和资源生命周期。
- frontend/src/**/*.test.ts(x)：对应单元和组件测试。

### 修改

- tcad_simulator.py：增加安全的 /studio/ 静态入口，不改旧 WebUI/API 分发。
- tests/test_webui_cad_shell.py：增加 React 静态入口契约测试。
- .gitignore：忽略 frontend/node_modules/、frontend/dist/ 和 .superpowers/。
- README.md：记录 React Shell 开发、构建和访问方式。
- docs/ARCHITECTURE_TARGET.md：记录 M2 实际组件与最小 Viewer 边界。
- docs/ROADMAP_PROCESS_CAD.md：更新 M1 合并状态及 M2/M3 切片。

## 任务 1：建立可验证的 React/Vite 骨架

**文件：**

- 创建：frontend/package.json
- 创建：frontend/tsconfig.json
- 创建：frontend/vite.config.ts
- 创建：frontend/index.html
- 创建：frontend/src/test/setup.ts
- 创建：frontend/src/App.test.tsx
- 创建：frontend/src/App.tsx
- 创建：frontend/src/main.tsx
- 创建：frontend/src/styles.css
- 修改：.gitignore

- [ ] **步骤 1：创建构建配置和失败的 Shell 测试**

先创建 package.json：

~~~json
{
  "name": "tcad-studio-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "engines": {"node": ">=20.19.0"},
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "typecheck": "tsc --noEmit",
    "test": "vitest"
  },
  "dependencies": {
    "react": "19.2.8",
    "react-dom": "19.2.8",
    "three": "0.185.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "7.0.1",
    "@testing-library/react": "16.3.3",
    "@types/node": "26.4.0",
    "@types/react": "19.2.18",
    "@types/react-dom": "19.2.5",
    "@types/three": "0.185.4",
    "@vitejs/plugin-react": "6.1.1",
    "jsdom": "30.0.1",
    "typescript": "7.0.2",
    "vite": "8.2.2",
    "vitest": "4.1.11"
  }
}
~~~

vite.config.ts：

~~~ts
import react from "@vitejs/plugin-react";
import {defineConfig} from "vitest/config";

export default defineConfig({
  base: "/studio/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.TCAD_API_PROXY ?? "http://127.0.0.1:8765",
        changeOrigin: false
      }
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true
  }
});
~~~

App.test.tsx 先引用尚不存在的 App：

~~~tsx
import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {App} from "./App";

describe("App", () => {
  it("显示 M2 启动状态", () => {
    render(<App />);
    expect(screen.getByRole("heading", {name: "TCAD Studio"})).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("正在连接");
  });
});
~~~

- [ ] **步骤 2：安装依赖并验证红灯**

运行：

~~~bash
cd frontend
npm install
npm test -- --run src/App.test.tsx
~~~

预期：FAIL，报错无法解析 ./App。

- [ ] **步骤 3：实现最小 App 和入口**

App.tsx：

~~~tsx
export function App() {
  return (
    <main className="app-shell">
      <h1>TCAD Studio</h1>
      <div role="status" aria-live="polite">正在连接现有 Process CAD Session…</div>
    </main>
  );
}
~~~

main.tsx：

~~~tsx
import {StrictMode} from "react";
import {createRoot} from "react-dom/client";
import {App} from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("缺少 #root 挂载节点");
createRoot(root).render(<StrictMode><App /></StrictMode>);
~~~

在 .gitignore 增加：

~~~gitignore
.superpowers/
frontend/node_modules/
frontend/dist/
frontend/coverage/
~~~

- [ ] **步骤 4：验证骨架**

运行：

~~~bash
cd frontend
npm test -- --run
npm run typecheck
npm run build
~~~

预期：1 个测试通过，typecheck 和 build exit 0；dist 未出现在 git status。

- [ ] **步骤 5：提交**

~~~bash
git add .gitignore frontend/package.json frontend/package-lock.json frontend/tsconfig.json \
  frontend/vite.config.ts frontend/index.html frontend/src
git commit -m "chore(M2): 建立 React 与 Vite 测试骨架"
git push backup codex/m2-react-shell
~~~

## 任务 2：增加安全的 /studio/ 同源静态入口

**文件：**

- 修改：tests/test_webui_cad_shell.py
- 修改：tcad_simulator.py

- [ ] **步骤 1：编写失败的 Python 行为测试**

在 WebUI 测试文件新增 ReactStudioStaticTests。测试使用 TemporaryDirectory 创建独立 dist，
避免依赖本地 npm build：

~~~python
class ReactStudioStaticTests(unittest.TestCase):
    def _request(self, base, method, path, headers=None):
        import http.client
        from urllib.parse import urlparse

        parsed = urlparse(base)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=30)
        conn.request(method, path, headers=dict(headers or {}))
        response = conn.getresponse()
        body = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        conn.close()
        return status, response_headers, body

    def _manager(self, temp_dir, dist_dir):
        return tcad.WebUIServerManager(
            host="127.0.0.1",
            port=0,
            storage_root=Path(temp_dir) / "storage",
            studio_dist_dir=Path(dist_dir),
        )

    def test_studio_serves_index_assets_and_keeps_legacy_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist = Path(temp_dir) / "dist"
            (dist / "assets").mkdir(parents=True)
            (dist / "index.html").write_text("<main>React Shell</main>", encoding="utf-8")
            (dist / "assets" / "app.js").write_text("export {};", encoding="utf-8")
            manager = self._manager(temp_dir, dist)
            manager.start()
            try:
                status, headers, body = self._request(manager.url, "GET", "/studio")
                self.assertEqual(status, 302)
                self.assertEqual(headers["location"], "/studio/")
                status, headers, body = self._request(manager.url, "GET", "/studio/")
                self.assertEqual(status, 200)
                self.assertIn(b"React Shell", body)
                status, headers, body = self._request(manager.url, "GET", "/studio/assets/app.js")
                self.assertEqual(status, 200)
                self.assertIn("javascript", headers["content-type"])
                status, _headers, body = self._request(manager.url, "GET", "/")
                self.assertEqual(status, 200)
                self.assertIn(b"TCAD", body)
            finally:
                manager.stop()
~~~

另外加入 3 个独立测试：

- 缺少 dist 时 /studio/ 返回 503 且包含 npm run build；
- Accept: text/html 的 /studio/recipe/1 回退 index.html；
- /studio/../、百分号编码 traversal 和指向 dist 外的 symlink 返回 403。

- [ ] **步骤 2：验证红灯**

运行：

~~~bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m2-static-red \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_webui_cad_shell.ReactStudioStaticTests
~~~

预期：ERROR，WebUIServerManager 不接受 studio_dist_dir。

- [ ] **步骤 3：实现安全静态读取**

给 WebUIServerManager.__init__ 增加可选参数：

~~~python
studio_dist_dir: Optional[Path] = None,
~~~

并保存规范路径：

~~~python
self.studio_dist_dir = (
    Path(studio_dist_dir)
    if studio_dist_dir is not None
    else (_webui_launch_root() / "frontend" / "dist")
)
~~~

在 _WebUIRequestHandler 增加 _serve_studio(path)：

~~~python
def _serve_studio(self, path: str) -> None:
    dist = self.server.manager.studio_dist_dir.resolve()
    index = dist / "index.html"
    if not index.is_file():
        message = (
            "<h1>React Shell 尚未构建</h1>"
            "<p>运行 cd frontend &amp;&amp; npm install &amp;&amp; npm run build</p>"
        ).encode("utf-8")
        self._send_bytes(message, "text/html; charset=utf-8", status=503)
        return
    rel = urllib.parse.unquote(path[len("/studio/"):])
    rel_path = Path(rel or "index.html")
    if rel_path.is_absolute() or ".." in rel_path.parts:
        self._send_json({"ok": False, "error": "Forbidden"}, status=403)
        return
    candidate = (dist / rel_path).resolve()
    if not candidate.is_relative_to(dist):
        self._send_json({"ok": False, "error": "Forbidden"}, status=403)
        return
    if not candidate.is_file():
        accepts_html = "text/html" in str(self.headers.get("Accept", ""))
        if not accepts_html:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        candidate = index
    data = candidate.read_bytes()
    content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
        content_type += "; charset=utf-8"
    self._send_bytes(data, content_type, extra_headers={"Cache-Control": "no-store"})
~~~

在 do_GET 的 /static 分支之前处理 /studio 和 /studio/。重定向必须手写 302、Location 和
Content-Length: 0，不创建 Session。

- [ ] **步骤 4：验证静态入口与旧 API**

运行：

~~~bash
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m2-static-green \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_webui_cad_shell.ReactStudioStaticTests \
  tests.test_webui_cad_shell.M2ApiContractTests \
  tests.test_webui_cad_shell.M2ApiDocConsistencyTests
~~~

预期：全部通过。

- [ ] **步骤 5：提交**

~~~bash
git add tcad_simulator.py tests/test_webui_cad_shell.py
git commit -m "feat(M2): 提供 React Shell 同源静态入口"
git push backup codex/m2-react-shell
~~~

## 任务 3：冻结 TypeScript API 边界

**文件：**

- 创建：frontend/src/api/types.ts
- 创建：frontend/src/api/schemas.ts
- 创建：frontend/src/api/client.ts
- 创建：frontend/src/api/schemas.test.ts
- 创建：frontend/src/api/client.test.ts

- [ ] **步骤 1：先写 guard 和错误契约测试**

schemas.test.ts 使用真实最小 payload：

~~~ts
import {describe, expect, it} from "vitest";
import {parseInitEnvelope} from "./schemas";

const valid = {
  ok: true,
  result: {
    recipe: [{
      name: "Initialize Wafer",
      instance_name: "Substrate",
      enabled: true,
      params: {material: "Silicon"},
      parameter_specs: [{key: "material", label: "Material", type: "choice"}],
      runtime_status: "ready"
    }],
    model: {grid_shape: [64, 64, 96], voxel_size_nm: 10},
    recipe_factories: ["Initialize Wafer"],
    materials: []
  }
};

describe("parseInitEnvelope", () => {
  it("接受 additive 字段并保留客户端必需字段", () => {
    const parsed = parseInitEnvelope({...valid, server_added: 1});
    expect(parsed.recipe[0].instanceName).toBe("Substrate");
    expect(parsed.recipe).toHaveLength(1);
  });

  it("缺少 recipe 时给出 JSON path", () => {
    expect(() => parseInitEnvelope({ok: true, result: {model: {}}}))
      .toThrow("result.recipe");
  });
});
~~~

client.test.ts 使用 vi.stubGlobal("fetch", vi.fn()) 覆盖：

- HTTP 200 + ok:false 仍抛 TcadApiError；
- /api/run/step 的平面结构化错误字段完整映射；
- binary 成功返回 ArrayBuffer；
- binary 失败若 content-type 为 JSON，则解析错误而不是把 JSON 当 STL；
- credentials 固定为 same-origin；
- AbortError 保持可识别，不转成普通用户错误。

- [ ] **步骤 2：验证红灯**

运行：

~~~bash
cd frontend
npm test -- --run src/api
~~~

预期：FAIL，types/schemas/client 模块不存在。

- [ ] **步骤 3：实现最小领域类型和 guard**

types.ts 的核心类型：

~~~ts
export type RuntimeStatus = "ready" | "dirty" | "running" | "done" | "error";

export interface ParameterSpecView {
  key: string;
  label: string;
  type: string;
  defaultValue?: unknown;
  minimum?: number;
  maximum?: number;
  units?: string;
  choices?: readonly unknown[];
}

export interface StepView {
  index: number;
  name: string;
  instanceName: string;
  enabled: boolean;
  params: Record<string, unknown>;
  parameterSpecs: ParameterSpecView[];
  runtimeStatus: RuntimeStatus;
}

export interface InitView {
  recipe: StepView[];
  factories: string[];
  materials: unknown[];
}
~~~

schemas.ts 用 requireRecord、requireArray、requireString、optionalFiniteNumber 组合解析。所有未知
字段忽略；runtime_status 非法时回退 ready，但 recipe/model 等必需容器缺失时抛
ApiContractError(path)。不得从 /api/init 的 model summary 臆造 revision；几何 revision 只从
/api/preview/manifest 的 rev 读取。

- [ ] **步骤 4：实现 API client**

client.ts 提供：

~~~ts
export class TcadApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly parameterPath?: string,
    readonly suggestion?: string,
    readonly rolledBack?: boolean,
    readonly causeValue?: unknown
  ) {
    super(message);
    this.name = "TcadApiError";
  }
}

export async function apiJson<T>(
  path: string,
  init: RequestInit,
  parse: (payload: unknown) => T
): Promise<T> {
  const response = await fetch(path, {...init, credentials: "same-origin"});
  const payload: unknown = await response.json();
  if (!response.ok || !isOkEnvelope(payload)) throw toApiError(response.status, payload);
  return parse(payload);
}

export async function apiBinary(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(path, {credentials: "same-origin", signal});
  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const payload = contentType.includes("json") ? await response.json() : {error: response.statusText};
    throw toApiError(response.status, payload);
  }
  return response.arrayBuffer();
}
~~~

POST helper 必须统一 JSON.stringify 和 Content-Type，GET 不附加无意义 body。

- [ ] **步骤 5：验证并提交**

运行：

~~~bash
cd frontend
npm test -- --run src/api
npm run typecheck
~~~

预期：全部通过。

~~~bash
git add frontend/src/api
git commit -m "feat(M2): 建立兼容 API 类型边界"
git push backup codex/m2-react-shell
~~~

## 任务 4：实现纯 reducer 和 Session actions

**文件：**

- 创建：frontend/src/state/appReducer.ts
- 创建：frontend/src/state/appReducer.test.ts
- 创建：frontend/src/state/AppStateContext.tsx
- 创建：frontend/src/state/AppStateContext.test.tsx

- [ ] **步骤 1：编写 reducer 红灯测试**

覆盖以下动作：

~~~ts
it("bootstrap 成功后选择首步并进入 ready", () => {
  const state = appReducer(initialAppState, {type: "bootstrap/succeeded", payload: initView});
  expect(state.phase).toBe("ready");
  expect(state.selectedStepIndex).toBe(0);
});

it("保存成功只接受最新 field sequence", () => {
  const editing = appReducer(readyState, {
    type: "parameter/draftChanged", index: 1, key: "dose", value: 120, sequence: 2
  });
  const stale = appReducer(editing, {
    type: "parameter/saveSucceeded", index: 1, key: "dose", sequence: 1,
    step: oldStep, statuses: ["done", "dirty"]
  });
  expect(stale.drafts["1:dose"].value).toBe(120);
});

it("mutation gate 阻止第二个运行请求", () => {
  const running = appReducer(readyState, {type: "run/started", operation: "all"});
  expect(running.phase).toBe("running");
  expect(running.activeMutation).toBe("all");
});
~~~

另外断言 bootstrap 失败、字段错误保留 draft、timeline restore、viewer revision 和结构化 step
error。

- [ ] **步骤 2：验证红灯**

运行：

~~~bash
cd frontend
npm test -- --run src/state/appReducer.test.ts
~~~

预期：FAIL，appReducer 不存在。

- [ ] **步骤 3：实现 reducer**

AppState 至少包含：

~~~ts
export interface AppState {
  phase: "booting" | "ready" | "running" | "fatal";
  recipe: StepView[];
  selectedStepIndex: number | null;
  previewGeneration: number;
  lastModelRevision: number | null;
  timeline: TimelineView | null;
  drafts: Record<string, ParameterDraft>;
  stepErrors: Record<number, TcadApiError>;
  activeMutation: "step" | "to" | "all" | "timeline" | null;
  globalError: TcadApiError | null;
}
~~~

Reducer 保持纯函数；不得在 reducer 中 fetch、创建 Three.js 对象或 setTimeout。

- [ ] **步骤 4：实现 Provider actions**

AppStateContext 暴露 bootstrap、selectStep、updateDraft、saveParameter、runStep、runTo、runAll、
loadTimeline 和 restoreTimeline。异步 action 在 dispatch 前后检查 sequence；run action 先检查
activeMutation，重复点击直接 return。bootstrap、成功的 run 和 timeline restore 递增
previewGeneration；只有 run 响应实际带 model_revision 时才更新 lastModelRevision。

- [ ] **步骤 5：验证真实调用顺序**

使用注入的 TcadApi 接口替身，不 mock reducer。断言 bootstrap 只请求一次 init；run 成功后先
更新 revision，再刷新 timeline；Provider unmount 后不 dispatch。

运行：

~~~bash
cd frontend
npm test -- --run src/state
npm run typecheck
~~~

- [ ] **步骤 6：提交**

~~~bash
git add frontend/src/state
git commit -m "feat(M2): 建立 React Session 状态机"
git push backup codex/m2-react-shell
~~~

## 任务 5：实现高密度三栏 Shell 和步骤选择

**文件：**

- 修改：frontend/src/App.tsx
- 修改：frontend/src/App.test.tsx
- 修改：frontend/src/styles.css
- 创建：frontend/src/components/Toolbar.tsx
- 创建：frontend/src/components/ProcessFlowPane.tsx
- 创建：frontend/src/components/ProcessFlowPane.test.tsx
- 创建：frontend/src/components/ParameterPanel.tsx（仅真实选中步骤摘要和加载状态）
- 创建：frontend/src/components/TimelineBar.tsx（仅 Timeline landmark 和加载状态）
- 创建：frontend/src/components/StatusBadge.tsx
- 创建：frontend/src/components/ErrorNotice.tsx
- 创建：frontend/src/viewer/ThreeViewer.tsx（仅可访问的加载/空态，不绘制假 3D）

- [ ] **步骤 1：编写布局和交互红灯测试**

~~~tsx
it("bootstrap 后同时显示三栏与 Timeline", async () => {
  render(<TestApp api={apiWithInit(initView)} />);
  expect(await screen.findByRole("region", {name: "Process Flow"})).toBeVisible();
  expect(screen.getByRole("region", {name: "Parameters"})).toBeVisible();
  expect(screen.getByRole("region", {name: "3D Viewer"})).toBeVisible();
  expect(screen.getByRole("navigation", {name: "Process Timeline"})).toBeVisible();
});

it("点击步骤只改变本地选择", async () => {
  render(<TestApp api={apiWithInit(twoSteps)} />);
  await userEvent.click(await screen.findByRole("option", {name: /Oxidation/}));
  expect(screen.getByRole("option", {name: /Oxidation/})).toHaveAttribute("aria-selected", "true");
  expect(api.post).not.toHaveBeenCalled();
});
~~~

另外断言状态文字不只靠颜色、fatal init 有 Retry、低于 1100 px 的 Parameters 折叠按钮存在
并带 aria-expanded。

- [ ] **步骤 2：验证红灯**

运行：

~~~bash
cd frontend
npm test -- --run src/App.test.tsx src/components/ProcessFlowPane.test.tsx
~~~

预期：FAIL，三栏组件不存在。

- [ ] **步骤 3：实现 Shell**

App 使用语义结构：

~~~tsx
<div className="studio-shell">
  <Toolbar />
  <div className="studio-workspace">
    <ProcessFlowPane />
    <section aria-label="Parameters" className={parameterClass}><ParameterPanel /></section>
  <section aria-label="3D Viewer" className="viewer-pane"><ThreeViewer refreshToken={previewGeneration} /></section>
  </div>
  <TimelineBar />
</div>
~~~

ProcessFlowPane 使用 role=listbox，step 使用 role=option、aria-selected 和 StatusBadge。
instanceName 为主标题，name 和参数摘要为副标题。

为保证该提交可独立 build，ParameterPanel、TimelineBar 和 ThreeViewer 在本任务建立最小壳层。
ThreeViewer 只能显示「正在加载 3D Viewer」或「当前模型为空」文字状态，不得绘制静态假 3D；
任务 6、7、8 分别在这些已有组件上接入真实行为。

CSS 使用：

~~~css
.studio-workspace {
  display: grid;
  grid-template-columns: minmax(270px, 29%) minmax(300px, 30%) minmax(440px, 1fr);
  min-height: 0;
}
@media (max-width: 1100px) {
  .studio-workspace.parameters-collapsed {
    grid-template-columns: minmax(260px, 34%) minmax(440px, 1fr);
  }
  .studio-workspace.parameters-collapsed .parameter-pane { display: none; }
}
~~~

- [ ] **步骤 4：验证并提交**

运行：

~~~bash
cd frontend
npm test -- --run src/App.test.tsx src/components
npm run typecheck
npm run build
~~~

~~~bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/styles.css \
  frontend/src/components
git commit -m "feat(M2): 实现高密度 Process CAD Shell"
git push backup codex/m2-react-shell
~~~

## 任务 6：实现 parameter_specs 通用表单

**文件：**

- 修改：frontend/src/components/ParameterPanel.tsx
- 创建：frontend/src/components/ParameterPanel.test.tsx
- 创建：frontend/src/components/parameterValidation.ts
- 创建：frontend/src/components/parameterValidation.test.ts
- 修改：frontend/src/state/AppStateContext.tsx

- [ ] **步骤 1：先写参数验证红灯**

~~~ts
it("拒绝超出 maximum 的数值", () => {
  const spec = {key: "dose", label: "Dose", type: "float", minimum: 0, maximum: 500};
  expect(validateParameter(spec, "600")).toEqual({ok: false, message: "必须小于或等于 500"});
});

it("合法整数转换为 number", () => {
  const spec = {key: "cycles", label: "Cycles", type: "int", minimum: 1};
  expect(validateParameter(spec, "12")).toEqual({ok: true, value: 12});
});
~~~

覆盖 float、int、bool、choice、string、空值和非有限数；未知类型使用 string 控件，不猜测
process-specific 语义。

- [ ] **步骤 2：编写组件红灯**

使用 vi.useFakeTimers：

~~~tsx
it("合法值停止输入 350ms 后保存，blur 立即保存", async () => {
  const api = apiWithInit(stepWithDose);
  render(<TestApp api={api} />);
  const input = await screen.findByLabelText("Dose");
  await userEvent.clear(input);
  await userEvent.type(input, "125");
  expect(api.setStep).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(349);
  expect(api.setStep).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  expect(api.setStep).toHaveBeenCalledWith(0, {dose: 125}, expect.anything());
});
~~~

另测非法输入不请求、失败保留 draft、服务端 parameter_path/suggestion 可见、切换步骤取消旧
debounce。

- [ ] **步骤 3：验证红灯**

运行：

~~~bash
cd frontend
npm test -- --run src/components/parameterValidation.test.ts \
  src/components/ParameterPanel.test.tsx
~~~

- [ ] **步骤 4：实现通用控件和保存序号**

ParameterPanel 只根据 spec.type 选择 input/select/checkbox。每个字段 key 为
selectedStepIndex + ":" + spec.key；useEffect cleanup 清除 timer。blur/Enter 调用 flush；
saveParameter 发送：

~~~ts
api.setStep({
  index: selectedStepIndex,
  params: {[spec.key]: validated.value}
});
~~~

成功必须使用响应中的 result 和 statuses；不得在客户端自行推断后续 Dirty。

- [ ] **步骤 5：验证并提交**

运行：

~~~bash
cd frontend
npm test -- --run src/components/parameterValidation.test.ts \
  src/components/ParameterPanel.test.tsx src/state
npm run typecheck
~~~

~~~bash
git add frontend/src/components/ParameterPanel.tsx \
  frontend/src/components/ParameterPanel.test.tsx \
  frontend/src/components/parameterValidation.ts \
  frontend/src/components/parameterValidation.test.ts \
  frontend/src/state/AppStateContext.tsx
git commit -m "feat(M2): 接入通用步骤参数编辑"
git push backup codex/m2-react-shell
~~~

## 任务 7：接入执行操作和 Timeline

**文件：**

- 修改：frontend/src/components/Toolbar.tsx
- 创建：frontend/src/components/Toolbar.test.tsx
- 修改：frontend/src/components/TimelineBar.tsx
- 创建：frontend/src/components/TimelineBar.test.tsx
- 修改：frontend/src/state/AppStateContext.tsx
- 修改：frontend/src/api/client.ts

- [ ] **步骤 1：编写运行 gate 红灯测试**

~~~tsx
it("Run All 进行中锁住参数和其他运行按钮", async () => {
  const pending = deferred<ApiEnvelope>();
  const api = apiWithRunAll(pending.promise);
  render(<TestApp api={api} />);
  await userEvent.click(await screen.findByRole("button", {name: "运行全部"}));
  expect(screen.getByRole("button", {name: "运行选中步骤"})).toBeDisabled();
  expect(screen.getByRole("button", {name: "运行至选中步骤"})).toBeDisabled();
  expect(screen.getByRole("region", {name: "Parameters"})).toHaveAttribute("aria-busy", "true");
  await userEvent.click(screen.getByRole("button", {name: "运行全部"}));
  expect(api.runAll).toHaveBeenCalledTimes(1);
});
~~~

另测 run/step 平面错误映射到对应步骤、rolled_back false 有醒目提示、成功后刷新 timeline。

- [ ] **步骤 2：编写 Timeline 红灯测试**

~~~tsx
it("只允许恢复有效快照", async () => {
  render(<TimelineHarness items={[
    {index: 0, state: "done", runtimeStatus: "done", snapshotValid: true},
    {index: 1, state: "dirty", runtimeStatus: "dirty", snapshotValid: false}
  ]} />);
  expect(screen.getByRole("button", {name: "恢复步骤 1"})).toBeEnabled();
  expect(screen.getByRole("button", {name: "恢复步骤 2"})).toBeDisabled();
});
~~~

Previous/Next 必须跳过无效节点；restore 失败保持当前位置；成功显示「历史快照 Step N」。

- [ ] **步骤 3：验证红灯**

运行：

~~~bash
cd frontend
npm test -- --run src/components/Toolbar.test.tsx \
  src/components/TimelineBar.test.tsx
~~~

- [ ] **步骤 4：实现运行和 Timeline actions**

Toolbar 调用 Provider 的 runStep(selected)、runTo(selected)、runAll。TimelineBar 只根据服务端
snapshotValid 计算 prev/next；restore 成功使用 result.timeline.current 和 result.model 更新
revision，不调用任何 run endpoint。

结构化错误展示必须包含：

~~~tsx
<ErrorNotice
  message={error.message}
  parameterPath={error.parameterPath}
  suggestion={error.suggestion}
  rolledBack={error.rolledBack}
/>
~~~

- [ ] **步骤 5：验证并提交**

运行：

~~~bash
cd frontend
npm test -- --run src/components src/state src/api
npm run typecheck
~~~

~~~bash
git add frontend/src/components frontend/src/state/AppStateContext.tsx frontend/src/api/client.ts
git commit -m "feat(M2): 接入工艺执行与 Timeline"
git push backup codex/m2-react-shell
~~~

## 任务 8：实现真实最小 Three.js Viewer

**文件：**

- 创建：frontend/src/viewer/fitCamera.ts
- 创建：frontend/src/viewer/fitCamera.test.ts
- 创建：frontend/src/viewer/meshLoader.ts
- 创建：frontend/src/viewer/meshLoader.test.ts
- 修改：frontend/src/viewer/ThreeViewer.tsx
- 创建：frontend/src/viewer/ThreeViewer.test.tsx
- 修改：frontend/src/App.tsx
- 修改：frontend/src/styles.css

- [ ] **步骤 1：先写 fitCamera 纯函数测试**

~~~ts
it("ISO pose 以 bounds 中心为 target 并完整容纳模型", () => {
  const bounds = new Box3(new Vector3(-5, -10, 2), new Vector3(5, 10, 8));
  const fit = calculatePerspectiveFit(bounds, 40, 16 / 9);
  expect(fit.target.toArray()).toEqual([0, 0, 5]);
  expect(fit.distance).toBeGreaterThan(20);
  expect(Number.isFinite(fit.near)).toBe(true);
  expect(fit.far).toBeGreaterThan(fit.near);
});
~~~

覆盖空 bounds、退化 bounds、非有限坐标和 1×1 容器。

- [ ] **步骤 2：编写 meshLoader 红灯测试**

注入 fetchManifest、fetchStl 和 parseStl，避免测试 Three.js 内部网络：

~~~ts
it("revision 更新取消旧材料请求并丢弃旧结果", async () => {
  const first = deferred<ArrayBuffer>();
  const loader = createMeshLoader(fakeDependencies({first}));
  const load1 = loader.load(3);
  const load2 = loader.load(4);
  first.resolve(new ArrayBuffer(8));
  await expect(load1).resolves.toMatchObject({stale: true});
  await expect(load2).resolves.toMatchObject({revision: 4, stale: false});
  expect(fakeDependencies.abortCount).toBeGreaterThan(0);
});
~~~

另测：

- 只请求 visual.visible !== false 的材料；
- 同 revision 不重复请求；
- 单材料失败返回 warnings，其他材料保留；
- manifest 的 color/opacity/metallic/roughness 映射到 material config；
- dispose 按 object identity 去重。

- [ ] **步骤 3：编写 Viewer 生命周期红灯测试**

通过 ViewerRuntimeFactory 注入窄替身：

~~~tsx
it("相机操作不产生 API 请求，unmount 释放 runtime", async () => {
  const runtime = fakeViewerRuntime();
  render(<ThreeViewer refreshToken={7} runtimeFactory={() => runtime} />);
  await screen.findByText("WebGL2");
  await userEvent.click(screen.getByRole("button", {name: "ISO 视图"}));
  await userEvent.click(screen.getByRole("button", {name: "适应窗口"}));
  expect(runtime.apiCalls).toBe(0);
  cleanup();
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
});
~~~

另测 WebGL 创建失败显示真实原因、不渲染假 3D；材料级失败可重试。

- [ ] **步骤 4：验证红灯**

运行：

~~~bash
cd frontend
npm test -- --run src/viewer
~~~

预期：FAIL，Viewer 模块不存在。

- [ ] **步骤 5：实现 meshLoader**

每次 refreshToken 变化先请求 manifest；材料 URL 必须使用 manifest 返回的真实 revision：

~~~ts
const manifest = await api.previewManifest({mode: "solid", faceLimit: 40000, signal});
const meshes = await mapWithConcurrency(
  manifest.meshes.filter((mesh) => mesh.visual?.visible !== false),
  4,
  async (mesh) => {
    const bytes = await api.previewStl({
      matId: mesh.matId,
      revision: manifest.revision,
      mode: "solid",
      signal
    });
    return {mesh, geometry: stlLoader.parse(bytes)};
  }
);
~~~

禁止把 process material color 写回 Worker；材质只存在 Three.js scene。

- [ ] **步骤 6：实现 ThreeViewer**

初始化顺序：

1. 在真实 canvas 上只创建一次 WebGLRenderer；
2. 创建 Scene、PerspectiveCamera、lights、Group、OrbitControls；
3. 注册 ResizeObserver；
4. refreshToken 变化时检查 manifest，按 manifest.rev 请求 mesh；
5. 首次加载 Fit；之后 manifest.rev 变化替换 group 但保持 camera，相同 rev 不重复下载；
6. requestAnimationFrame 仅在 controls change/resize/load 后渲染，避免空闲持续占用。

catch 必须清理已经创建的 controls、listener、renderer 和 RAF，再显示可见错误。不得在真实
canvas 上做 capability pre-probe。

- [ ] **步骤 7：验证 Viewer**

运行：

~~~bash
cd frontend
npm test -- --run src/viewer src/App.test.tsx
npm run typecheck
npm run build
~~~

再启动隔离 WebUI 和 Vite：

~~~bash
TCAD_WEBUI_STORAGE_ROOT=/tmp/tcad-m2-webui \
  TCAD_SKIP_QT=1 MPLBACKEND=Agg \
  /opt/anaconda3/bin/python3 tcad_simulator.py --webui --port 8765

cd frontend
npm run dev -- --host 127.0.0.1
~~~

浏览器确认真实 STL 可左键旋转、右键平移、滚轮缩放；点击相机按钮时 Network 面板没有新增
/api 请求。

- [ ] **步骤 8：提交**

~~~bash
git add frontend/src/viewer frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat(M2): 加载真实 Three.js 工艺网格"
git push backup codex/m2-react-shell
~~~

## 任务 9：文档、集成验证和里程碑收口

**文件：**

- 修改：README.md
- 修改：docs/ARCHITECTURE_TARGET.md
- 修改：docs/ROADMAP_PROCESS_CAD.md
- 修改：docs/superpowers/specs/2026-08-30-m2-react-shell-design.md（仅将状态改为已实现）

- [ ] **步骤 1：更新文档**

README 增加：

~~~bash
# 后端
TCAD_SKIP_QT=1 MPLBACKEND=Agg python3 tcad_simulator.py --webui --port 8765

# React 开发服务器
cd frontend
npm ci
npm run dev

# 同源构建
npm run build
# 访问 http://127.0.0.1:8765/studio/
~~~

ROADMAP 明确：

- M1 已通过 PR #1 合并到 backup/main；
- M2 已交付高密度 Shell、真实 API、Timeline 和最小 mesh load/Orbit；
- M3 继续六视图、正交、XYZ clipping、材料控制、选择和测量；
- Current Branch State 使用实现完成时的真实 SHA，不保留旧 zcode/codex M1 状态。

- [ ] **步骤 2：运行全部前端验证**

~~~bash
cd frontend
npm ci
npm test -- --run
npm run typecheck
npm run build
~~~

记录测试数量、耗时和 build 产物大小。

- [ ] **步骤 3：运行全部 Python 回归**

~~~bash
cd ..
env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m2-full \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_process_cad_foundation \
  tests.test_process_cad_primitives \
  tests.test_process_cad_demos \
  tests.test_webui_viewer_contract \
  tests.test_webui_cad_shell
~~~

预期：现有 172 项加新增 static contract 全部通过。

- [ ] **步骤 4：运行编译、旧 WebUI JS 和 Golden 基准**

~~~bash
env PYTHONPYCACHEPREFIX=/tmp/tcad-m2-compile \
  /opt/anaconda3/bin/python3 -m py_compile tcad_simulator.py tools/*.py

/opt/anaconda3/bin/python3 -c 'import tcad_simulator as t; print(t._WEBUI_SCRIPT_JS)' \
  | node --check -

env TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-m2-golden \
  /opt/anaconda3/bin/python3 tools/run_process_cad_baseline.py \
  --grid 128 --output /tmp/tcad-m2-five-flow.json

git diff --check
~~~

预期：compile 和 node exit 0；5 套流程均 ok:true；diff-check 无输出。

- [ ] **步骤 5：生产式 /studio/ 浏览器验收**

构建 frontend 后直接启动 Python WebUI，不启动 Vite。检查：

1. /studio/ 能初始化真实 Session；
2. / 仍为旧 WebUI；
3. 1280 px 宽三栏完整可见；
4. 参数合法保存、非法不发送；
5. Run Selected/To/All 状态正确；
6. Timeline 只恢复有效快照；
7. 真实模型可旋转、平移、缩放、Fit 和 ISO；
8. WebGL/材料错误均为可见状态；
9. 相机操作不产生 Worker/mesh 请求。

- [ ] **步骤 6：提交文档**

~~~bash
git add README.md docs/ARCHITECTURE_TARGET.md docs/ROADMAP_PROCESS_CAD.md \
  docs/superpowers/specs/2026-08-30-m2-react-shell-design.md
git commit -m "docs(M2): 记录 React Shell 运行与验收"
git push backup codex/m2-react-shell
~~~

- [ ] **步骤 7：最终审查准备**

~~~bash
git status --short --branch
git log --oneline --decorate backup/main..HEAD
git diff --stat backup/main...HEAD
git ls-remote backup refs/heads/codex/m2-react-shell
git ls-remote origin refs/heads/codex/m2-react-shell
~~~

要求：tracked worktree clean；本地 HEAD 与 backup 分支 SHA 一致；origin 不存在该功能分支。
输出 Goal、Base Commit、Final Commit、Changed Files、Architecture Decisions、Existing APIs
Reused、Tests Added、Tests Executed、Known Limitations、Risks、Diff Summary 和 Reviewer
Checklist，等待独立 architecture/code review，不自行合并 main。
