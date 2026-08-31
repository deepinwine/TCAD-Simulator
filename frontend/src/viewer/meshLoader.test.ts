import {BufferGeometry} from 'three';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import type {PreviewManifestView, PreviewMeshView, PreviewStlRequest} from '../api/types';
import {createMeshLoader, type MeshLoaderDependencies} from './meshLoader';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, resolve, reject};
}

function mesh(materialId: number, overrides: Partial<PreviewMeshView> = {}): PreviewMeshView {
  return {
    materialId,
    name: `mat-${materialId}`,
    triangleCount: 12,
    boundingBox: {
      min: [0, 0, 0],
      max: [1, 1, 1],
    },
    visual: {
      materialId,
      displayName: `Mat ${materialId}`,
      color: [0.2, 0.4, 0.6],
      opacity: 1,
      metallic: 0.1,
      roughness: 0.5,
      visible: true,
    },
    ...overrides,
  };
}

function manifest(revision: number, meshes: PreviewMeshView[]): PreviewManifestView {
  return {revision, mode: 'solid', meshes};
}

interface FakeOptions {
  firstStl?: Promise<ArrayBuffer>;
  failMaterialId?: number;
  manifestProvider?: (call: number) => PreviewManifestView;
  sharedGeometry?: BufferGeometry;
}

function fakeDependencies(options: FakeOptions = {}) {
  let manifestCalls = 0;
  let stlCalls = 0;
  const controllers: AbortController[] = [];
  const stlRequests: PreviewStlRequest[] = [];
  const fetchManifest = vi.fn(async (_request: unknown, signal: AbortSignal) => {
    manifestCalls += 1;
    void signal;
    return options.manifestProvider
      ? options.manifestProvider(manifestCalls)
      : manifest(3, [mesh(1), mesh(2)]);
  });
  const fetchStl = vi.fn(async (request: PreviewStlRequest, signal: AbortSignal) => {
    stlCalls += 1;
    stlRequests.push(request);
    const controller = new AbortController();
    controllers.push(controller);
    signal.addEventListener('abort', () => controller.abort());
    if (options.failMaterialId === request.materialId) {
      throw new Error(`STL ${request.materialId} 下载失败`);
    }
    if (stlCalls === 1 && options.firstStl) return options.firstStl;
    return new ArrayBuffer(8);
  });
  const parseStl = vi.fn((bytes: ArrayBuffer) => {
    void bytes;
    return options.sharedGeometry ?? new BufferGeometry();
  });
  const deps = {
    fetchManifest,
    fetchStl,
    parseStl,
    manifestCalls: () => manifestCalls,
    stlRequests: () => stlRequests,
    abortCount: () => controllers.filter(controller => controller.signal.aborted).length,
  } satisfies MeshLoaderDependencies & {
    manifestCalls(): number;
    stlRequests(): PreviewStlRequest[];
    abortCount(): number;
  };
  return deps;
}

describe('createMeshLoader', () => {
  let uniqueGeometry: BufferGeometry;

  beforeEach(() => {
    uniqueGeometry = new BufferGeometry();
  });

  it('revision 更新取消旧材料请求并丢弃旧结果', async () => {
    const first = deferred<ArrayBuffer>();
    let stlCall = 0;
    const stlSignals: AbortSignal[] = [];
    const deps = fakeDependencies({
      firstStl: first.promise,
      manifestProvider: call => manifest(call + 2, [mesh(1)]),
    });
    deps.fetchStl.mockImplementation(async (_request: PreviewStlRequest, signal: AbortSignal) => {
      stlCall += 1;
      stlSignals.push(signal);
      if (stlCall === 1) {
        return first.promise.then(bytes => {
          if (signal.aborted) throw new Error('aborted');
          return bytes;
        });
      }
      return new ArrayBuffer(8);
    });
    const loader = createMeshLoader(deps);
    const load1 = loader.load(3);
    // 让 load1 推进到 STL 挂起阶段，再被 load2 抢占
    await vi.waitFor(() => expect(stlSignals.length).toBe(1));
    const load2 = loader.load(4);
    first.resolve(new ArrayBuffer(8));
    await expect(load1).resolves.toMatchObject({stale: true});
    await expect(load2).resolves.toMatchObject({revision: 4, stale: false});
    expect(stlSignals.length).toBeGreaterThan(1);
    expect(stlSignals[0].aborted).toBe(true);
  });

  it('只请求 visual.visible !== false 的材料', async () => {
    const deps = fakeDependencies({
      manifestProvider: () => manifest(
        7,
        [mesh(1), mesh(2, {visual: {...mesh(2).visual, visible: false}}), mesh(3)],
      ),
    });
    const loader = createMeshLoader(deps);
    const result = await loader.load(1);
    expect(result.meshes.map(entry => entry.mesh.materialId)).toEqual([1, 3]);
    expect(deps.stlRequests().map(request => request.materialId)).toEqual([1, 3]);
  });

  it('同 revision 不重复请求 STL', async () => {
    const deps = fakeDependencies({
      manifestProvider: () => manifest(9, [mesh(1), mesh(2)]),
      sharedGeometry: uniqueGeometry,
    });
    const loader = createMeshLoader(deps);
    const first = await loader.load(1);
    expect(deps.stlRequests()).toHaveLength(2);
    const second = await loader.load(2);
    expect(second.revision).toBe(9);
    expect(second.meshes).toBe(first.meshes);
    expect(deps.stlRequests()).toHaveLength(2);
  });

  it('单材料失败返回 warnings，其他材料保留', async () => {
    const deps = fakeDependencies({
      failMaterialId: 2,
      manifestProvider: () => manifest(5, [mesh(1), mesh(2), mesh(3)]),
    });
    const loader = createMeshLoader(deps);
    const result = await loader.load(1);
    expect(result.meshes.map(entry => entry.mesh.materialId)).toEqual([1, 3]);
    expect(result.warnings).toHaveLength(1);
    expect(result.warnings[0]).toContain('2');
  });

  it('manifest 的 visual 映射到 material config', async () => {
    const deps = fakeDependencies({
      manifestProvider: () => manifest(4, [mesh(6, {
        visual: {
          materialId: 6,
          displayName: 'Oxide',
          color: [0.9, 0.8, 0.7],
          opacity: 0.55,
          metallic: 0.25,
          roughness: 0.35,
          visible: true,
        },
      })]),
    });
    const loader = createMeshLoader(deps);
    const result = await loader.load(1);
    expect(result.meshes[0].material).toEqual({
      color: [0.9, 0.8, 0.7],
      opacity: 0.55,
      metallic: 0.25,
      roughness: 0.35,
      transparent: true,
    });
  });

  it('dispose 按 object identity 去重', async () => {
    const shared = new BufferGeometry();
    const disposeSpy = vi.spyOn(shared, 'dispose');
    const deps = fakeDependencies({
      manifestProvider: () => manifest(6, [mesh(1), mesh(2)]),
      sharedGeometry: shared,
    });
    const loader = createMeshLoader(deps);
    await loader.load(1);
    loader.dispose();
    expect(disposeSpy).toHaveBeenCalledTimes(1);
  });

  it('STL 请求使用 manifest 返回的真实 revision', async () => {
    const deps = fakeDependencies({
      manifestProvider: () => manifest(11, [mesh(1)]),
    });
    const loader = createMeshLoader(deps);
    await loader.load(99);
    expect(deps.stlRequests()[0]).toMatchObject({revision: 11, mode: 'solid'});
  });
});
