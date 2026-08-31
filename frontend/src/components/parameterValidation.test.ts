import {describe, expect, it} from 'vitest';
import type {ParameterSpecView} from '../api/types';
import {validateParameter} from './parameterValidation';

function spec(overrides: Partial<ParameterSpecView>): ParameterSpecView {
  return {
    key: 'value',
    label: 'Value',
    type: 'string',
    ...overrides,
  };
}

describe('validateParameter', () => {
  it.each([
    ['float', '1.25e2', 125],
    ['float', '1.', 1],
    ['int', '12', 12],
    ['int', '12.0', 12],
  ])('%s 将合法数值文本转换为 number', (type, raw, value) => {
    expect(validateParameter(spec({type}), raw)).toEqual({ok: true, value});
  });

  it.each(['', '   ', 'NaN', 'Infinity', '-Infinity'])('数值拒绝空值或非有限值 %j', raw => {
    expect(validateParameter(spec({type: 'float'}), raw)).toEqual({
      ok: false,
      message: '请输入有限数值',
    });
  });

  it('整数拒绝带小数部分的值', () => {
    expect(validateParameter(spec({type: 'int'}), '12.5')).toEqual({
      ok: false,
      message: '请输入整数',
    });
  });

  it('整数拒绝超过 JavaScript 安全范围的值', () => {
    expect(validateParameter(spec({type: 'int'}), '9007199254740992')).toEqual({
      ok: false,
      message: '请输入安全整数',
    });
  });

  it('minimum 和 maximum 为包含边界', () => {
    const bounded = spec({type: 'float', minimum: 0, maximum: 500});
    expect(validateParameter(bounded, '0')).toEqual({ok: true, value: 0});
    expect(validateParameter(bounded, '500')).toEqual({ok: true, value: 500});
    expect(validateParameter(bounded, '-0.1')).toEqual({
      ok: false,
      message: '必须大于或等于 0',
    });
    expect(validateParameter(bounded, '500.1')).toEqual({
      ok: false,
      message: '必须小于或等于 500',
    });
  });

  it.each([
    [true, true],
    [false, false],
    ['true', true],
    ['false', false],
    ['1', true],
    ['0', false],
  ])('bool 解析明确的布尔值 %j', (raw, value) => {
    expect(validateParameter(spec({type: 'bool'}), raw)).toEqual({ok: true, value});
  });

  it.each(['', 'yes', 1, null])('bool 拒绝不明确的值 %j', raw => {
    expect(validateParameter(spec({type: 'bool'}), raw)).toEqual({
      ok: false,
      message: '请选择开启或关闭',
    });
  });

  it('choice 只接受 choices 中严格相等的真实 primitive/null 值', () => {
    const choice = spec({
      type: 'choice',
      choices: [['1', '字符串'], [1, '数字'], [true, '布尔'], [null, '空值']],
    });
    expect(validateParameter(choice, '1')).toEqual({ok: true, value: '1'});
    expect(validateParameter(choice, 1)).toEqual({ok: true, value: 1});
    expect(validateParameter(choice, true)).toEqual({ok: true, value: true});
    expect(validateParameter(choice, null)).toEqual({ok: true, value: null});
    expect(validateParameter(choice, 'true')).toEqual({
      ok: false,
      message: '请选择列表中的有效选项',
    });
  });

  it('enum 使用与 choice 相同的严格枚举语义', () => {
    const enumSpec = spec({type: 'enum', choices: [[0, 'Off'], [1, 'On']]});
    expect(validateParameter(enumSpec, 1)).toEqual({ok: true, value: 1});
    expect(validateParameter(enumSpec, '1')).toEqual({
      ok: false,
      message: '请选择列表中的有效选项',
    });
  });

  it.each(['string', 'text', 'future-type'])('%s 保留文本及空串，不擅自 trim', type => {
    expect(validateParameter(spec({type}), '')).toEqual({ok: true, value: ''});
    expect(validateParameter(spec({type}), '  keep  ')).toEqual({
      ok: true,
      value: '  keep  ',
    });
  });
});
