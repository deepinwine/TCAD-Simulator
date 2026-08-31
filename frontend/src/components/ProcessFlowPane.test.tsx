import {act, fireEvent, render, screen} from '@testing-library/react';
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

  it('只保留一个 Tab 入口并用方向键、Home 和 End 移动焦点而不选择', () => {
    const onSelect = vi.fn();
    render(
      <>
        <ProcessFlowPane
          recipe={[step(0, 'ready'), step(1, 'ready'), step(2, 'ready')]}
          selectedStepIndex={1}
          onSelect={onSelect}
        />
        <button type="button">下一个控件</button>
      </>,
    );
    const options = screen.getAllByRole('option');

    expect(options.map(option => option.tabIndex)).toEqual([-1, 0, -1]);
    options[1].focus();
    fireEvent.keyDown(options[1], {key: 'ArrowDown'});
    expect(options[2]).toHaveFocus();
    expect(options.map(option => option.tabIndex)).toEqual([-1, -1, 0]);
    fireEvent.keyDown(options[2], {key: 'ArrowDown'});
    expect(options[2]).toHaveFocus();
    expect(options.map(option => option.tabIndex)).toEqual([-1, -1, 0]);
    fireEvent.keyDown(options[2], {key: 'ArrowUp'});
    expect(options[1]).toHaveFocus();
    expect(options.map(option => option.tabIndex)).toEqual([-1, 0, -1]);
    fireEvent.keyDown(options[1], {key: 'Home'});
    expect(options[0]).toHaveFocus();
    expect(options.map(option => option.tabIndex)).toEqual([0, -1, -1]);
    fireEvent.keyDown(options[0], {key: 'End'});
    expect(options[2]).toHaveFocus();
    expect(options.map(option => option.tabIndex)).toEqual([-1, -1, 0]);
    act(() => screen.getByRole('button', {name: '下一个控件'}).focus());
    expect(screen.getByRole('button', {name: '下一个控件'})).toHaveFocus();
    expect(options.filter(option => option.tabIndex === 0)).toEqual([options[2]]);
    act(() => options.find(option => option.tabIndex === 0)?.focus());
    expect(options[2]).toHaveFocus();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('Enter、Space 和鼠标可选择禁用工艺步骤且不会重复触发', () => {
    const onSelect = vi.fn();
    const disabledStep = {...step(1, 'dirty'), enabled: false};
    render(
      <ProcessFlowPane
        recipe={[step(0, 'ready'), disabledStep]}
        selectedStepIndex={0}
        onSelect={onSelect}
      />,
    );
    const disabled = screen.getByRole('option', {name: /Instance 1/});

    expect(disabled).not.toHaveAttribute('aria-disabled');
    expect(disabled).toHaveTextContent('已禁用');
    act(() => disabled.focus());
    expect(disabled).toHaveFocus();
    expect(disabled).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(disabled, {key: 'Enter'});
    expect(onSelect).toHaveBeenNthCalledWith(1, 1);
    fireEvent.keyDown(disabled, {key: ' '});
    expect(onSelect).toHaveBeenNthCalledWith(2, 1);
    fireEvent.click(disabled);
    expect(onSelect).toHaveBeenNthCalledWith(3, 1);
    expect(onSelect).toHaveBeenCalledTimes(3);
  });

  it('外部 selection 与 recipe 更新会安全重置 roving Tab 点', () => {
    const onSelect = vi.fn();
    const recipe = [step(0, 'ready'), step(1, 'ready'), step(2, 'ready')];
    const view = render(
      <ProcessFlowPane recipe={recipe} selectedStepIndex={0} onSelect={onSelect} />,
    );

    fireEvent.click(screen.getAllByRole('option')[2]);
    expect(onSelect).toHaveBeenCalledWith(2);
    view.rerender(
      <ProcessFlowPane recipe={recipe} selectedStepIndex={2} onSelect={onSelect} />,
    );
    expect(screen.getAllByRole('option').map(option => option.tabIndex)).toEqual([-1, -1, 0]);

    view.rerender(
      <ProcessFlowPane recipe={[step(5, 'ready')]} selectedStepIndex={2} onSelect={onSelect} />,
    );
    expect(screen.getByRole('option')).toHaveAttribute('tabindex', '0');
  });
});
