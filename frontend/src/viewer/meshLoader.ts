import type {BufferGeometry} from 'three';
import type {
  PreviewManifestRequest,
  PreviewManifestView,
  PreviewMeshView,
  PreviewStlRequest,
} from '../api/types';

export interface MaterialConfig {
  color: readonly [number, number, number];
  opacity: number;
  metallic: number;
  roughness: number;
  transparent: boolean;
}

export interface LoadedMesh {
  mesh: PreviewMeshView;
  geometry: BufferGeometry;
  material: MaterialConfig;
}

export interface MeshLoadResult {
  revision: number;
  meshes: LoadedMesh[];
  warnings: string[];
  stale: boolean;
  cached: boolean;
}

export interface MeshLoaderDependencies {
  fetchManifest(
    request: PreviewManifestRequest,
    signal: AbortSignal,
  ): Promise<PreviewManifestView>;
  fetchStl(request: PreviewStlRequest, signal: AbortSignal): Promise<ArrayBuffer>;
  parseStl(bytes: ArrayBuffer): BufferGeometry;
  concurrency?: number;
}

export interface MeshLoader {
  load(token: number, signal?: AbortSignal): Promise<MeshLoadResult>;
  dispose(): void;
}

const STL_MODE = 'solid' as const;
const DEFAULT_CONCURRENCY = 4;

function staleResult(): MeshLoadResult {
  return {revision: -1, meshes: [], warnings: [], stale: true, cached: false};
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
  revision: number;
  meshes: LoadedMesh[];
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

  const load = async (token: number, signal?: AbortSignal): Promise<MeshLoadResult> => {
    if (signal?.aborted) return staleResult();
    if (token === lastToken && cache !== null) {
      return {...staleResult(), stale: false, cached: true, ...cache};
    }

    const currentGeneration = ++generation;
    abortActive();
    const manifestRequest: PreviewManifestRequest = {mode: STL_MODE, faceLimit: 40000};
    let manifest: PreviewManifestView;
    try {
      manifest = await deps.fetchManifest(manifestRequest, signal ?? new AbortController().signal);
    } catch {
      return currentGeneration === generation ? staleResult() : staleResult();
    }
    if (currentGeneration !== generation || signal?.aborted) return staleResult();

    if (cache !== null && cache.revision === manifest.revision) {
      lastToken = token;
      return {revision: cache.revision, meshes: cache.meshes, warnings: [], stale: false, cached: true};
    }

    const requested = manifest.meshes.filter(entry => entry.visual?.visible !== false);
    const warnings: string[] = [];
    const meshes = await mapWithConcurrency(
      requested,
      deps.concurrency ?? DEFAULT_CONCURRENCY,
      async (entry): Promise<LoadedMesh | null> => {
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
          const geometry = deps.parseStl(bytes);
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

    if (currentGeneration !== generation) return staleResult();
    const loaded = meshes.filter((entry): entry is LoadedMesh => entry !== null);
    cache = {revision: manifest.revision, meshes: loaded};
    lastToken = token;
    return {revision: manifest.revision, meshes: loaded, warnings, stale: false, cached: false};
  };

  const dispose = () => {
    abortActive();
    for (const geometry of ownedGeometries) geometry.dispose();
    ownedGeometries.clear();
    cache = null;
    lastToken = null;
  };

  return {load, dispose};
}
