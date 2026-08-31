import {Box3, Sphere, Vector3} from 'three';

export interface PerspectiveFit {
  target: Vector3;
  distance: number;
  near: number;
  far: number;
}

const defaultFit = (): PerspectiveFit => ({
  target: new Vector3(),
  distance: 10,
  near: 0.1,
  far: 1000,
});

function isFiniteVector(vector: Vector3 | undefined): boolean {
  return vector !== undefined
    && Number.isFinite(vector.x)
    && Number.isFinite(vector.y)
    && Number.isFinite(vector.z);
}

/**
 * 计算完整容纳 bounds 的透视相机位姿。
 *
 * 距离按包围球与有效视场角（垂直 fov 与水平 fov 中更严格者）推导，
 * 保证模型在任意视口比例下都完整可见。
 */
export function calculatePerspectiveFit(
  bounds: Box3,
  fovDeg: number,
  aspect: number,
): PerspectiveFit {
  const fov = Number.isFinite(fovDeg) && fovDeg > 0 && fovDeg < 180 ? fovDeg : 45;
  const safeAspect = Number.isFinite(aspect) && aspect > 0 ? aspect : 1;

  if (bounds.isEmpty() || !isFiniteVector(bounds.min) || !isFiniteVector(bounds.max)) {
    return defaultFit();
  }

  const sphere = bounds.getBoundingSphere(new Sphere());
  if (
    !isFiniteVector(sphere.center)
    || !Number.isFinite(sphere.radius)
    || sphere.radius < 0
  ) {
    return defaultFit();
  }

  const target = sphere.center.clone();
  const radius = Math.max(sphere.radius, 1e-6);
  const fovY = (fov * Math.PI) / 180;
  const fovX = 2 * Math.atan(Math.tan(fovY / 2) * safeAspect);
  const effectiveFov = Math.min(fovY, fovX);
  const distance = radius / Math.sin(effectiveFov / 2);
  const near = Math.max((distance - radius) * 0.05, 1e-3);
  const far = Math.max((distance + radius) * 4, near * 2);
  return {target, distance, near, far};
}
