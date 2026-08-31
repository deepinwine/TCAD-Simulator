import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {STLLoader} from 'three/examples/jsm/loaders/STLLoader.js';
import type {TcadApi} from '../api/types';
import {calculatePerspectiveFit} from './fitCamera';
import {createMeshLoader, type LoadedMesh} from './meshLoader';

export type StandardView = 'iso' | 'top' | 'bottom' | 'front' | 'back' | 'left' | 'right';

export interface ViewerRuntime {
  readonly backend: string;
  mount(container: HTMLElement): void;
  setStandardView(view: StandardView): void;
  fit(): void;
  loadMeshes(token: number): Promise<{warnings: string[]}>;
  dispose(): void;
}

const VIEW_DIRECTIONS: Record<StandardView, THREE.Vector3> = {
  iso: new THREE.Vector3(1, 0.7, 1).normalize(),
  top: new THREE.Vector3(0, 1, 0),
  bottom: new THREE.Vector3(0, -1, 0),
  front: new THREE.Vector3(0, 0, 1),
  back: new THREE.Vector3(0, 0, -1),
  left: new THREE.Vector3(-1, 0, 0),
  right: new THREE.Vector3(1, 0, 0),
};

/**
 * 真实 Three.js Viewer runtime。
 *
 * 相机、视图与渲染全部浏览器本地完成，不触发任何 API 请求；只有
 * loadMeshes（refreshToken 变化时）经冻结契约拉取 manifest 与 STL。
 */
export function createThreeViewerRuntime(api: TcadApi): ViewerRuntime {
  let renderer: THREE.WebGLRenderer | null = null;
  let scene: THREE.Scene | null = null;
  let camera: THREE.PerspectiveCamera | null = null;
  let controls: OrbitControls | null = null;
  let group: THREE.Group | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let container: HTMLElement | null = null;
  let canvas: HTMLCanvasElement | null = null;
  let renderHandle = 0;
  let disposed = false;
  let firstLoadDone = false;
  let backendLabel = 'WebGL2';

  const stlLoader = new STLLoader();
  const meshLoader = createMeshLoader({
    fetchManifest: (request, signal) => api.getPreviewManifest(request, signal),
    fetchStl: (request, signal) => api.getMaterialStl(request, signal),
    parseStl: bytes => stlLoader.parse(bytes),
  });

  const scheduleRender = () => {
    if (disposed || renderer === null || scene === null || camera === null) return;
    if (renderHandle !== 0) return;
    renderHandle = requestAnimationFrame(() => {
      renderHandle = 0;
      if (disposed || renderer === null || scene === null || camera === null) return;
      renderer.render(scene, camera);
    });
  };

  const resize = () => {
    if (renderer === null || camera === null || container === null) return;
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    scheduleRender();
  };

  const contentBounds = (): THREE.Box3 => {
    const bounds = new THREE.Box3();
    if (group !== null && group.children.length > 0) {
      bounds.setFromObject(group);
    } else {
      bounds.set(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1));
    }
    return bounds;
  };

  const applyPose = (direction: THREE.Vector3) => {
    if (camera === null || controls === null) return;
    const fit = calculatePerspectiveFit(
      contentBounds(),
      camera.fov,
      Number.isFinite(camera.aspect) && camera.aspect > 0 ? camera.aspect : 1,
    );
    camera.near = fit.near;
    camera.far = fit.far;
    camera.position.copy(direction).multiplyScalar(fit.distance).add(fit.target);
    camera.lookAt(fit.target);
    controls.target.copy(fit.target);
    controls.update();
    scheduleRender();
  };

  const runtime: ViewerRuntime = {
    get backend() {
      return backendLabel;
    },
    mount(host: HTMLElement) {
      if (disposed || container !== null) return;
      container = host;
      canvas = document.createElement('canvas');
      canvas.className = 'viewer-canvas';
      canvas.setAttribute('aria-label', '3D 工艺结构预览');
      canvas.setAttribute('role', 'img');
      host.appendChild(canvas);
      try {
        // 只在真实 canvas 上创建一次 renderer；失败抛出真实原因，不做预探测。
        renderer = new THREE.WebGLRenderer({canvas, antialias: true});
        const gl = renderer.getContext();
        const version = gl.getParameter(gl.VERSION) as string;
        backendLabel = version.includes('WebGL 2') ? 'WebGL2' : 'WebGL1';
      } catch (error) {
        canvas.remove();
        canvas = null;
        renderer = null;
        throw error;
      }

      scene = new THREE.Scene();
      scene.background = new THREE.Color(0x0d141e);
      camera = new THREE.PerspectiveCamera(40, 1, 0.1, 1000);
      camera.up.set(0, 0, 1);
      const hemisphere = new THREE.HemisphereLight(0xbfd6ea, 0x1a2431, 1.1);
      const key = new THREE.DirectionalLight(0xffffff, 1.6);
      key.position.set(6, -8, 10);
      scene.add(hemisphere, key);
      group = new THREE.Group();
      scene.add(group);

      controls = new OrbitControls(camera, renderer.domElement);
      controls.addEventListener('change', scheduleRender);

      resizeObserver = new ResizeObserver(() => resize());
      resizeObserver.observe(host);
      resize();
      applyPose(VIEW_DIRECTIONS.iso);
    },
    setStandardView(view: StandardView) {
      applyPose(VIEW_DIRECTIONS[view]);
    },
    fit() {
      if (camera === null) return;
      const direction = camera.position.clone().sub(controls?.target ?? new THREE.Vector3());
      if (direction.lengthSq() < 1e-9) direction.copy(VIEW_DIRECTIONS.iso);
      applyPose(direction.normalize());
    },
    async loadMeshes(token: number) {
      const result = await meshLoader.load(token);
      if (result.stale || disposed || group === null) return {warnings: result.warnings};
      const previous = group.children.slice();
      group.clear();
      for (const child of previous) {
        const mesh = child as THREE.Mesh;
        (mesh.material as THREE.Material).dispose();
      }
      for (const entry of result.meshes as LoadedMesh[]) {
        const material = new THREE.MeshStandardMaterial({
          color: new THREE.Color(
            entry.material.color[0],
            entry.material.color[1],
            entry.material.color[2],
          ),
          opacity: entry.material.opacity,
          transparent: entry.material.transparent,
          metalness: entry.material.metallic,
          roughness: entry.material.roughness,
          side: THREE.DoubleSide,
        });
        const mesh = new THREE.Mesh(entry.geometry, material);
        mesh.name = entry.mesh.name;
        group.add(mesh);
      }
      if (!firstLoadDone && result.meshes.length > 0) {
        firstLoadDone = true;
        runtime.setStandardView('iso');
      }
      scheduleRender();
      return {warnings: result.warnings};
    },
    dispose() {
      disposed = true;
      if (renderHandle !== 0) {
        cancelAnimationFrame(renderHandle);
        renderHandle = 0;
      }
      meshLoader.dispose();
      if (group !== null) {
        for (const child of group.children.slice()) {
          const mesh = child as THREE.Mesh;
          (mesh.material as THREE.Material).dispose();
        }
        group.clear();
      }
      controls?.dispose();
      controls = null;
      resizeObserver?.disconnect();
      resizeObserver = null;
      renderer?.dispose();
      renderer = null;
      canvas?.remove();
      canvas = null;
      container = null;
      scene = null;
      camera = null;
      group = null;
    },
  };

  return runtime;
}
