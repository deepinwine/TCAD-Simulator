import {Raycaster, Vector2, Vector3, type Camera, type Mesh} from 'three';

export interface PickCandidate {
  mesh: Mesh;
  matId: number;
  name: string;
}

export interface PickHit {
  matId: number;
  name: string;
  point: Vector3;
}

/**
 * 以归一化设备坐标（-1..1）对候选网格做射线拾取，返回最近命中。
 *
 * 纯 three 数学（无 WebGL 依赖），可在 jsdom 中直接测试。
 */
export function pickAtNormalizedCoords(
  candidates: ReadonlyArray<PickCandidate>,
  camera: Camera,
  ndcX: number,
  ndcY: number,
): PickHit | null {
  if (candidates.length === 0) return null;
  const raycaster = new Raycaster();
  raycaster.setFromCamera(new Vector2(ndcX, ndcY), camera);
  const meshes = candidates.map(candidate => candidate.mesh);
  const hits = raycaster.intersectObjects(meshes, false);
  const first = hits[0];
  if (first === undefined) return null;
  const candidate = candidates.find(item => item.mesh === first.object);
  if (candidate === undefined) return null;
  return {matId: candidate.matId, name: candidate.name, point: first.point.clone()};
}

/** 测量两点间的欧氏距离（世界坐标，单位 µm）。 */
export function measureDistance(a: Vector3, b: Vector3): number {
  return a.distanceTo(b);
}
