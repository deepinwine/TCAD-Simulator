import {expect, it} from 'vitest';
import {updateProjectRecipe, validDomain} from './projectSettingsModel';
const blob = {name: 'project', metadata: {keep: true}, domain: {grid_shape: [32, 32, 64], voxel_size_nm: 5, threads: 4}, steps_full: [{name: 'Initialize Wafer', instance_name: 'SOI', enabled: false, group: 'start', loop: '2', params: {material: 'Si', thickness_nm: 200, wafer_type: 'Bulk'}, params_raw: {material: 'Si', thickness_nm: 200, wafer_type: 'SOI', box_thickness_nm: 20}}, {name: 'Structure Etch', group: 'custom', params_raw: {depth_nm: 30}}]};
it('updates full export atomically preserving all step metadata and raw SOI fields', () => {
  const updated = updateProjectRecipe(blob, [64, 32, 64], 10, {material: 'Poly', thickness_nm: 300});
  expect(updated.domain).toEqual({grid_shape: [64, 32, 64], voxel_size_nm: 10, threads: 4});
  expect(updated.steps_full[0]).toEqual({...blob.steps_full[0], params: {material: 'Poly', thickness_nm: 300, wafer_type: 'SOI', box_thickness_nm: 20}, params_raw: {material: 'Poly', thickness_nm: 300, wafer_type: 'SOI', box_thickness_nm: 20}});
  expect(updated.steps_full[1]).toEqual(blob.steps_full[1]);
  expect(updated.metadata).toEqual(blob.metadata); expect(blob.domain.voxel_size_nm).toBe(5);
});
it('rejects missing initializer and unsafe grids before mutation', () => {
  expect(() => updateProjectRecipe({...blob, steps_full: [blob.steps_full[1]]}, [32, 32, 64], 5, {})).toThrow();
  for (const grid of [[1e308, 32, 64], [32.5, 32, 64], [0, 32, 64], [1024, 1024, 1024]]) expect(validDomain(grid, 5)).toBe(false);
  expect(validDomain([64, 64, 128], 5)).toBe(true); expect(validDomain([64, 64, 128], Infinity)).toBe(false);
});
