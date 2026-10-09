import {Raycaster, Vector2, Vector3, type Camera, type Mesh, type Intersection, type Material} from 'three';

export interface PickCandidate {
  mesh: Mesh;
  matId: number;
  name: string;
  resolveHit?: (intersection: Intersection) => {matId: number; name: string} | null;
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
  for (const hit of hits) {
    const candidate = candidates.find(item => item.mesh === hit.object);
    if (!candidate) continue;
    let visible = true;
    for (let object: import('three').Object3D | null = candidate.mesh; object; object = object.parent) {
      if (!object.visible) {visible = false; break;}
    }
    if (!visible) continue;
    const material = candidate.mesh.material as Material;
    if (material.opacity <= 0 || material.clippingPlanes?.some(plane => plane.distanceToPoint(hit.point) < -1e-8)) continue;
    const resolved = candidate.resolveHit ? candidate.resolveHit(hit) : candidate;
    if (resolved === null) continue;
    return {matId:resolved.matId,name:resolved.name,point:hit.point.clone()};
  }
  return null;
}

/** 测量两点间的欧氏距离（世界坐标，单位 µm）。 */
export function measureDistance(a: Vector3, b: Vector3): number {
  return a.distanceTo(b);
}
