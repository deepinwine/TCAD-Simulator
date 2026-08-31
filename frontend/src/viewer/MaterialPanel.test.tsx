import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {MaterialPanel} from './MaterialPanel';

afterEach(() => cleanup());

const materials = [
  {matId: 1, name: 'Silicon', visible: true, opacity: 1},
  {matId: 2, name: 'Silicon Dioxide', visible: true, opacity: 0.9},
];

describe('MaterialPanel', () => {
  it('列出材料名并按初始显示状态渲染控件', () => {
    render(
      <MaterialPanel
        materials={materials}
        display={{1: {visible: true, opacity: 1}, 2: {visible: true, opacity: 0.9}}}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText('Silicon')).toBeVisible();
    expect(screen.getByText('Silicon Dioxide')).toBeVisible();
    expect(screen.getByRole('checkbox', {name: 'Silicon 可见'})).toBeChecked();
    expect(screen.getByRole('slider', {name: 'Silicon 透明度'})).toHaveValue('1');
    expect(screen.getByRole('slider', {name: 'Silicon Dioxide 透明度'})).toHaveValue('0.9');
  });

  it('可见性开关与透明度滑杆触发 onChange', () => {
    const onChange = vi.fn();
    render(
      <MaterialPanel
        materials={materials}
        display={{1: {visible: true, opacity: 1}, 2: {visible: true, opacity: 0.9}}}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('checkbox', {name: 'Silicon 可见'}));
    expect(onChange).toHaveBeenCalledWith(1, {visible: false, opacity: 1});

    fireEvent.change(screen.getByRole('slider', {name: 'Silicon 透明度'}), {
      target: {value: '0.4'},
    });
    expect(onChange).toHaveBeenLastCalledWith(1, {visible: true, opacity: 0.4});
  });

  it('disabled 时全部控件禁用', () => {
    render(
      <MaterialPanel
        materials={materials}
        display={{1: {visible: true, opacity: 1}, 2: {visible: true, opacity: 0.9}}}
        onChange={() => {}}
        disabled
      />,
    );
    expect(screen.getByRole('checkbox', {name: 'Silicon 可见'})).toBeDisabled();
    expect(screen.getByRole('slider', {name: 'Silicon 透明度'})).toBeDisabled();
  });
});
