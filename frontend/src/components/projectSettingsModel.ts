export const MAX_PROJECT_VOXELS = 128 ** 3;
export function validDomain(grid: readonly number[], voxel: number): boolean {
  return grid.length === 3 && grid.every(value => Number.isSafeInteger(value) && value > 0 && Number.isFinite(value * voxel))
    && grid.reduce((product, value) => product * value, 1) <= MAX_PROJECT_VOXELS && Number.isFinite(voxel) && voxel > 0;
}
export function updateProjectRecipe<T extends Record<string, unknown>>(blob: T, grid: readonly number[], voxel: number, params: Record<string, unknown>): T {
  if (!validDomain(grid, voxel)) throw new Error('Invalid domain');
  const next = structuredClone(blob);
  const steps = next.steps_full;
  if (!Array.isArray(steps) || !['Structure Wafer', 'Initialize Wafer'].includes(steps[0]?.name)) throw new Error('Missing initializer');
  const initial = steps[0] as Record<string, unknown>;
  const previous = initial.params_raw ?? initial.params;
  const merged = {...(previous as Record<string, unknown>), ...params};
  initial.params = merged;
  initial.params_raw = {...merged};
  const domain = {...(next.domain as Record<string, unknown>), grid_shape: [...grid], voxel_size_nm: voxel};
  return {...next, domain};
}
