import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {Vector3} from 'three';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {TcadApiError} from '../api/client';
import type {TcadApi} from '../api/types';
import {I18nProvider} from '../i18n/I18nContext';
import {ThreeViewer, type ViewerRuntime, type StandardView} from './ThreeViewer';
import type {PickHit} from './picking';

function fakeViewerRuntime(overrides: Partial<ViewerRuntime> = {}) {
  const calls = {
    apiCalls: 0,
    loadedTokens: [] as number[],
    standardViews: [] as StandardView[],
    fits: 0,
    disposed: 0,
    projections: [] as Array<'perspective' | 'orthographic'>,
    materialDisplay: [] as Array<[number, {visible?: boolean; opacity?: number}]>,
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
    setClipping: vi.fn(),
    setMaterialDisplay: vi.fn((matId: number, display: {visible?: boolean; opacity?: number}) => {
      calls.materialDisplay.push([matId, display]);
    }),
    pickAt: vi.fn((): PickHit | null => null),
    setMeasureMarkers: vi.fn(),
    fit: vi.fn(() => {
      calls.fits += 1;
    }),
    loadMeshes: vi.fn(async (token: number) => {
      calls.apiCalls += 1;
      calls.loadedTokens.push(token);
      return {warnings: [], materials: []};
    }),
    dispose: vi.fn(() => {
      calls.disposed += 1;
    }),
    ...overrides,
  };
  return {runtime, calls};
}

const apiStub = {} as TcadApi;

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('ThreeViewer', () => {
  it('binds authoritative model context without remounting and exposes section failures for retry', async () => {
    const setSectionContext = vi.fn();
    const {runtime} = fakeViewerRuntime({setSectionContext});
    const factory = () => runtime;
    const model = {gridShape: [2,3,4] as const, voxelSizeNm: 100};
    const view = render(<ThreeViewer api={apiStub} model={model} refreshToken={1} runtimeFactory={factory} />);
    await waitFor(() => expect(setSectionContext).toHaveBeenCalled());
    const callback = setSectionContext.mock.calls.at(-1)![1];
    callback(new Error('section failed'));
    expect(await screen.findByRole('alert')).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: '重试加载几何'}));
    view.rerender(<ThreeViewer api={apiStub} model={{...model, voxelSizeNm: 200}} refreshToken={2} runtimeFactory={factory} />);
    await waitFor(() => expect(setSectionContext.mock.calls.at(-1)![0].voxelSizeNm).toBe(200));
    expect(runtime.mount).toHaveBeenCalledTimes(1);
  });
  it('部分加载失败仅显示本地化摘要，重试成功后更新材料列表并清除错误', async () => {
    const loadMeshes = vi.fn()
      .mockResolvedValueOnce({warnings: ['SiO2: Authorization: Bearer secret-token'], materials: [{matId: 1, name: 'Si', visible: true, opacity: 1}]})
      .mockResolvedValueOnce({warnings: [], materials: [{matId: 2, name: 'SiO2', visible: true, opacity: 1}]});
    const {runtime} = fakeViewerRuntime({loadMeshes});
    render(<ThreeViewer api={apiStub} refreshToken={1} runtimeFactory={() => runtime} />);
    expect(await screen.findByText('部分材料加载失败')).toBeVisible();
    expect(screen.queryByText(/Authorization: Bearer/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: '重试加载几何'}));
    expect(await screen.findByText('SiO2')).toBeVisible();
    expect(screen.queryByText('部分材料加载失败')).not.toBeInTheDocument();
  });

  it('网格加载的已知 API 错误码使用本地化正文而不显示原始消息', async () => {
    const {runtime} = fakeViewerRuntime({
      loadMeshes: vi.fn(async () => {
        throw new TcadApiError('Authorization: Bearer secret-token', {
          status: 404,
          code: 'missing_mesh',
        });
      }),
    });
    render(<ThreeViewer api={apiStub} refreshToken={1} runtimeFactory={() => runtime} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('缺少所需的几何网格。');
    expect(alert).not.toHaveTextContent('Authorization: Bearer');
  });

  it('初始化异常保留 API code 的本地化边界且不显示敏感原文', async () => {
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={1}
        runtimeFactory={() => {
          throw new TcadApiError('Authorization: Bearer secret-token', {
            status: 404,
            code: 'missing_mesh',
          });
        }}
      />,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('缺少所需的几何网格。');
    expect(alert).not.toHaveTextContent('Authorization: Bearer');
  });

  it('普通加载异常显示安全的未知错误而非原始消息', async () => {
    const {runtime} = fakeViewerRuntime({
      loadMeshes: vi.fn(async () => {
        throw new Error('secret-database-path: /private/db');
      }),
    });
    render(<ThreeViewer api={apiStub} refreshToken={1} runtimeFactory={() => runtime} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('发生未预期的错误。');
    expect(alert).not.toHaveTextContent('secret-database-path');
  });

  it('manifest 失败保留材料列表并标示旧几何', async () => {
    const loadMeshes = vi.fn()
      .mockResolvedValueOnce({warnings: [], materials: [{matId: 1, name: 'Si', visible: true, opacity: 1}]})
      .mockRejectedValueOnce(new Error('manifest 离线'));
    const {runtime} = fakeViewerRuntime({loadMeshes});
    const factory = () => runtime;
    const view = render(<ThreeViewer api={apiStub} refreshToken={1} runtimeFactory={factory} />);
    await screen.findByText('Si');
    view.rerender(<ThreeViewer api={apiStub} refreshToken={2} runtimeFactory={factory} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('发生未预期的错误。');
    expect(screen.queryByText('manifest 离线')).not.toBeInTheDocument();
    expect(screen.getByText('Si')).toBeVisible();
    expect(screen.getByText(/仍显示上次加载的几何，可能与当前模型不同/)).toBeVisible();
  });

  it('英文下可信的 WebGL 和旧几何建议可见，但服务端内容保持隐藏', async () => {
    window.localStorage.setItem('tcad.locale.v1', 'en');
    const initView = render(
      <I18nProvider>
        <ThreeViewer
          api={apiStub}
          refreshToken={1}
          runtimeFactory={() => {
            throw new TcadApiError('Authorization: Bearer secret-token', {
              status: 404,
              code: 'missing_mesh',
              suggestion: 'server-suggestion-secret',
            });
          }}
        />
      </I18nProvider>,
    );
    const initAlert = await screen.findByRole('alert');
    expect(initAlert).toHaveTextContent('Check WebGL2 support in the browser and try again.');
    expect(initAlert).not.toHaveTextContent('Authorization: Bearer');
    expect(initAlert).not.toHaveTextContent('server-suggestion-secret');

    initView.unmount();
    const loadMeshes = vi.fn()
      .mockResolvedValueOnce({warnings: [], materials: [{matId: 1, name: 'Si', visible: true, opacity: 1}]})
      .mockRejectedValueOnce(new Error('secret-database-path'));
    const {runtime} = fakeViewerRuntime({loadMeshes});
    const view = render(
      <I18nProvider>
        <ThreeViewer api={apiStub} refreshToken={1} runtimeFactory={() => runtime} />
      </I18nProvider>,
    );
    await screen.findByText('Si');
    view.rerender(
      <I18nProvider>
        <ThreeViewer api={apiStub} refreshToken={2} runtimeFactory={() => runtime} />
      </I18nProvider>,
    );
    const loadAlert = await screen.findByRole('alert');
    expect(loadAlert).toHaveTextContent('The previously loaded geometry is still displayed and may not match the current model. Try again.');
    expect(loadAlert).not.toHaveTextContent('secret-database-path');
  });

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

  it('裁剪控件默认全关，启用与滑杆操作调用 setClipping 且不发请求', async () => {
    const shared = fakeViewerRuntime();
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={2}
        runtimeFactory={() => shared.runtime}
      />,
    );
    await screen.findByText('WebGL2');
    const slider = screen.getByRole('slider', {name: 'X 裁剪位置'});
    expect(slider).toBeDisabled();
    expect(screen.getByRole('slider', {name: 'Y 裁剪位置'})).toBeDisabled();
    expect(screen.getByRole('slider', {name: 'Z 裁剪位置'})).toBeDisabled();
    expect(shared.runtime.setClipping).not.toHaveBeenCalled();
    const callsBefore = shared.calls.apiCalls;

    fireEvent.click(screen.getByRole('checkbox', {name: '启用 X 裁剪'}));
    expect(shared.runtime.setClipping).toHaveBeenCalledTimes(1);
    expect(shared.runtime.setClipping).toHaveBeenCalledWith({
      x: {enabled: true, position: 0},
      y: {enabled: false, position: 0},
      z: {enabled: false, position: 0},
    });

    fireEvent.change(screen.getByRole('slider', {name: 'X 裁剪位置'}), {
      target: {value: '0.75'},
    });
    expect(shared.runtime.setClipping).toHaveBeenLastCalledWith({
      x: {enabled: true, position: 0.75},
      y: {enabled: false, position: 0},
      z: {enabled: false, position: 0},
    });
    expect(shared.calls.apiCalls).toBe(callsBefore);
  });

  it('加载后列出材料，显示控制调用 setMaterialDisplay 且不发请求', async () => {
    const shared = fakeViewerRuntime({
      loadMeshes: vi.fn(async (token: number) => {
        shared.calls.apiCalls += 1;
        shared.calls.loadedTokens.push(token);
        return {
          warnings: [],
          materials: [
            {matId: 1, name: 'Silicon', visible: true, opacity: 1},
            {matId: 2, name: 'Silicon Dioxide', visible: true, opacity: 0.9},
          ],
        };
      }),
    });
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={4}
        runtimeFactory={() => shared.runtime}
      />,
    );
    await screen.findByText('Silicon');
    expect(screen.getByText('Silicon Dioxide')).toBeVisible();
    const callsBefore = shared.calls.apiCalls;

    fireEvent.click(screen.getByRole('checkbox', {name: 'Silicon 可见'}));
    expect(shared.calls.materialDisplay).toEqual([[1, {visible: false, opacity: 1}]]);

    fireEvent.change(screen.getByRole('slider', {name: 'Silicon Dioxide 透明度'}), {
      target: {value: '0.3'},
    });
    expect(
      shared.calls.materialDisplay[shared.calls.materialDisplay.length - 1],
    ).toEqual([2, {visible: true, opacity: 0.3}]);
    expect(shared.calls.apiCalls).toBe(callsBefore);
  });

  it('点击命中显示选择信息，拖拽不触发，测量模式两点出距离', async () => {
    const hitA: PickHit = {matId: 1, name: 'Silicon', point: new Vector3(0, 0, 0)};
    const hitB: PickHit = {matId: 2, name: 'SiO2', point: new Vector3(0.3, 0.4, 0)};
    const pickAt = vi.fn(() => hitA);
    const shared = fakeViewerRuntime({pickAt});
    render(
      <ThreeViewer
        api={apiStub}
        refreshToken={6}
        runtimeFactory={() => shared.runtime}
      />,
    );
    await screen.findByText('WebGL2');
    const stage = document.querySelector('.viewer-stage')!;
    const callsBefore = shared.calls.apiCalls;

    // 拖拽（位移大）不触发选择
    fireEvent.pointerDown(stage, {pointerId: 1, button: 0, clientX: 400, clientY: 300});
    fireEvent.pointerUp(stage, {pointerId: 1, button: 0, clientX: 460, clientY: 340});
    expect(shared.runtime.pickAt).not.toHaveBeenCalled();

    // 单击命中 → 显示材料名
    fireEvent.pointerDown(stage, {pointerId: 2, button: 0, clientX: 400, clientY: 300});
    fireEvent.pointerUp(stage, {pointerId: 2, button: 0, clientX: 402, clientY: 302});
    expect(shared.runtime.pickAt).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Silicon/)).toBeVisible();

    // 测量模式：两次单击出距离并落标记
    fireEvent.click(screen.getByRole('button', {name: '测量模式'}));
    expect(screen.getByRole('button', {name: '测量模式'})).toHaveAttribute('aria-pressed', 'true');
    fireEvent.pointerDown(stage, {pointerId: 3, button: 0, clientX: 400, clientY: 300});
    fireEvent.pointerUp(stage, {pointerId: 3, button: 0, clientX: 400, clientY: 300});
    pickAt.mockReturnValue(hitB);
    fireEvent.pointerDown(stage, {pointerId: 4, button: 0, clientX: 500, clientY: 300});
    fireEvent.pointerUp(stage, {pointerId: 4, button: 0, clientX: 500, clientY: 300});
    expect(screen.getByText(/距离 0\.5000/)).toBeVisible();
    expect(shared.runtime.setMeasureMarkers).toHaveBeenCalled();
    expect(shared.calls.apiCalls).toBe(callsBefore);
  });

  it('refreshToken 变化触发网格加载，材料失败可重试', async () => {
    let shouldFail = true;
    const shared = fakeViewerRuntime({
      loadMeshes: vi.fn(async (token: number) => {
        shared.calls.apiCalls += 1;
        shared.calls.loadedTokens.push(token);
        if (shouldFail) throw new Error('材料 mat-2 下载失败');
        return {warnings: [], materials: []};
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
    expect(alert).toHaveTextContent('发生未预期的错误。');
    expect(alert).not.toHaveTextContent('材料 mat-2 下载失败');

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

  it('WebGL 创建失败显示安全摘要且不渲染假 3D', async () => {
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
    expect(alert).toHaveTextContent('发生未预期的错误。');
    expect(alert).not.toHaveTextContent('WebGL2 上下文创建失败');
    expect(alert).toHaveTextContent('请检查浏览器 WebGL2 支持后重试。');
    expect(document.querySelector('canvas')).toBeNull();
    expect(screen.queryByText('WebGL2')).toBeNull();
    expect(screen.getByRole('button', {name: '正交视图'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'ISO 视图'})).toBeDisabled();
    expect(screen.getByRole('checkbox', {name: '启用 X 裁剪'})).toBeDisabled();
    expect(screen.getByRole('slider', {name: 'X 裁剪位置'})).toBeDisabled();
  });
});
