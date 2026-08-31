import {Box3, Sphere, Vector3} from 'three';
import {describe, expect, it} from 'vitest';
import {calculateOrthographicFit, calculatePerspectiveFit} from './fitCamera';

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

describe('calculateOrthographicFit', () => {
  it('frustum 半高至少覆盖包围球半径，宽高比只影响半宽', () => {
    const bounds = new Box3(new Vector3(-5, -10, 2), new Vector3(5, 10, 8));
    const radius = bounds.getBoundingSphere(new Sphere()).radius;
    const fit = calculateOrthographicFit(bounds, 16 / 9);
    expect(fit.target.toArray()).toEqual([0, 0, 5]);
    expect(fit.halfHeight).toBeGreaterThanOrEqual(radius);
    expect(fit.halfWidth).toBeCloseTo(fit.halfHeight * (16 / 9), 6);
  });

  it('窄视口由宽度约束主导：半高放大、半宽恰好覆盖半径', () => {
    const bounds = new Box3(new Vector3(-5, -10, 2), new Vector3(5, 10, 8));
    const radius = bounds.getBoundingSphere(new Sphere()).radius;
    const wide = calculateOrthographicFit(bounds, 2);
    const portrait = calculateOrthographicFit(bounds, 0.5);
    // aspect=2 时高度约束主导：halfHeight == radius；aspect=0.5 时 halfHeight 翻倍
    expect(wide.halfHeight).toBeCloseTo(radius, 6);
    expect(wide.halfWidth).toBeCloseTo(radius * 2, 6);
    expect(portrait.halfHeight).toBeCloseTo(radius * 2, 6);
    expect(portrait.halfWidth).toBeCloseTo(radius, 6);
  });

  it('near 为负、far 更远且数值有限（正交相机可置于模型任意侧）', () => {
    const bounds = new Box3(new Vector3(-5, -10, 2), new Vector3(5, 10, 8));
    const fit = calculateOrthographicFit(bounds, 16 / 9);
    expect(fit.near).toBeLessThan(0);
    expect(Number.isFinite(fit.far)).toBe(true);
    expect(fit.far).toBeGreaterThan(fit.near);
    expect(Number.isFinite(fit.distance)).toBe(true);
    expect(fit.distance).toBeGreaterThan(0);
  });

  it('空 bounds 与退化 bounds 返回有限默认 frustum', () => {
    const empty = calculateOrthographicFit(new Box3(), 16 / 9);
    expect(empty.target.toArray()).toEqual([0, 0, 0]);
    expect(empty.halfWidth).toBeGreaterThan(0);
    expect(empty.halfHeight).toBeGreaterThan(0);
    expect(empty.far).toBeGreaterThan(empty.near);
    const point = new Box3(new Vector3(1, 2, 3), new Vector3(1, 2, 3));
    const degenerate = calculateOrthographicFit(point, 1);
    expect(degenerate.target.toArray()).toEqual([1, 2, 3]);
    expect(Number.isFinite(degenerate.halfHeight)).toBe(true);
    expect(degenerate.far).toBeGreaterThan(degenerate.near);
  });

  it('非法 aspect 退回安全默认值', () => {
    const bounds = new Box3(new Vector3(-1, -1, -1), new Vector3(1, 1, 1));
    const fit = calculateOrthographicFit(bounds, Number.NaN);
    expect(Number.isFinite(fit.halfHeight)).toBe(true);
    expect(fit.halfWidth).toBeCloseTo(fit.halfHeight, 6);
    expect(fit.far).toBeGreaterThan(fit.near);
  });
});
