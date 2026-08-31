import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import type {RuntimeStatus, StepView} from '../api/types';
import {ProcessFlowPane} from './ProcessFlowPane';

function step(index: number, status: RuntimeStatus, params: Record<string, unknown> = {}): StepView {
  return {
    index,
    name: `Process ${index}`,
    instanceName: `Instance ${index}`,
    group: '',
    loop: '',
    enabled: true,
    params,
    parameterSpecs: [],
    runtimeStatus: status,
  };
}

describe('ProcessFlowPane', () => {
  it('使用 listbox/option 表达单选并显示所有状态文字', () => {
    const onSelect = vi.fn();
    const recipe = (['ready', 'dirty', 'running', 'done', 'error'] as RuntimeStatus[])
      .map((status, index) => step(index, status));
    render(<ProcessFlowPane recipe={recipe} selectedStepIndex={0} onSelect={onSelect} />);

    expect(screen.getByRole('listbox', {name: 'Process Flow'})).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(5);
    expect(screen.getByLabelText('状态：就绪 Ready')).toBeVisible();
    expect(screen.getByLabelText('状态：已修改 Dirty')).toBeVisible();
    expect(screen.getByLabelText('状态：运行中 Running')).toBeVisible();
    expect(screen.getByLabelText('状态：完成 Done')).toBeVisible();
    expect(screen.getByLabelText('状态：错误 Error')).toBeVisible();

    fireEvent.click(screen.getByRole('option', {name: /Instance 4/}));
    expect(onSelect).toHaveBeenCalledWith(4);
  });

  it('参数摘要紧凑且不会渲染 object Object 或无限长文本', () => {
    const veryLong = 'x'.repeat(400);
    render(
      <ProcessFlowPane
        recipe={[step(0, 'ready', {
          material: {name: 'SiO2', metadata: {private: veryLong}},
          values: [1, 2, 3, 4, 5],
          description: veryLong,
        })]}
        selectedStepIndex={0}
        onSelect={() => undefined}
      />,
    );

    const option = screen.getByRole('option');
    expect(option).not.toHaveTextContent('[object Object]');
    expect(option.textContent?.length).toBeLessThan(220);
  });

  it('空配方显示明确空态', () => {
    render(<ProcessFlowPane recipe={[]} selectedStepIndex={null} onSelect={() => undefined} />);
    expect(screen.getByText('当前配方没有工艺步骤')).toBeVisible();
  });
});
