import type {ParameterChoiceValue, ParameterSpecView} from '../api/types';

export type ParameterValidationResult =
  | {ok: true; value: unknown}
  | {ok: false; messageKey: ParameterValidationMessageKey};

export type ParameterValidationMessageKey =
  | 'validation.finite'
  | 'validation.integer'
  | 'validation.safeInteger'
  | 'validation.minimum'
  | 'validation.maximum'
  | 'validation.boolean'
  | 'validation.choice';

const decimalNumberPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

function validateNumber(
  spec: ParameterSpecView,
  raw: unknown,
  integer: boolean,
): ParameterValidationResult {
  const text = typeof raw === 'number' ? String(raw) : typeof raw === 'string' ? raw.trim() : '';
  if (text === '' || !decimalNumberPattern.test(text)) {
    return {ok: false, messageKey: 'validation.finite'};
  }
  const value = Number(text);
  if (!Number.isFinite(value)) return {ok: false, messageKey: 'validation.finite'};
  if (integer && !Number.isInteger(value)) return {ok: false, messageKey: 'validation.integer'};
  if (integer && !Number.isSafeInteger(value)) {
    return {ok: false, messageKey: 'validation.safeInteger'};
  }
  if (spec.minimum !== undefined && value < spec.minimum) {
    return {ok: false, messageKey: 'validation.minimum'};
  }
  if (spec.maximum !== undefined && value > spec.maximum) {
    return {ok: false, messageKey: 'validation.maximum'};
  }
  return {ok: true, value};
}

function validateBoolean(raw: unknown): ParameterValidationResult {
  if (typeof raw === 'boolean') return {ok: true, value: raw};
  if (typeof raw === 'string') {
    const value = raw.trim().toLowerCase();
    if (value === 'true' || value === '1') return {ok: true, value: true};
    if (value === 'false' || value === '0') return {ok: true, value: false};
  }
  return {ok: false, messageKey: 'validation.boolean'};
}

function validateChoice(spec: ParameterSpecView, raw: unknown): ParameterValidationResult {
  const match = spec.choices?.find(([value]) => Object.is(value, raw));
  return match === undefined
    ? {ok: false, messageKey: 'validation.choice'}
    : {ok: true, value: match[0] satisfies ParameterChoiceValue};
}

export function validateParameter(
  spec: ParameterSpecView,
  raw: unknown,
): ParameterValidationResult {
  switch (spec.type) {
    case 'float':
      return validateNumber(spec, raw, false);
    case 'int':
    case 'integer':
      return validateNumber(spec, raw, true);
    case 'bool':
    case 'boolean':
      return validateBoolean(raw);
    case 'choice':
    case 'enum':
      return validateChoice(spec, raw);
    default:
      return {ok: true, value: typeof raw === 'string' ? raw : String(raw ?? '')};
  }
}
