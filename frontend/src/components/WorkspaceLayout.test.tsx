import {useEffect} from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {WorkspaceLayout} from './WorkspaceLayout';
describe('三栏工作区', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('左右分隔键盘调宽限制范围，保留中间viewer生命周期及草稿', () => {
    const mounted = vi.fn(); const unmounted = vi.fn();
    function Viewer() {useEffect(() => {mounted(); return unmounted;}, []); return <div>3D</div>;}
    render(<WorkspaceLayout left={<div>步骤</div>} viewer={<Viewer />} parameters={<input defaultValue="draft" aria-label="参数" />} collapsed={false} />);
    const [left, right] = screen.getAllByRole('separator');
    expect(left).toHaveAttribute('aria-valuenow', '280'); expect(right).toHaveAttribute('aria-valuenow', '320');
    fireEvent.keyDown(left, {key: 'ArrowRight'}); expect(left).toHaveAttribute('aria-valuenow', '300');
    fireEvent.keyDown(right, {key: 'ArrowLeft'}); expect(right).toHaveAttribute('aria-valuenow', '340');
    for (let i = 0; i < 30; i++) fireEvent.keyDown(left, {key: 'ArrowRight'});
    expect(left).toHaveAttribute('aria-valuenow', '420'); expect(mounted).toHaveBeenCalledTimes(1); expect(unmounted).not.toHaveBeenCalled();
    expect(screen.getByLabelText('参数')).toHaveValue('draft');
  });
  it('使用pointer capture拖动并在释放后停止调宽', () => {
    class PointerEvent extends MouseEvent {pointerId: number; constructor(type: string, options: PointerEventInit) {super(type, options); this.pointerId = options.pointerId ?? 0;}}
    vi.stubGlobal('PointerEvent', PointerEvent);
    render(<WorkspaceLayout left="步骤" viewer="3D" parameters="参数" collapsed={false} />);
    const left = screen.getAllByRole('separator')[0];
    left.setPointerCapture = vi.fn(); left.releasePointerCapture = vi.fn();
    fireEvent.pointerDown(left, {pointerId: 7, clientX: 280});
    fireEvent.pointerMove(left, {pointerId: 7, clientX: 350});
    expect(left.setPointerCapture).toHaveBeenCalledWith(7); expect(left).toHaveAttribute('aria-valuenow', '350');
    fireEvent.pointerUp(left, {pointerId: 7});
    fireEvent.pointerMove(left, {pointerId: 7, clientX: 400});
    expect(left).toHaveAttribute('aria-valuenow', '350');
  });
});
