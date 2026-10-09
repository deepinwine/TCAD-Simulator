import {Box3, Group, Mesh, MeshBasicMaterial, PlaneGeometry, DataTexture, RGBAFormat, UnsignedByteType, NearestFilter, DoubleSide, LinearSRGBColorSpace} from 'three';
import type {ModelSummaryView, RgbColor, MaterialSliceView} from '../api/types';
import {worldClipPosition, deriveClipPlanes, type ClipAxis, type ClipState} from './clipping';
import type {PickCandidate} from './picking';

export interface SectionColor {
  color: RgbColor;
  opacity: number;
  visible: boolean;
  name?: string;
}

/** STL marching-cubes samples are centred on i*voxel, with domain edges at -.5 and n-.5. */
export function sectionPlacement(model: ModelSummaryView, bounds: Box3, axis: ClipAxis, position: number) {
  const a = {x: 0, y: 1, z: 2}[axis];
  const [u, v] = axis === 'x' ? [1, 2] : axis === 'y' ? [0, 2] : [0, 1];
  const voxel = model.voxelSizeNm / 1000;
  const world = worldClipPosition(bounds, axis, position);
  const cellCoordinate = world / voxel + .5;
  const nearest = Math.round(cellCoordinate);
  // Exact cell interfaces expose the retained negative side. Snap only within
  // a few double-precision ULPs, never across a meaningful fraction of a voxel.
  const snapped = Math.abs(cellCoordinate - nearest) <= Number.EPSILON * Math.max(1, Math.abs(cellCoordinate)) * 8
    ? nearest : cellCoordinate;
  const index = Math.ceil(snapped) - 1;
  const shape = [model.gridShape[v], model.gridShape[u]] as const;
  const center = model.gridShape.map(n => (n - 1) * voxel / 2);
  center[a] = world;
  return {
    axis, world, shape, center,
    size: [shape[1] * voxel, shape[0] * voxel] as const,
    index: Math.min(model.gridShape[a] - 1, Math.max(0, index)),
    indexMax: model.gridShape[a] - 1,
    inside: index >= 0 && index < model.gridShape[a],
  };
}

export function sectionPixels(data: Uint16Array, materials: ReadonlyMap<number, SectionColor>) {
  const rgba = new Uint8Array(data.length * 4);
  const unknown = new Set<number>();
  data.forEach((id, i) => {
    if (id === 0) return;
    const material = materials.get(id);
    if (material?.visible === false) return;
    if (!material) unknown.add(id);
    const color = material?.color ?? [160 / 255, 160 / 255, 160 / 255];
    for (let channel = 0; channel < 3; channel++) rgba[i * 4 + channel] = Math.round(color[channel] * 255);
    rgba[i * 4 + 3] = Math.round((material?.opacity ?? 1) * 255);
  });
  return {rgba, unknownIds: [...unknown]};
}

export interface SectionInput {
  model: ModelSummaryView | null;
  revision: number;
  bounds: Box3;
  clip: ClipState;
  materials: ReadonlyMap<number, SectionColor>;
}

export function createMaterialSections(
  group: Group,
  fetchSlice: (request: {axis: ClipAxis; index: number}, signal: AbortSignal) => Promise<MaterialSliceView>,
  verifyRevision?: (revision: number, signal: AbortSignal) => Promise<boolean>,
  textureLimit: () => number = () => 4096,
) {
  let generation = 0;
  let controller: AbortController | null = null;
  let disposed = false;
  let candidates: PickCandidate[] = [];
  let cacheKey = '';
  const cache = new Map<ClipAxis, MaterialSliceView>();
  const clear = () => {
    candidates = [];
    for (const child of group.children.slice()) {
      const mesh = child as Mesh<PlaneGeometry, MeshBasicMaterial>;
      mesh.material.map?.dispose();
      mesh.material.dispose();
      mesh.geometry.dispose();
      group.remove(mesh);
    }
  };
  return {
    async update(input: SectionInput) {
      const current = ++generation;
      controller?.abort();
      clear();
      controller = new AbortController();
      const signal = controller.signal;
      if (disposed || !input.model || input.bounds.isEmpty()) return [] as number[];
      const key = `${input.revision}:${input.model.gridShape.join(',')}:${input.model.voxelSizeNm}`;
      if (key !== cacheKey) {
        cache.clear();
        cacheKey = key;
      }
      const placements = (['x', 'y', 'z'] as const)
        .filter(axis => input.clip[axis].enabled)
        .map(axis => sectionPlacement(input.model!, input.bounds, axis, input.clip[axis].position))
        .filter(p => p.inside);
      try {
        if (placements.some(p => p.shape.some(n => n > Math.min(4096, textureLimit()))
          || p.shape[0] * p.shape[1] > 16_777_216)) {
          throw new Error('Slice exceeds renderer texture budget');
        }
        let fetched = false;
        const slices = await Promise.all(placements.map(p => {
          const existing = cache.get(p.axis);
          if (existing?.index === p.index) return existing;
          fetched = true;
          return fetchSlice({axis: p.axis, index: p.index}, signal);
        }));
        if (disposed || current !== generation || signal.aborted) return [];
        if (fetched && verifyRevision && !await verifyRevision(input.revision, signal)) {
          throw new Error('Slice model revision changed; reload geometry');
        }
        if (disposed || current !== generation || signal.aborted) return [];
        const unknown = new Set<number>();
        slices.forEach((slice, i) => {
          const p = placements[i];
          if (slice.axis !== p.axis || slice.index !== p.index || slice.indexMax !== p.indexMax
            || slice.shape[0] !== p.shape[0] || slice.shape[1] !== p.shape[1]
            || slice.data.length !== p.shape[0] * p.shape[1]) {
            throw new Error('Slice does not match model domain');
          }
          cache.set(p.axis, slice);
        });
        slices.forEach((slice, i) => {
          const p = placements[i];
          const pixels = sectionPixels(slice.data, input.materials);
          pixels.unknownIds.forEach(id => unknown.add(id));
          const texture = new DataTexture(pixels.rgba, p.shape[1], p.shape[0], RGBAFormat, UnsignedByteType);
          texture.minFilter = texture.magFilter = NearestFilter;
          // Match the linear RGB components used by the existing STL materials.
          texture.colorSpace = LinearSRGBColorSpace;
          texture.needsUpdate = true;
          const material = new MeshBasicMaterial({
            map: texture, transparent: true, alphaTest: 1 / 255, side: DoubleSide, depthWrite: true,
          });
          material.clippingPlanes = deriveClipPlanes({
            ...input.clip, [p.axis]: {...input.clip[p.axis], enabled: false},
          }, input.bounds);
          const mesh = new Mesh(new PlaneGeometry(...p.size), material);
          // Plane UV u/v follows worker columns/rows: X=(Y,Z), Y=(X,Z), Z=(X,Y).
          if (p.axis === 'x') mesh.rotation.set(Math.PI / 2, Math.PI / 2, 0);
          if (p.axis === 'y') mesh.rotation.x = Math.PI / 2;
          mesh.position.set(p.center[0], p.center[1], p.center[2]);
          group.add(mesh);
          candidates.push({mesh, matId: 0, name: 'section', resolveHit: hit => {
            if (!hit.uv) return null;
            const col = Math.min(p.shape[1] - 1, Math.max(0, Math.floor(hit.uv.x * p.shape[1])));
            const row = Math.min(p.shape[0] - 1, Math.max(0, Math.floor(hit.uv.y * p.shape[0])));
            const pixel = row * p.shape[1] + col;
            if (pixels.rgba[pixel * 4 + 3] < 1) return null;
            const matId = slice.data[pixel];
            return {matId, name: input.materials.get(matId)?.name ?? String(matId)};
          }});
        });
        group.updateMatrixWorld(true);
        return [...unknown];
      } catch (error) {
        if (disposed || current !== generation || signal.aborted) return [];
        controller?.abort();
        cache.clear();
        clear();
        throw error;
      }
    },
    pickCandidates() {return candidates;},
    dispose() {
      disposed = true;
      generation++;
      controller?.abort();
      cache.clear();
      clear();
    },
  };
}
