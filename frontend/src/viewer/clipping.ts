import {Box3, Plane, Vector3} from 'three';

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
 * 平面顺序固定为启用的 X、Y、Z。
 */
export function deriveClipPlanes(state: ClipState, bounds: Box3): Plane[] {
  if (bounds.isEmpty()) return [];
  const planes: Plane[] = [];
  for (const axis of ['x', 'y', 'z'] as const) {
    const axisState = state[axis];
    if (!axisState.enabled) continue;
    planes.push(axisPlane(axis, worldClipPosition(bounds, axis, axisState.position)));
  }
  return planes;
}
