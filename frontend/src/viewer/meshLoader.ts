import type {BufferGeometry} from 'three';
import type {
  DisplayManifestView, DisplayMeshRequest,
  PreviewManifestRequest,
  PreviewManifestView,
  PreviewMeshView,
  PreviewStlRequest,
  MaterialVisualView,
} from '../api/types';

export interface MaterialConfig {
  color: readonly [number, number, number];
  opacity: number;
  metallic: number;
  roughness: number;
  transparent: boolean;
}

export interface LoadedMesh {
  ownerId?: number;
  stepId?: string | null;
  mesh: PreviewMeshView;
  geometry: BufferGeometry;
  material: MaterialConfig;
}

export interface MeshLoadResult {
  display?: DisplayManifestView;
  displayError?: string;
  visuals: MaterialVisualView[];
  revision: number;
  meshes: LoadedMesh[];
  warnings: string[];
  stale: boolean;
  cached: boolean;
}

export interface MeshLoaderDependencies {
  fetchDisplayManifest?(signal: AbortSignal): Promise<DisplayManifestView>;
  fetchDisplayMesh?(request: DisplayMeshRequest, signal: AbortSignal): Promise<ArrayBuffer>;
  parseDisplayMesh?(bytes: ArrayBuffer): BufferGeometry;
  fetchManifest(
    request: PreviewManifestRequest,
    signal: AbortSignal,
  ): Promise<PreviewManifestView>;
  fetchStl(request: PreviewStlRequest, signal: AbortSignal): Promise<ArrayBuffer>;
  parseStl(bytes: ArrayBuffer): BufferGeometry;
  concurrency?: number;
}

export interface MeshLoader {
  load(token: number, signal?: AbortSignal, forceManifest?: boolean): Promise<MeshLoadResult>;
  dispose(): void;
}

const STL_MODE = 'solid' as const;
const DEFAULT_CONCURRENCY = 4;
// Match the backend StructureDisplayCache's fixed per-revision budgets.
const DISPLAY_TRIANGLE_BUDGET = 1_000_000;
const DISPLAY_BYTE_BUDGET = 128 * 1024 * 1024;

function staleResult(): MeshLoadResult {
  return {revision: -1, meshes: [], visuals: [], warnings: [], stale: true, cached: false};
}

function toMaterialConfig(visual: PreviewMeshView['visual']): MaterialConfig {
  return {
    color: visual.color,
    opacity: visual.opacity,
    metallic: visual.metallic,
    roughness: visual.roughness,
    transparent: visual.opacity < 1,
  };
}

async function mapWithConcurrency<TIn, TOut>(
  items: TIn[],
  concurrency: number,
  worker: (item: TIn) => Promise<TOut>,
): Promise<TOut[]> {
  const results = new Array<TOut>(items.length);
  let cursor = 0;
  const lanes = Array.from({length: Math.max(1, Math.min(concurrency, items.length))}, async () => {
    while (cursor < items.length) {
      const current = cursor;
      cursor += 1;
      results[current] = await worker(items[current]);
    }
  });
  await Promise.all(lanes);
  return results;
}

interface CacheEntry {
  display?: DisplayManifestView;
  displayError?: string;
  visuals: MaterialVisualView[];
  revision: number;
  meshes: LoadedMesh[];
  complete: boolean;
}

/**
 * 按 refreshToken 加载工艺网格：先取 manifest，再按 manifest 返回的真实 revision
 * 下载可见材料的 STL。新 token 开始时取消旧一代的进行中请求，旧结果标记 stale。
 */
export function createMeshLoader(deps: MeshLoaderDependencies): MeshLoader {
  let generation = 0;
  let lastToken: number | null = null;
  let cache: CacheEntry | null = null;
  const ownedGeometries = new Set<BufferGeometry>();
  let activeControllers = new Set<AbortController>();

  const abortActive = () => {
    for (const controller of activeControllers) controller.abort();
    activeControllers = new Set();
  };
  const retireCache = (previous: CacheEntry | null, next: LoadedMesh[]) => {
    const retained = new Set(next.map(entry => entry.geometry));
    const retired = new Set(previous?.meshes.map(entry => entry.geometry));
    for (const geometry of retired) {
      if (retained.has(geometry)) continue;
      geometry.dispose();
      ownedGeometries.delete(geometry);
    }
  };

  const load = async (token: number, signal?: AbortSignal, forceManifest = false): Promise<MeshLoadResult> => {
    if (signal?.aborted) return staleResult();
    if (!forceManifest && token === lastToken && cache?.complete) {
      return {...staleResult(), stale: false, cached: true, ...cache};
    }

    const currentGeneration = ++generation;
    abortActive();
    const manifestRequest: PreviewManifestRequest = {mode: STL_MODE, faceLimit: 40000};
    let manifest: PreviewManifestView;
    const manifestController = new AbortController();
    activeControllers.add(manifestController);
    const abortManifest = () => manifestController.abort();
    signal?.addEventListener('abort', abortManifest);
    try {
      manifest = await deps.fetchManifest(manifestRequest, manifestController.signal);
    } catch (error) {
      if (currentGeneration !== generation || manifestController.signal.aborted
        || (error instanceof Error && error.name === 'AbortError')) return staleResult();
      throw error;
    } finally {
      signal?.removeEventListener('abort', abortManifest);
      activeControllers.delete(manifestController);
    }
    if (currentGeneration !== generation || signal?.aborted) return staleResult();

    if (cache?.complete && cache.revision === manifest.revision && !(forceManifest && cache.displayError)) {
      lastToken = token;
      return {...cache, visuals: manifest.meshes.map(entry => entry.visual), warnings: [], stale: false, cached: true};
    }

    let display: DisplayManifestView | undefined;
    let displayError: string | undefined;
    if (deps.fetchDisplayManifest && deps.fetchDisplayMesh && deps.parseDisplayMesh) {
      const controller = new AbortController(); activeControllers.add(controller);
      const abort = () => controller.abort(); signal?.addEventListener('abort', abort);
      const created: BufferGeometry[] = [];
      let published = false;
      try {
        display = await deps.fetchDisplayManifest(controller.signal);
        if (currentGeneration !== generation || controller.signal.aborted) return staleResult();
        if (display.revision !== manifest.revision) throw new Error('Display model revision changed; reload geometry');
        if (!display.available) throw new Error(display.unavailableReasons.join(', ') || 'Display unavailable');
        const totals = display.groups.reduce((sum, entry) => ({
          triangles: sum.triangles + entry.triangleCount, bytes: sum.bytes + entry.bytes,
        }), {triangles: 0, bytes: 0});
        if (!Number.isSafeInteger(totals.triangles) || !Number.isSafeInteger(totals.bytes)
          || totals.triangles > DISPLAY_TRIANGLE_BUDGET || totals.bytes > DISPLAY_BYTE_BUDGET) {
          throw new Error('display_budget_exceeded');
        }
        const visuals = new Map(manifest.meshes.map(entry => [entry.materialId,entry]));
        const loaded = await mapWithConcurrency(display.groups, deps.concurrency ?? DEFAULT_CONCURRENCY, async entry => {
          const formal = visuals.get(entry.materialId);
          if (!formal) throw new Error(`Unknown display material: ${entry.materialId}`);
          const bytes = await deps.fetchDisplayMesh!({revision:display!.revision,ownerId:entry.ownerId,materialId:entry.materialId},controller.signal);
          if (currentGeneration !== generation || controller.signal.aborted) throw new Error('Display load aborted');
          if (bytes.byteLength !== entry.bytes) throw new Error('Display mesh byte length does not match manifest');
          const geometry = deps.parseDisplayMesh!(bytes); created.push(geometry);
          return {ownerId:entry.ownerId,stepId:entry.stepId,mesh:{...formal,triangleCount:entry.triangleCount,boundingBox:entry.boundingBox},geometry,material:toMaterialConfig(formal.visual)};
        });
        if (currentGeneration !== generation || controller.signal.aborted) return staleResult();
        created.forEach(geometry => ownedGeometries.add(geometry));
        published = true;
        const previous = cache;
        cache = {revision:manifest.revision,meshes:loaded,visuals:manifest.meshes.map(entry => entry.visual),complete:true,display}; lastToken = token;
        retireCache(previous, loaded);
        return {...cache,warnings:[],stale:false,cached:false};
      } catch (error) {
        controller.abort();
        if (currentGeneration !== generation || signal?.aborted) return staleResult();
        displayError = error instanceof Error ? error.message : String(error);
        if (display) display = {...display,available:false,groups:[],unavailableReasons:[displayError]};
        else display = {revision:manifest.revision,available:false,bounds:{min:[0,0,0],max:[0,0,0]},ownerStepIds:{},groups:[],stepEntities:[],unavailableReasons:[displayError]};
      } finally {
        if (!published) new Set(created).forEach(geometry => geometry.dispose());
        signal?.removeEventListener('abort', abort);
        activeControllers.delete(controller);
      }
    }

    const requested = manifest.meshes.filter(entry => entry.visual?.visible !== false);
    const reusable = new Map(cache?.revision === manifest.revision
      ? cache.meshes.map(entry => [entry.mesh.materialId, entry]) : []);
    const warnings: string[] = [];
    const createdFormal = new Set<BufferGeometry>();
    const meshes = await mapWithConcurrency(
      requested,
      deps.concurrency ?? DEFAULT_CONCURRENCY,
      async (entry): Promise<LoadedMesh | null> => {
        if (currentGeneration !== generation || signal?.aborted) return null;
        const existing = reusable.get(entry.materialId);
        if (existing) return {...existing, mesh: entry, material: toMaterialConfig(entry.visual)};
        const controller = new AbortController();
        activeControllers.add(controller);
        const onExternalAbort = () => controller.abort();
        signal?.addEventListener('abort', onExternalAbort);
        try {
          const request: PreviewStlRequest = {
            materialId: entry.materialId,
            revision: manifest.revision,
            mode: STL_MODE,
          };
          const bytes = await deps.fetchStl(request, controller.signal);
          if (currentGeneration !== generation || controller.signal.aborted) return null;
          const geometry = deps.parseStl(bytes);
          createdFormal.add(geometry);
          ownedGeometries.add(geometry);
          return {mesh: entry, geometry, material: toMaterialConfig(entry.visual)};
        } catch (error) {
          if (controller.signal.aborted) return null;
          warnings.push(`${entry.name}: ${error instanceof Error ? error.message : String(error)}`);
          return null;
        } finally {
          signal?.removeEventListener('abort', onExternalAbort);
          activeControllers.delete(controller);
        }
      },
    );

    if (currentGeneration !== generation || signal?.aborted) {
      for (const geometry of createdFormal) {
        geometry.dispose(); ownedGeometries.delete(geometry);
      }
      return staleResult();
    }
    const loaded = meshes.filter((entry): entry is LoadedMesh => entry !== null);
    const visuals = manifest.meshes.map(entry => entry.visual);
    const previous = cache;
    cache = {revision: manifest.revision, meshes: loaded, visuals, complete: loaded.length === requested.length, display, displayError};
    retireCache(previous, loaded);
    lastToken = token;
    return {...cache, warnings, stale: false, cached: false};
  };

  const dispose = () => {
    generation += 1;
    abortActive();
    for (const geometry of ownedGeometries) geometry.dispose();
    ownedGeometries.clear();
    cache = null;
    lastToken = null;
  };

  return {load, dispose};
}
