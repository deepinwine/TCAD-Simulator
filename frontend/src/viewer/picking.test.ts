import {BufferGeometry, Float32BufferAttribute, Mesh, MeshStandardMaterial, PerspectiveCamera, Vector3} from 'three';
import {describe, expect, it} from 'vitest';
import {measureDistance, pickAtNormalizedCoords} from './picking';

function triangleMesh(): Mesh {
  const geometry = new BufferGeometry();
  geometry.setAttribute(
    'position',
    new Float32BufferAttribute([-1, -1, 0, 1, -1, 0, 0, 1, 0], 3),
  );
  return new Mesh(geometry, new MeshStandardMaterial());
}

function frontCamera(): PerspectiveCamera {
  const camera = new PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();
  return camera;
}

describe('pickAtNormalizedCoords', () => {
  it('视线穿过三角形时命中并返回世界坐标', () => {
    const mesh = triangleMesh();
    const hit = pickAtNormalizedCoords(
      [{mesh, matId: 1, name: 'Silicon'}],
      frontCamera(),
      0,
      0,
    );
    expect(hit).not.toBeNull();
    expect(hit!.matId).toBe(1);
    expect(hit!.name).toBe('Silicon');
    expect(hit!.point.z).toBeCloseTo(0, 6);
  });

  it('视线未命中任何网格时返回 null', () => {
    const mesh = triangleMesh();
    const hit = pickAtNormalizedCoords(
      [{mesh, matId: 1, name: 'Silicon'}],
      frontCamera(),
      0.95,
      0.95,
    );
    expect(hit).toBeNull();
  });

  it('多候选时取最近命中并映射回材料信息', () => {
    const near = triangleMesh();
    const far = triangleMesh();
    far.position.set(0, 0, -3);
    far.updateMatrixWorld();
    const hit = pickAtNormalizedCoords(
      [
        {mesh: far, matId: 2, name: 'SiO2'},
        {mesh: near, matId: 1, name: 'Silicon'},
      ],
      frontCamera(),
      0,
      0,
    );
    expect(hit!.matId).toBe(1);
    expect(hit!.point.z).toBeCloseTo(0, 6);
  });
});

describe('measureDistance', () => {
  it('两点距离按欧氏距离计算', () => {
    expect(
      measureDistance(new Vector3(0, 0, 0), new Vector3(3, 4, 0)),
    ).toBeCloseTo(5, 6);
    expect(
      measureDistance(new Vector3(1, 1, 1), new Vector3(1, 1, 1)),
    ).toBe(0);
  });
});
