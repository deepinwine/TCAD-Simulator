import {describe, expect, it} from 'vitest';
import {toCanonical, fromCanonical, formatDisplayValue, UnitConversionError, type Dimension, type DisplayUnit} from './units';

describe('canonical units', () => {
  it.each<[Dimension, DisplayUnit, number, number]>([
    ['length', 'µm', 1000, 1], ['time', 'min', 120, 2],
    ['angle', 'rad', 180, Math.PI], ['rate', 'µm/min', 10, 0.6],
    ['time', 'ms', 1, 1000],
  ])('converts %s using %s without drift', (dimension, unit, canonical, display) => {
    expect(fromCanonical(canonical, dimension, unit)).toBeCloseTo(display, 12);
    expect(toCanonical(display, dimension, unit)).toBeCloseTo(canonical, 12);
    let value = canonical;
    for (let i = 0; i < 100; i++) value = toCanonical(fromCanonical(value, dimension, unit), dimension, unit);
    expect(Math.abs(value - canonical)).toBeLessThan(1e-10);
  });
  it('reports structured errors for nonfinite numbers and invalid units', () => {
    for (const value of [NaN, Infinity, -Infinity]) {
      expect(() => toCanonical(value, 'length', 'nm')).toThrow(UnitConversionError);
      expect(() => fromCanonical(value, 'length', 'nm')).toThrow(UnitConversionError);
    }
    for (const unit of ['s', 'bogus'] as DisplayUnit[]) {
      expect(() => toCanonical(1, 'length', unit)).toThrow(expect.objectContaining({code: 'invalid_unit'}));
    }
    expect(() => toCanonical(1, 'bogus' as Dimension, 'nm')).toThrow(UnitConversionError);
    expect(formatDisplayValue(1.23456, 3)).toBe('1.235');
    expect(() => formatDisplayValue(NaN, 2)).toThrow(UnitConversionError);
  });
});
