import type {DisplayManifestView, StepView} from '../api/types';
import {isInitializer} from '../components/processCatalog';

export type VisibilityReason = 'loading' | 'unavailable' | 'unknown' | 'empty' | 'operation';
const NON_ENTITY_OPERATIONS = new Set([
  'Structure Pattern', 'Structure Doping', 'Structure Etch',
  'Structure Planarize', 'Structure CMP', 'Structure Strip',
]);

export function stepVisibilityReason(
  step: StepView,
  manifest: DisplayManifestView | null | undefined,
  ready: boolean,
): VisibilityReason | null {
  if (isInitializer(step) || !step.name.startsWith('Structure ')
    || NON_ENTITY_OPERATIONS.has(step.name)) return 'operation';
  if (!ready) return 'loading';
  if (!manifest?.available) return 'unavailable';
  if (!step.stepId) return 'unknown';
  const entity = manifest.stepEntities.find(item => item.stepId === step.stepId);
  if (!entity || entity.unavailableReason === 'unknown_provenance') return 'unknown';
  if (!entity.hideable || !entity.ownerId || !entity.voxelCount) return 'empty';
  if (manifest.ownerStepIds[String(entity.ownerId)] !== step.stepId) return 'unknown';
  return manifest.groups.some(group => group.ownerId === entity.ownerId && group.stepId === step.stepId) ? null : 'empty';
}
export function validHiddenSteps(
  ids: readonly string[], recipe: readonly StepView[],
  manifest: DisplayManifestView | null, ready: boolean,
): string[] {
  return [...new Set(ids)].filter(id => recipe.some(step => step.stepId === id && stepVisibilityReason(step, manifest, ready) === null));
}
export function sourceVisible(
  ownerId: number | undefined, stepId: string | null | undefined,
  hidden: ReadonlySet<string>,
): boolean {
  return !ownerId || !stepId || !hidden.has(stepId);
}
