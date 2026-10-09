import {Box3, Plane, Vector3, type Group, type Mesh, type Material} from 'three';

export type ClipAxis = 'x' | 'y' | 'z';

export interface ClipAxisState {
  enabled: boolean;
  /** 归一化位置 0..1，映射到包围盒该轴的 min..max。 */
  position: number;
}

export interface ClipState {
  x: ClipAxisState;
  y: ClipAxisState;
  z: ClipAxisState;
}

export const clipStateAllOff = (): ClipState => ({
  x: {enabled: false, position: 0},
  y: {enabled: false, position: 0},
  z: {enabled: false, position: 0},
});

const AXIS_INDEX: Record<ClipAxis, 0 | 1 | 2> = {x: 0, y: 1, z: 2};

/** 归一化位置（钳制到 [0,1]）映射为包围盒该轴的世界坐标。 */
export function worldClipPosition(bounds: Box3, axis: ClipAxis, position: number): number {
  const index = AXIS_INDEX[axis];
  const min = bounds.min.getComponent(index);
  const max = bounds.max.getComponent(index);
  const clamped = Number.isFinite(position)
    ? Math.min(1, Math.max(0, position))
    : 0;
  return min + (max - min) * clamped;
}

function axisPlane(axis: ClipAxis, worldPosition: number): Plane {
  // 保留平面负侧（axis <= worldPosition）的几何：法向沿轴负向，常数即世界位置。
  const normal = new Vector3(0, 0, 0).setComponent(AXIS_INDEX[axis], -1);
  return new Plane(normal, worldPosition);
}

/**
 * 由裁剪状态与包围盒推导 three.js 裁剪平面。
 *
 * 空包围盒无从映射世界坐标，返回空数组（相当于不裁剪）。
 * 空体积返回空数组并由 applyClipState 隐藏组；完全保留的轴不生成平面。
 * 内部平面顺序固定为启用的 X、Y、Z。
 */
export function deriveClipPlanes(state: ClipState, bounds: Box3): Plane[] {
  if (bounds.isEmpty() || isClipVolumeEmpty(state)) return [];
  const planes: Plane[] = [];
  for (const axis of ['x', 'y', 'z'] as const) {
    const axisState = state[axis];
    if (!axisState.enabled || axisState.position >= 1) continue;
    planes.push(axisPlane(axis, worldClipPosition(bounds, axis, axisState.position)));
  }
  return planes;
}

/** 任一启用轴位于 min 时，负侧没有保留体积；不以共面 plane 模拟空集。 */
export function isClipVolumeEmpty(state: ClipState): boolean {
  return (['x','y','z'] as const).some(axis => state[axis].enabled
    && (!Number.isFinite(state[axis].position) || state[axis].position <= 0));
}

/** 整组控制空体积，同时保留各材料的用户可见性。 */
export function applyClipState(group: Group, state: ClipState, bounds: Box3): Plane[] {
  group.visible = !isClipVolumeEmpty(state);
  const planes = deriveClipPlanes(state,bounds);
  for (const child of group.children) {
    const material = (child as Mesh).material as Material | null;
    if (!material) continue;
    const previous = material.clippingPlanes?.length ?? 0;
    material.clippingPlanes = planes.length ? planes : null;
    if (previous !== planes.length) material.needsUpdate = true;
  }
  return planes;
}
