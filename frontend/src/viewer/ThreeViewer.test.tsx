import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import type {TcadApi} from '../api/types';
import {ThreeViewer, type ViewerRuntime, type StandardView} from './ThreeViewer';

function fakeViewerRuntime(overrides: Partial<ViewerRuntime> = {}) {
  const calls = {
    apiCalls: 0,
    loadedTokens: [] as number[],
    standardViews: [] as StandardView[],
    fits: 0,
    disposed: 0,
    projections: [] as Array<'perspective' | 'orthographic'>,
  };
  const runtime: ViewerRuntime = {
    backend: 'WebGL2',
    mount: vi.fn(),
    setStandardView: vi.fn((view: StandardView) => {
      calls.standardViews.push(view);
    }),
    setProjection: vi.fn((mode: 'perspective' | 'orthographic') => {
      calls.projections.push(mode);
    }),
    fit: vi.fn(() => {
      calls.fits += 1;
    }),
    loadMeshes: vi.fn(async (token: number) => {
      calls.apiCalls += 1;
      calls.loadedTokens.push(token);
      return {warnings: []};
    }),
    dispose: vi.fn(() => {
      calls.disposed += 1;
    }),
    ...overrides,
  };
  return {runtime, calls};
}

const apiStub = {} as TcadApi;

afterEach(() => cleanup());

describe('ThreeViewer', () => {
  it('相机操作不产生 API 请求，unmount 释放 runtime', async () => {
    const {runtime, calls} = fakeViewerRuntime();
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={7}
        runtimeFactory={() => runtime}
      />,
    );

    await screen.findByText('WebGL2');
    const callsBeforeCamera = calls.apiCalls;
    fireEvent.click(screen.getByRole('button', {name: 'ISO 视图'}));
    fireEvent.click(screen.getByRole('button', {name: '适应窗口'}));
    expect(calls.apiCalls).toBe(callsBeforeCamera);
    expect(calls.standardViews).toEqual(['iso']);
    expect(calls.fits).toBe(1);

    cleanup();
    expect(calls.disposed).toBe(1);
    expect(runtime.dispose).toHaveBeenCalledTimes(1);
  });

  it('六个标准视图按钮触发对应视图', async () => {
    const shared = fakeViewerRuntime();
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={1}
        runtimeFactory={() => shared.runtime}
      />,
    );
    await screen.findByText('WebGL2');
    const names = ['顶视图', '底视图', '前视图', '后视图', '左视图', '右视图'] as const;
    const views: StandardView[] = ['top', 'bottom', 'front', 'back', 'left', 'right'];
    names.forEach(name => {
      fireEvent.click(screen.getByRole('button', {name}));
    });
    expect(shared.calls.standardViews).toEqual(views);
  });

  it('透视/正交切换翻转 aria-pressed 并调用 setProjection', async () => {
    const shared = fakeViewerRuntime();
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={3}
        runtimeFactory={() => shared.runtime}
      />,
    );
    await screen.findByText('WebGL2');
    const toggle = screen.getByRole('button', {name: '正交视图'});
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    const callsBefore = shared.calls.apiCalls;

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(shared.calls.projections).toEqual(['orthographic']);
    expect(shared.calls.apiCalls).toBe(callsBefore);

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(shared.calls.projections).toEqual(['orthographic', 'perspective']);
    expect(shared.calls.apiCalls).toBe(callsBefore);
  });

  it('refreshToken 变化触发网格加载，材料失败可重试', async () => {
    let shouldFail = true;
    const shared = fakeViewerRuntime({
      loadMeshes: vi.fn(async (token: number) => {
        shared.calls.apiCalls += 1;
        shared.calls.loadedTokens.push(token);
        if (shouldFail) throw new Error('材料 mat-2 下载失败');
        return {warnings: []};
      }),
    });
    const {rerender} = render(
      <ThreeViewer
        api={apiStub}
        refreshToken={5}
        runtimeFactory={() => shared.runtime}
      />,
    );
    await waitFor(() => expect(shared.calls.loadedTokens).toEqual([5]));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('材料 mat-2 下载失败');

    shouldFail = false;
    fireEvent.click(screen.getByRole('button', {name: '重试加载几何'}));
    await waitFor(() => expect(shared.calls.loadedTokens).toEqual([5, 5]));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());

    rerender(
      <ThreeViewer
        api={apiStub}
        refreshToken={6}
        runtimeFactory={() => shared.runtime}
      />,
    );
    await waitFor(() => expect(shared.calls.loadedTokens).toEqual([5, 5, 6]));
  });

  it('WebGL 创建失败显示真实原因且不渲染假 3D', async () => {
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={1}
        runtimeFactory={() => {
          throw new Error('WebGL2 上下文创建失败：canvas 被占用');
        }}
      />,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('WebGL2 上下文创建失败：canvas 被占用');
    expect(document.querySelector('canvas')).toBeNull();
    expect(screen.queryByText('WebGL2')).toBeNull();
    expect(screen.getByRole('button', {name: '正交视图'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'ISO 视图'})).toBeDisabled();
  });
});
