import {Box3, Vector3} from 'three';
import {describe, expect, it} from 'vitest';
import {calculatePerspectiveFit} from './fitCamera';

describe('calculatePerspectiveFit', () => {
  it('ISO pose 以 bounds 中心为 target 并完整容纳模型', () => {
    const bounds = new Box3(new Vector3(-5, -10, 2), new Vector3(5, 10, 8));
    const fit = calculatePerspectiveFit(bounds, 40, 16 / 9);
    expect(fit.target.toArray()).toEqual([0, 0, 5]);
    expect(fit.distance).toBeGreaterThan(20);
    expect(Number.isFinite(fit.near)).toBe(true);
    expect(fit.far).toBeGreaterThan(fit.near);
  });

  it('空 bounds 返回有限默认姿态', () => {
    const fit = calculatePerspectiveFit(new Box3(), 40, 16 / 9);
    expect(fit.target.toArray()).toEqual([0, 0, 0]);
    expect(Number.isFinite(fit.distance)).toBe(true);
    expect(fit.far).toBeGreaterThan(fit.near);
    expect(fit.near).toBeGreaterThan(0);
  });

  it('退化 bounds（单点）仍满足 near < far 且数值有限', () => {
    const point = new Box3(new Vector3(1, 2, 3), new Vector3(1, 2, 3));
    const fit = calculatePerspectiveFit(point, 40, 16 / 9);
    expect(fit.target.toArray()).toEqual([1, 2, 3]);
    expect(Number.isFinite(fit.distance)).toBe(true);
    expect(fit.far).toBeGreaterThan(fit.near);
  });

  it('非有限坐标按空 bounds 处理', () => {
    const bad = new Box3(
      new Vector3(Number.NEGATIVE_INFINITY, 0, 0),
      new Vector3(Number.POSITIVE_INFINITY, 1, 1),
    );
    const fit = calculatePerspectiveFit(bad, 40, 16 / 9);
    expect(fit.target.toArray()).toEqual([0, 0, 0]);
  });

  it('窄视口使用水平与垂直 fov 中更严格者，1×1 容器数值有限', () => {
    const bounds = new Box3(new Vector3(-5, -10, 2), new Vector3(5, 10, 8));
    const wide = calculatePerspectiveFit(bounds, 40, 16 / 9);
    const square = calculatePerspectiveFit(bounds, 40, 1);
    const portrait = calculatePerspectiveFit(bounds, 40, 0.5);
    // 竖屏水平 fov 更小，容纳同一模型需要更远的距离
    expect(portrait.distance).toBeGreaterThan(wide.distance);
    // 1×1 容器恰好 fovX == fovY，结果与宽屏（垂直约束）一致且有限
    expect(square.distance).toBeCloseTo(wide.distance, 6);
    expect(Number.isFinite(square.near)).toBe(true);
    expect(square.far).toBeGreaterThan(square.near);
  });

  it('非法 fov 或 aspect 退回安全默认值', () => {
    const bounds = new Box3(new Vector3(-1, -1, -1), new Vector3(1, 1, 1));
    const fit = calculatePerspectiveFit(bounds, Number.NaN, 0);
    expect(Number.isFinite(fit.distance)).toBe(true);
    expect(fit.far).toBeGreaterThan(fit.near);
  });
});
