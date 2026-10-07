import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import type {StepView} from '../api/types';
import {AddStepDialog} from './AddStepDialog';
import {I18nProvider} from '../i18n/I18nContext';
const template: StepView = {index: 0, name: 'Structure Deposit', instanceName: 'Structure Deposit', group: '', loop: '', enabled: true, runtimeStatus: 'ready', params: {thickness_nm: 35, metadata: {source: 'default'}}, parameterSpecs: [{key: 'thickness_nm', label: 'Thickness', type: 'float', minimum: 0, dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm'], units: 'nm'}, {key: 'metadata', label: 'Metadata', type: 'json'}]};
describe('创建表单', () => {
  it('英文创建文案与单位标签使用集中目录', () => {
    window.localStorage.setItem('tcad.locale.v1', 'en');
    render(<I18nProvider><AddStepDialog template={template} busy={false} onCancel={() => {}} onConfirm={async () => {}} /></I18nProvider>);
    expect(screen.getByRole('heading', {name: /Configure step/})).toBeVisible();
    expect(screen.getByLabelText('Thickness (nm)')).toHaveValue(35);
    expect(screen.getByLabelText('Thickness unit')).toHaveValue('nm');
    expect(screen.getByRole('button', {name: 'Add step'})).toBeVisible();
    expect(screen.getByRole('button', {name: 'Cancel'})).toBeVisible();
  });
  it('有限的µm极值转换溢出呈现invalid并保留表单与输入', () => {
    const confirm = vi.fn(async () => {});
    render(<AddStepDialog template={template} busy={false} onCancel={() => {}} onConfirm={confirm} />);
    fireEvent.change(screen.getByLabelText('厚度单位'), {target: {value: 'µm'}});
    fireEvent.change(screen.getByLabelText('厚度（µm）'), {target: {value: '1e308'}});
    expect(screen.getByRole('dialog')).toBeVisible();
    expect(screen.getByLabelText('厚度（µm）')).toHaveValue(1e308);
    expect(screen.getByRole('alert')).toBeVisible();
    expect(screen.getByRole('button', {name: '确认添加'})).toBeDisabled();
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('厚度（µm）'), {target: {value: '0.035'}});
    expect(screen.getByRole('button', {name: '确认添加'})).not.toBeDisabled();
  });
  it('切换ms导致显示值溢出时保留原值与单位并禁止确认，修正后可恢复', () => {
    const confirm = vi.fn(async () => {});
    const timeTemplate: StepView = {...template, params: {duration: 1e308}, parameterSpecs: [{key: 'duration', label: 'Duration', type: 'float', maximum: 1e308, units: 's', dimension: 'time', canonicalUnit: 's', displayUnits: ['s', 'ms']}]};
    render(<AddStepDialog template={timeTemplate} busy={false} onCancel={() => {}} onConfirm={confirm} />);
    fireEvent.change(screen.getByLabelText('Duration单位'), {target: {value: 'ms'}});
    expect(screen.getByLabelText('Duration（s）')).toHaveValue(1e308);
    expect(screen.getByLabelText('Duration单位')).toHaveValue('s');
    expect(screen.getByRole('alert')).toBeVisible();
    expect(screen.getByRole('button', {name: '确认添加'})).toBeDisabled();
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Duration（s）'), {target: {value: '1'}});
    fireEvent.change(screen.getByLabelText('Duration单位'), {target: {value: 'ms'}});
    expect(screen.getByLabelText('Duration（ms）')).toHaveValue(1000);
    expect(screen.getByRole('button', {name: '确认添加'})).not.toBeDisabled();
  });
  it('弧度极值的canonical转换溢出也呈现字段错误', () => {
    const confirm = vi.fn(async () => {});
    const angleTemplate: StepView = {...template, params: {orientation: 90}, parameterSpecs: [{key: 'orientation', label: 'Orientation', type: 'float', units: '°', dimension: 'angle', canonicalUnit: 'degree', displayUnits: ['°', 'rad']}]};
    render(<AddStepDialog template={angleTemplate} busy={false} onCancel={() => {}} onConfirm={confirm} />);
    fireEvent.change(screen.getByLabelText('旋转角单位'), {target: {value: 'rad'}});
    fireEvent.change(screen.getByLabelText('旋转角（rad）'), {target: {value: '1e308'}});
    expect(screen.getByLabelText('旋转角（rad）')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', {name: '确认添加'})).toBeDisabled();
    expect(confirm).not.toHaveBeenCalled();
  });
  it('35nm转为0.035µm并提交canonical值，复杂默认字段保留', () => {
    const confirm = vi.fn(async () => {});
    render(<AddStepDialog template={template} busy={false} onCancel={() => {}} onConfirm={confirm} />);
    fireEvent.change(screen.getByLabelText('厚度单位'), {target: {value: 'µm'}});
    expect(screen.getByLabelText('厚度（µm）')).toHaveValue(0.035);
    fireEvent.click(screen.getByRole('button', {name: '确认添加'}));
    expect(confirm).toHaveBeenCalledWith({params: {thickness_nm: 35, metadata: {source: 'default'}}});
  });
  it('invalid数值和进行中请求阻止确认', () => {
    const confirm = vi.fn(async () => {});
    const view = render(<AddStepDialog template={template} busy={false} onCancel={() => {}} onConfirm={confirm} />);
    fireEvent.change(screen.getByLabelText('厚度（nm）'), {target: {value: '-1'}});
    expect(screen.getByRole('button', {name: '确认添加'})).toBeDisabled();
    expect(screen.getByRole('alert')).toBeVisible();
    view.rerender(<AddStepDialog template={template} busy onCancel={() => {}} onConfirm={confirm} />);
    expect(screen.getByLabelText('厚度（nm）')).toBeDisabled();
    expect(confirm).not.toHaveBeenCalled();
  });
});
