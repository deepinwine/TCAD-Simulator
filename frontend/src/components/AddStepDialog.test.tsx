import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import type {StepView} from '../api/types';
import {AddStepDialog} from './AddStepDialog';
const template: StepView = {index: 0, name: 'Structure Deposit', instanceName: 'Structure Deposit', group: '', loop: '', enabled: true, runtimeStatus: 'ready', params: {thickness_nm: 35, metadata: {source: 'default'}}, parameterSpecs: [{key: 'thickness_nm', label: 'Thickness', type: 'float', minimum: 0, dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm'], units: 'nm'}, {key: 'metadata', label: 'Metadata', type: 'json'}]};
describe('创建表单', () => {
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
