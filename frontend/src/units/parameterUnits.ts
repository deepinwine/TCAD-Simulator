import type {ParameterSpecView} from '../api/types';
import {canonicalUnits, toCanonical, type Dimension, type DisplayUnit} from './units';
export function conversionSpec(spec: ParameterSpecView): {dimension: Dimension; units: DisplayUnit[]; preferred: DisplayUnit} | null {
  if (!['float', 'int', 'integer'].includes(spec.type) || !spec.dimension || !spec.canonicalUnit || !spec.displayUnits?.length) return null;
  const dimension = spec.dimension as Dimension;
  if (!Object.hasOwn(canonicalUnits, dimension) || canonicalUnits[dimension] !== spec.canonicalUnit) return null;
  const units = spec.displayUnits as DisplayUnit[];
  const canonicalDisplay = spec.canonicalUnit === 'degree' ? '°' : spec.canonicalUnit;
  try {
    for (const unit of units) toCanonical(0, dimension, unit);
    return {dimension, units, preferred: units.includes(canonicalDisplay as DisplayUnit) ? canonicalDisplay as DisplayUnit : units[0]};
  } catch { return null; }
}
