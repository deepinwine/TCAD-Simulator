import {Box3, Vector3, Group, Mesh, MeshStandardMaterial} from 'three';
import {describe, expect, it} from 'vitest';
import {clipStateAllOff, deriveClipPlanes, worldClipPosition, type ClipState} from './clipping';
import * as clipping from './clipping';

const bounds = new Box3(new Vector3(-10, 0, 5), new Vector3(10, 20, 15));

const stateWith = (partial: Partial<ClipState>): ClipState => ({
  ...clipStateAllOff(),
  ...partial,
});

describe('deriveClipPlanes', () => {
  it('全部关闭时返回空数组', () => {
    expect(deriveClipPlanes(clipStateAllOff(), bounds)).toEqual([]);
  });

  it('X 启用：法向沿 -X，常数等于归一化位置映射的世界坐标', () => {
    const planes = deriveClipPlanes(
      stateWith({x: {enabled: true, position: .75}}),
      bounds,
    );
    expect(planes).toHaveLength(1);
    expect(planes[0].normal.toArray()).toEqual([-1, 0, 0]);
    expect(planes[0].constant).toBeCloseTo(5, 6);
  });

  it('Y 启用 0.5：常数映射到中点；Z 启用 0：空体积不生成共面 plane', () => {
    const [yPlane] = deriveClipPlanes(
      stateWith({y: {enabled: true, position: 0.5}}),
      bounds,
    );
    expect(yPlane.normal.toArray()).toEqual([0, -1, 0]);
    expect(yPlane.constant).toBeCloseTo(10, 6);
    const zPlanes = deriveClipPlanes(
      stateWith({z: {enabled: true, position: 0}}),
      bounds,
    );
    expect(zPlanes).toEqual([]);
  });

  it('多轴启用按 X、Y、Z 顺序返回多个平面', () => {
    const planes = deriveClipPlanes(
      stateWith({
        x: {enabled: true, position: 0.25},
        z: {enabled: true, position: 0.75},
      }),
      bounds,
    );
    expect(planes).toHaveLength(2);
    expect(planes[0].normal.toArray()).toEqual([-1, 0, 0]);
    expect(planes[1].normal.toArray()).toEqual([0, 0, -1]);
    expect(planes[0].constant).toBeCloseTo(-5, 6);
    expect(planes[1].constant).toBeCloseTo(12.5, 6);
  });

  it('归一化位置越界被钳制到 [0, 1]', () => {
    const below = deriveClipPlanes(
      stateWith({x: {enabled: true, position: -0.5}}),
      bounds,
    );
    expect(below).toEqual([]);
    const above = deriveClipPlanes(
      stateWith({x: {enabled: true, position: 1.5}}),
      bounds,
    );
    expect(above).toEqual([]);
  });

  it('空 bounds 返回空数组（无从映射世界坐标）', () => {
    const planes = deriveClipPlanes(
      stateWith({x: {enabled: true, position: 0.5}}),
      new Box3(),
    );
    expect(planes).toEqual([]);
  });
});

it.each(['x','y','z'] as const)('uses exact empty/full endpoint visibility for %s and preserves child material display', axis => {
  expect(clipping).toHaveProperty('applyClipState');
  const group = new Group();
  const visible = new Mesh(undefined,new MeshStandardMaterial());
  const hidden = new Mesh(undefined,new MeshStandardMaterial()); hidden.visible = false;
  group.add(visible,hidden);
  const apply = (position:number) => clipping.applyClipState(group,stateWith({[axis]:{enabled:true,position}}),bounds);
  apply(0);
  expect(group.visible).toBe(false);
  expect(visible.visible).toBe(true);
  expect(hidden.visible).toBe(false);
  apply(1);
  expect(group.visible).toBe(true);
  expect((visible.material as MeshStandardMaterial).clippingPlanes).toBeNull();
  expect(hidden.visible).toBe(false);
  apply(1e-10);
  expect(group.visible).toBe(true);
  expect((visible.material as MeshStandardMaterial).clippingPlanes).toHaveLength(1);
  expect(deriveClipPlanes(stateWith({x:{enabled:true,position:1},y:{enabled:true,position:.5}}),bounds)).toHaveLength(1);
});

describe('worldClipPosition', () => {
  it('0/0.5/1 映射 min/中点/max', () => {
    expect(worldClipPosition(bounds, 'x', 0)).toBeCloseTo(-10, 6);
    expect(worldClipPosition(bounds, 'y', 0.5)).toBeCloseTo(10, 6);
    expect(worldClipPosition(bounds, 'z', 1)).toBeCloseTo(15, 6);
  });
});
