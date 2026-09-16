export type Dimension = 'length' | 'time' | 'angle' | 'rate';
export type DisplayUnit = 'nm' | 'µm' | 'ms' | 's' | 'min' | '°' | 'rad' | 'nm/s' | 'µm/min';
export const canonicalUnits: Record<Dimension, string> = {length: 'nm', time: 's', angle: 'degree', rate: 'nm/s'};
export class UnitConversionError extends Error {
  constructor(readonly code: 'invalid_unit' | 'nonfinite_value' | 'invalid_decimals') {
    super(code);
    this.name = 'UnitConversionError';
  }
}
const factors: Record<Dimension, Partial<Record<DisplayUnit, number>>> = {
  length: {nm: 1, 'µm': 1000},
  time: {ms: 0.001, s: 1, min: 60},
  angle: {'°': 1, rad: 180 / Math.PI},
  rate: {'nm/s': 1, 'µm/min': 1000 / 60},
};

function finite(value: number): number {
  if (!Number.isFinite(value)) throw new UnitConversionError('nonfinite_value');
  return value;
}

function factor(dimension: Dimension, unit: DisplayUnit): number {
  const value = Object.hasOwn(factors, dimension) ? factors[dimension][unit] : undefined;
  if (typeof value !== 'number') throw new UnitConversionError('invalid_unit');
  return value;
}

export function toCanonical(value: number, dimension: Dimension, unit: DisplayUnit): number {
  return finite(finite(value) * factor(dimension, unit));
}
export function fromCanonical(value: number, dimension: Dimension, unit: DisplayUnit): number {
  return finite(finite(value) / factor(dimension, unit));
}
export function formatDisplayValue(value: number, decimals: number): string {
  finite(value);
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 100) {
    throw new UnitConversionError('invalid_decimals');
  }
  return value.toFixed(decimals);
}
