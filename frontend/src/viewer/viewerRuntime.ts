import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {STLLoader} from 'three/examples/jsm/loaders/STLLoader.js';
import type {TcadApi, ModelSummaryView, DisplayManifestView} from '../api/types';
import {parseDisplayGeometry} from './displayGeometry';
import {sourceVisible} from './stepVisibility';
import {createMaterialSections, type SectionColor} from './materialSections';
import {clipStateAllOff, applyClipState, type ClipState} from './clipping';
import {calculateOrthographicFit, calculatePerspectiveFit} from './fitCamera';
import {createMeshLoader, type LoadedMesh} from './meshLoader';
import {pickAtNormalizedCoords, type PickCandidate, type PickHit} from './picking';

export type StandardView = 'iso' | 'top' | 'bottom' | 'front' | 'back' | 'left' | 'right';
export type ProjectionMode = 'perspective' | 'orthographic';

export interface MaterialSummary {
  matId: number;
  name: string;
  visible: boolean;
  opacity: number;
}

export interface MaterialDisplay {
  visible?: boolean;
  opacity?: number;
}

export type MeasureMarkerPoints = ReadonlyArray<readonly [number, number, number]>;

export interface ViewerRuntime {
  setHiddenStepIds?(ids: readonly string[]): void;
  setSectionContext?(model: ModelSummaryView | null, onError: (error: unknown | null) => void): void;
  readonly backend: string;
  mount(container: HTMLElement): void;
  setStandardView(view: StandardView): void;
  setProjection(mode: ProjectionMode): void;
  setClipping(state: ClipState): void;
  setMaterialDisplay(matId: number, display: MaterialDisplay): void;
  pickAt(ndcX: number, ndcY: number): PickHit | null;
  setMeasureMarkers(points: MeasureMarkerPoints | null): void;
  fit(): void;
  loadMeshes(token: number, retry?: boolean): Promise<{warnings: string[]; materials: MaterialSummary[]; stale?: boolean; display?: DisplayManifestView; displayError?: string}>;
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
 * 相机、视图与材质显示属于本地状态。模型加载拉取 manifest/STL；
 * 裁剪封口只渲染冻结 slice API 返回的真实材料，并核对 mesh revision。
 */
export function createThreeViewerRuntime(api: TcadApi): ViewerRuntime {
  let renderer: THREE.WebGLRenderer | null = null;
  let scene: THREE.Scene | null = null;
  let camera: THREE.PerspectiveCamera | null = null;
  let orthoCamera: THREE.OrthographicCamera | null = null;
  let projection: ProjectionMode = 'perspective';
  let controls: OrbitControls | null = null;
  let group: THREE.Group | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let container: HTMLElement | null = null;
  let canvas: HTMLCanvasElement | null = null;
  let renderHandle = 0;
  let disposed = false;
  let firstLoadDone = false;
  let backendLabel = 'WebGL2';
  let clipState: ClipState = clipStateAllOff();
  const meshesByGroup = new Map<string, THREE.Mesh>();
  let hiddenStepIds = new Set<string>();
  let displayManifest: DisplayManifestView | null = null;
  let loadGeneration = 0;
  let selectedMesh: THREE.Mesh | null = null;
  let markerGroup: THREE.Group | null = null;
  const sectionGroup = new THREE.Group();
  let sectionNeedsReload = false;
  const sections = createMaterialSections(sectionGroup, (request, signal) => {
    if (request.revision !== undefined) {
      if (!api.getDisplaySlice) return Promise.reject(new Error('Paired display slice API unavailable'));
      return api.getDisplaySlice({axis:request.axis,index:request.index,revision:request.revision},signal);
    }
    if (!api.getMaterialSlice) return Promise.reject(new Error('Material slice API unavailable'));
    return api.getMaterialSlice(request, signal);
  }, async (revision,signal) => {
    if (displayManifest?.available) return !signal.aborted && displayManifest.revision === revision;
    const current = (await api.getPreviewManifest({mode:'solid',faceLimit:40000},signal)).revision;
    if (!signal.aborted && current !== revision) sectionNeedsReload = true;
    return current === revision;
  }, () => renderer?.capabilities.maxTextureSize ?? 4096);
  let modelSummary: ModelSummaryView | null = null;
  let sectionError: (error: unknown | null) => void = () => {};
  let sectionGeneration = 0;
  let meshRevision = -1;
  let meshesLoading = false;
  let sectionMaterials = new Map<number, SectionColor>();

  const updateSections = (localOnly = false) => {
    const generation = localOnly ? sectionGeneration : ++sectionGeneration;
    const materials = new Map(sectionMaterials);
    const bounds = group && group.children.length ? new THREE.Box3().setFromObject(group) : new THREE.Box3();
    void sections.update({model: meshesLoading ? null : modelSummary, revision:meshRevision,bounds,clip:clipState,materials,sourceMode:!!displayManifest?.available,ownerStepIds:displayManifest?.ownerStepIds,hiddenStepIds,localOnly}).then(ids => {
      if (generation !== sectionGeneration || disposed) return;
      sectionError(ids.length ? new Error(`Unknown slice materials: ${ids.join(', ')}`) : null);
      scheduleRender();
    }).catch(error => {
      if (generation !== sectionGeneration || disposed) return;
      sectionError(error); scheduleRender();
    });
  };

  const stlLoader = new STLLoader();
  const meshLoader = createMeshLoader({
    fetchManifest: (request, signal) => api.getPreviewManifest(request, signal),
    fetchStl: (request, signal) => api.getMaterialStl(request, signal),
    parseStl: bytes => stlLoader.parse(bytes),
    ...(api.getDisplayManifest && api.getDisplayMesh && api.getDisplaySlice ? {
      fetchDisplayManifest: (signal:AbortSignal) => api.getDisplayManifest!(signal),
      fetchDisplayMesh: (request:import('../api/types').DisplayMeshRequest,signal:AbortSignal) => api.getDisplayMesh!(request,signal),
      parseDisplayMesh:parseDisplayGeometry,
    } : {}),
  });

  const activeCamera = (): THREE.PerspectiveCamera | THREE.OrthographicCamera | null =>
    projection === 'orthographic' ? orthoCamera : camera;

  const viewAspect = (): number => {
    if (container === null) return 1;
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    return width / height;
  };

  const scheduleRender = () => {
    if (disposed || renderer === null || scene === null) return;
    const view = activeCamera();
    if (view === null) return;
    if (renderHandle !== 0) return;
    renderHandle = requestAnimationFrame(() => {
      renderHandle = 0;
      if (disposed || renderer === null || scene === null) return;
      const current = activeCamera();
      if (current === null) return;
      renderer.render(scene, current);
    });
  };

  const resize = () => {
    if (renderer === null || container === null) return;
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    const aspect = width / height;
    renderer.setSize(width, height, false);
    if (camera !== null) {
      camera.aspect = Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
      camera.updateProjectionMatrix();
    }
    if (orthoCamera !== null) {
      // 保持半高不变，仅按新宽高比重排半宽，避免布局变化改变放大倍率
      const halfHeight = (orthoCamera.top - orthoCamera.bottom) / 2;
      const halfWidth = halfHeight * (Number.isFinite(aspect) && aspect > 0 ? aspect : 1);
      orthoCamera.left = -halfWidth;
      orthoCamera.right = halfWidth;
      orthoCamera.updateProjectionMatrix();
    }
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
    if (controls === null) return;
    if (projection === 'orthographic') {
      if (orthoCamera === null) return;
      const fit = calculateOrthographicFit(contentBounds(), viewAspect());
      orthoCamera.left = -fit.halfWidth;
      orthoCamera.right = fit.halfWidth;
      orthoCamera.top = fit.halfHeight;
      orthoCamera.bottom = -fit.halfHeight;
      orthoCamera.near = fit.near;
      orthoCamera.far = fit.far;
      orthoCamera.position.copy(direction).multiplyScalar(fit.distance).add(fit.target);
      orthoCamera.up.set(0, 0, 1);
      orthoCamera.lookAt(fit.target);
      orthoCamera.updateProjectionMatrix();
      controls.target.copy(fit.target);
      controls.update();
      scheduleRender();
      return;
    }
    if (camera === null) return;
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

  const rebindControls = (target: THREE.Vector3) => {
    if (renderer === null) return;
    const view = activeCamera();
    if (view === null) return;
    controls?.dispose();
    controls = new OrbitControls(view, renderer.domElement);
    controls.addEventListener('change', scheduleRender);
    controls.target.copy(target);
    controls.update();
  };

  const applyClippingToMaterials = () => {
    if (renderer === null || group === null) return;
    const planes = applyClipState(group,clipState,contentBounds());
    renderer.localClippingEnabled = planes.length > 0;
  };

  const runtime: ViewerRuntime = {
    setHiddenStepIds(ids) {
      hiddenStepIds = new Set(ids);
      for (const mesh of meshesByGroup.values()) {
        mesh.visible = (sectionMaterials.get(mesh.userData.matId)?.visible ?? true) && sourceVisible(mesh.userData.ownerId,mesh.userData.stepId,hiddenStepIds);
      }
      if (selectedMesh && !selectedMesh.visible) {(selectedMesh.material as THREE.MeshStandardMaterial).emissive.setHex(0); selectedMesh = null;}
      updateSections(true); scheduleRender();
    },
    setSectionContext(model, onError) {
      modelSummary = model; sectionError = onError; updateSections();
    },
    get backend() {
      return backendLabel;
    },
    mount(host: HTMLElement) {
      if (disposed || container !== null) return;
      container = host;
      canvas = document.createElement('canvas');
      canvas.className = 'viewer-canvas';
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
      orthoCamera = new THREE.OrthographicCamera(-5, 5, 5, -5, -50, 200);
      orthoCamera.up.set(0, 0, 1);
      const hemisphere = new THREE.HemisphereLight(0xbfd6ea, 0x1a2431, 1.1);
      const key = new THREE.DirectionalLight(0xffffff, 1.6);
      key.position.set(6, -8, 10);
      scene.add(hemisphere, key);
      group = new THREE.Group();
      scene.add(group, sectionGroup);

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
    setProjection(mode: ProjectionMode) {
      if (mode === projection) return;
      const view = activeCamera();
      if (view === null || controls === null || renderer === null) return;
      const target = controls.target.clone();
      const offset = view.position.clone().sub(target);
      const direction = offset.clone().normalize();
      const aspect = viewAspect();
      const radius = Math.max(
        contentBounds().getBoundingSphere(new THREE.Sphere()).radius,
        1e-6,
      );
      if (mode === 'orthographic') {
        if (orthoCamera === null || camera === null) return;
        // 等效视尺寸：与当前透视相机在相同距离处的可见半高一致，切换无视觉跳变
        const halfHeight = Math.max(
          offset.length() * Math.tan((camera.fov * Math.PI) / 360),
          1e-6,
        );
        const halfWidth = halfHeight * aspect;
        orthoCamera.left = -halfWidth;
        orthoCamera.right = halfWidth;
        orthoCamera.top = halfHeight;
        orthoCamera.bottom = -halfHeight;
        orthoCamera.near = -(radius * 4);
        orthoCamera.far = offset.length() + radius * 4;
        orthoCamera.position.copy(view.position);
        orthoCamera.up.set(0, 0, 1);
        orthoCamera.lookAt(target);
        orthoCamera.updateProjectionMatrix();
      } else {
        if (camera === null || orthoCamera === null) return;
        const halfHeight = Math.max((orthoCamera.top - orthoCamera.bottom) / 2, 1e-6);
        const distance = halfHeight / Math.tan((camera.fov * Math.PI) / 360);
        camera.near = Math.max((distance - radius) * 0.05, 1e-3);
        camera.far = Math.max((distance + radius) * 4, camera.near * 2);
        camera.position.copy(target).addScaledVector(direction, distance);
        camera.lookAt(target);
        camera.updateProjectionMatrix();
      }
      projection = mode;
      rebindControls(target);
      scheduleRender();
    },
    setClipping(state: ClipState) {
      clipState = state;
      applyClippingToMaterials();
      updateSections();
      scheduleRender();
    },
    setMaterialDisplay(matId: number, display: MaterialDisplay) {
      const visual = sectionMaterials.get(matId);
      if (!visual) return;
      sectionMaterials.set(matId,{...visual,...display,opacity:display.opacity === undefined ? visual.opacity : Math.min(1,Math.max(0,display.opacity))});
      for (const mesh of meshesByGroup.values()) {
      if (mesh.userData.matId !== matId) continue;
      if (display.visible !== undefined) mesh.visible = display.visible && sourceVisible(mesh.userData.ownerId,mesh.userData.stepId,hiddenStepIds);
      if (display.opacity !== undefined) {
        const material = mesh.material as THREE.MeshStandardMaterial;
        const opacity = Math.min(1, Math.max(0, display.opacity));
        material.opacity = opacity;
        material.transparent = opacity < 1;
        material.needsUpdate = true;
      }
      }
      updateSections(true);
      scheduleRender();
    },
    pickAt(ndcX: number, ndcY: number): PickHit | null {
      const view = activeCamera();
      if (view === null) return null;
      const candidates: PickCandidate[] = [...sections.pickCandidates()];
      for (const mesh of meshesByGroup.values()) {
        if (!mesh.visible) continue;
        candidates.push({mesh, matId:mesh.userData.matId, name: mesh.name,ownerId:mesh.userData.ownerId,stepId:mesh.userData.stepId});
      }
      const hit = pickAtNormalizedCoords(candidates, view, ndcX, ndcY);
      const previous = selectedMesh;
      selectedMesh = hit !== null ? [...meshesByGroup.values()].find(mesh => mesh.userData.matId === hit.matId && mesh.userData.ownerId === hit.ownerId) ?? null : null;
      if (previous !== null && previous !== selectedMesh) {
        (previous.material as THREE.MeshStandardMaterial).emissive.setHex(0x000000);
      }
      if (selectedMesh !== null) {
        (selectedMesh.material as THREE.MeshStandardMaterial).emissive.setHex(0x1a3a5c);
      }
      scheduleRender();
      return hit;
    },
    setMeasureMarkers(points: MeasureMarkerPoints | null) {
      if (scene === null) return;
      if (markerGroup === null) {
        markerGroup = new THREE.Group();
        scene.add(markerGroup);
      }
      for (const child of markerGroup.children.slice()) {
        markerGroup.remove(child);
        const mesh = child as THREE.Mesh;
        if (mesh.material !== undefined) (mesh.material as THREE.Material).dispose();
        mesh.geometry?.dispose();
      }
      if (points !== null && points.length > 0) {
        const markerMaterial = new THREE.MeshBasicMaterial({color: 0x4f9cf9});
        const radius = contentBounds().getBoundingSphere(new THREE.Sphere()).radius * 0.01;
        const geometry = new THREE.SphereGeometry(Math.max(radius, 1e-4), 12, 8);
        for (const [x, y, z] of points) {
          const marker = new THREE.Mesh(geometry, markerMaterial);
          marker.position.set(x, y, z);
          markerGroup.add(marker);
        }
        if (points.length === 2) {
          const lineGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(...points[0]),
            new THREE.Vector3(...points[1]),
          ]);
          markerGroup.add(
            new THREE.Line(lineGeometry, new THREE.LineBasicMaterial({color: 0x4f9cf9})),
          );
        }
      }
      scheduleRender();
    },
    fit() {
      const view = activeCamera();
      if (view === null) return;
      const direction = view.position.clone().sub(controls?.target ?? new THREE.Vector3());
      if (direction.lengthSq() < 1e-9) direction.copy(VIEW_DIRECTIONS.iso);
      applyPose(direction.normalize());
    },
    async loadMeshes(token: number, retry = false) {
      const generation = ++loadGeneration;
      meshesLoading = true; updateSections();
      let result: Awaited<ReturnType<typeof meshLoader.load>>;
      try {result = await meshLoader.load(token,undefined,sectionNeedsReload || retry);} catch(error) {
        if (generation !== loadGeneration || disposed) return {warnings:[],materials:[],stale:true};
        // Retain the last complete view, but avoid mixing its caps with a newer model.
        displayManifest = null; runtime.setHiddenStepIds?.([]); throw error;
      }
      if (result.stale || generation !== loadGeneration || disposed || group === null) {
        return {warnings: result.warnings, materials: [] as MaterialSummary[], stale: true};
      }
      const preserveDisplay = meshRevision === result.revision;
      const previousDisplay = new Map(sectionMaterials);
      meshesLoading = false; meshRevision = result.revision; sectionNeedsReload = false;
      displayManifest = result.display ?? null;
      sectionMaterials = new Map(result.visuals.map(visual => [visual.materialId, preserveDisplay && previousDisplay.has(visual.materialId) ? previousDisplay.get(visual.materialId)! : {color:visual.color,opacity:visual.opacity,visible:visual.visible,name:visual.displayName}]));
      const previous = group.children.slice();
      group.clear();
      meshesByGroup.clear();
      selectedMesh = null;
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
        const display = sectionMaterials.get(entry.mesh.materialId)!;
        mesh.visible = display.visible && sourceVisible(entry.ownerId,entry.stepId,hiddenStepIds);
        material.opacity = display.opacity; material.transparent = display.opacity < 1;
        mesh.name = entry.mesh.name;
        mesh.userData = {matId:entry.mesh.materialId,ownerId:entry.ownerId,stepId:entry.stepId};
        group.add(mesh);
        meshesByGroup.set(`${entry.ownerId ?? 'formal'}:${entry.mesh.materialId}`, mesh);
      }
      const materials: MaterialSummary[] = result.visuals.map(visual => ({matId:visual.materialId,name:visual.displayName,visible:sectionMaterials.get(visual.materialId)!.visible,opacity:sectionMaterials.get(visual.materialId)!.opacity}));
      if (!firstLoadDone && result.meshes.length > 0) {
        firstLoadDone = true;
        runtime.setStandardView('iso');
      }
      applyClippingToMaterials();
      updateSections();
      scheduleRender();
      return {warnings: result.warnings, materials, display:result.display,displayError:result.displayError};
    },
    dispose() {
      disposed = true;
      sectionGeneration++; sections.dispose();
      if (renderHandle !== 0) {
        cancelAnimationFrame(renderHandle);
        renderHandle = 0;
      }
      meshLoader.dispose();
      loadGeneration++; meshesByGroup.clear();
      selectedMesh = null;
      if (markerGroup !== null) {
        for (const child of markerGroup.children.slice()) {
          markerGroup.remove(child);
          const mesh = child as THREE.Mesh;
          if (mesh.material !== undefined) (mesh.material as THREE.Material).dispose();
          mesh.geometry?.dispose();
        }
        scene?.remove(markerGroup);
        markerGroup = null;
      }
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
      orthoCamera = null;
      group = null;
    },
  };

  return runtime;
}
