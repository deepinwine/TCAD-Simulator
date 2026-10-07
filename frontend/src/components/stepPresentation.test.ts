import {describe, expect, it} from 'vitest';
import type {StepView} from '../api/types';
import {presentStep} from './stepPresentation';
const step = (name: string, params: Record<string, unknown>, instanceName = name): StepView => ({index: 0, name, instanceName, params, parameterSpecs: [], group: '', loop: '', enabled: true, runtimeStatus: 'ready'});
describe('步骤含义', () => {
  it('旧刻蚀显示时间，避免暗示深度构建', () => {
    const display = presentStep(step('Etch', {material: 'Silicon', time: 30}), [], 'zh-CN');
    expect(display.title).toBe('刻蚀 · Si · 时间 30 s');
    expect(display.description).toContain('时间与速率');
  });
  it('默认沉积标题解析数字材料并展示厚度', () => {
    expect(presentStep(step('Structure Deposit', {material: 2, thickness_nm: 80}), [{id: 2, name: 'Silicon Dioxide', color: [1, 1, 1], enabled: true}], 'zh-CN').title).toBe('沉积 · SiO₂ · 80 nm');
  });
  it('刻蚀展示深度，保留用户名称及英文', () => {
    expect(presentStep(step('Structure Etch', {material: 'Silicon Dioxide', depth_nm: 40}), [], 'zh-CN').title).toBe('刻蚀 · SiO₂ · 深度 40 nm');
    expect(presentStep(step('Structure Etch', {}, 'Contact opening'), [], 'en').title).toBe('Contact opening');
    expect(presentStep(step('Structure Fill', {height_nm: 100}), [], 'en').title).toContain('Fill');
  });
});
