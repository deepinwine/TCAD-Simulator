import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {TcadApiError} from './api/client';
import type {InitView, RuntimeStatus, StepView, TcadApi} from './api/types';
import {App} from './App';

function step(index: number, overrides: Partial<StepView> = {}): StepView {
  return {
    index,
    name: `step-${index}`,
    instanceName: `Step ${index}`,
    group: '',
    loop: '',
    enabled: true,
    params: {},
    parameterSpecs: [],
    runtimeStatus: 'ready',
    ...overrides,
  };
}

function initView(recipe: StepView[] = [step(0)]): InitView {
  return {
    recipe,
    model: {gridShape: [8, 8, 8], voxelSizeNm: 10},
    factories: ['deposit'],
    materials: [],
    uiState: {},
  };
}

function apiStub(overrides: Partial<TcadApi> = {}): TcadApi {
  return {
    init: vi.fn(async () => initView()),
    setStep: vi.fn(async request => ({
      step: step(request.index),
      statuses: ['ready'] as RuntimeStatus[],
      warnings: [],
    })),
    runStep: vi.fn(async () => ({})),
    runTo: vi.fn(async () => ({})),
    runAll: vi.fn(async () => ({})),
    undo: vi.fn(async () => ({applied: false, log: []})),
    redo: vi.fn(async () => ({applied: false, log: []})),
    importRecipe: vi.fn(async () => ({model: {gridShape: [8, 8, 8] as [number, number, number], voxelSizeNm: 10}, recipe: [], currentRecipe: {name: '', id: ''}, log: []})),
    newRecipe: vi.fn(async () => ({model: {gridShape: [8, 8, 8] as [number, number, number], voxelSizeNm: 10}, recipe: [], currentRecipe: {name: '', id: ''}, log: []})),
    saveRecipe: vi.fn(async () => ({saved: true})),
    exportRecipe: vi.fn(async () => new Blob(['{}'])),
    loadRecipe: vi.fn(async () => ({model: {gridShape: [8, 8, 8] as [number, number, number], voxelSizeNm: 10}, recipe: [], currentRecipe: {name: '', id: ''}, log: []})),
    getTimeline: vi.fn(async () => ({items: [], current: -1})),
    restoreTimeline: vi.fn(async () => ({
      timeline: {items: [], current: -1},
      model: initView().model,
      recipe: [],
      log: [],
    })),
    getPreviewManifest: vi.fn(async () => ({revision: 1, meshes: []})),
    getMaterialStl: vi.fn(async () => new ArrayBuffer(0)),
    ...overrides,
  };
}

describe('App shell', () => {
  it('bootstrap 后同时显示三栏与 Timeline', async () => {
    render(<App api={apiStub()} />);

    expect(await screen.findByRole('region', {name: 'Process Flow'})).toBeVisible();
    expect(screen.getByRole('region', {name: 'Parameters'})).toBeVisible();
    expect(screen.getByRole('region', {name: '3D Viewer'})).toBeVisible();
    expect(screen.getByRole('navigation', {name: 'Process Timeline'})).toBeVisible();
    expect(document.querySelector('canvas')).toBeNull();
  });

  it('点击步骤只改变本地选择且不发 API 请求', async () => {
    const api = apiStub({
      init: vi.fn(async () => initView([
        step(0, {instanceName: 'Substrate', name: 'Initialize Wafer'}),
        step(1, {
          instanceName: 'Gate Oxidation',
          name: 'Oxidation',
          params: {temperature: 950},
        }),
      ])),
    });
    render(<App api={api} />);

    const oxidation = await screen.findByRole('option', {name: /Gate Oxidation/});
    fireEvent.click(oxidation);

    expect(oxidation).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('region', {name: 'Parameters'})).toHaveTextContent('Gate Oxidation');
    expect(api.init).toHaveBeenCalledTimes(1);
    expect(api.setStep).not.toHaveBeenCalled();
    expect(api.runStep).not.toHaveBeenCalled();
    expect(api.runTo).not.toHaveBeenCalled();
    expect(api.runAll).not.toHaveBeenCalled();
    expect(api.getTimeline).toHaveBeenCalledTimes(1);
    expect(api.restoreTimeline).not.toHaveBeenCalled();
    expect(api.getPreviewManifest).not.toHaveBeenCalled();
    expect(api.getMaterialStl).not.toHaveBeenCalled();
  });

  it('fatal init 只显示安全错误并可重试恢复', async () => {
    const init = vi.fn()
      .mockRejectedValueOnce(new TcadApiError('secret-database-path', {
        status: 500,
        code: 'internal_error',
        details: {secret: '/private/server/path'},
      }))
      .mockResolvedValueOnce(initView());
    render(<App api={apiStub({init})} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('无法加载 TCAD Session');
    expect(document.body).not.toHaveTextContent('secret-database-path');
    expect(document.body).not.toHaveTextContent('/private/server/path');

    fireEvent.click(screen.getByRole('button', {name: '重试连接'}));
    expect(await screen.findByRole('region', {name: 'Process Flow'})).toBeVisible();
    expect(init).toHaveBeenCalledTimes(2);
  });

  it('Parameters 折叠按钮同步 class、hidden 与 aria-expanded', async () => {
    render(<App api={apiStub()} />);
    const button = await screen.findByRole('button', {name: '折叠 Parameters'});
    const panel = screen.getByRole('region', {name: 'Parameters'});
    const workspace = panel.parentElement;

    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(button).toHaveAttribute('aria-controls', panel.id);
    fireEvent.click(button);

    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveAccessibleName('展开 Parameters');
    expect(panel).toHaveAttribute('hidden');
    expect(workspace).toHaveClass('parameters-collapsed');
  });

  it('booting 阶段提供可访问 loading 状态', () => {
    const pending = new Promise<InitView>(() => undefined);
    render(<App api={apiStub({init: vi.fn(() => pending)})} />);

    expect(screen.getByRole('status')).toHaveTextContent('正在连接');
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('bootstrap 状态不会因重渲染而重复请求', async () => {
    const api = apiStub();
    const view = render(<App api={api} />);
    await screen.findByRole('region', {name: 'Process Flow'});

    view.rerender(<App api={api} />);
    await waitFor(() => expect(api.init).toHaveBeenCalledTimes(1));
  });

  it('run 网络失败后可重新同步服务端权威状态', async () => {
    const api = apiStub({
      runAll: vi.fn(async () => {
        throw new TcadApiError('无法连接 TCAD 服务。', {
          status: 0,
          code: 'network_error',
        });
      }),
    });
    const stubViewerRuntime = () => ({
      backend: 'WebGL2',
      mount: () => {},
      setStandardView: () => {},
      setProjection: () => {},
      setClipping: () => {},
      setMaterialDisplay: () => {},
      pickAt: () => null,
      setMeasureMarkers: () => {},
      fit: () => {},
      loadMeshes: async () => ({warnings: [], materials: []}),
      dispose: () => {},
    });
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('region', {name: 'Process Flow'});
    const getTimelineCallsBefore = (api.getTimeline as ReturnType<typeof vi.fn>).mock.calls.length;

    fireEvent.click(screen.getByRole('button', {name: '运行全部'}));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('无法连接 TCAD 服务');

    fireEvent.click(screen.getByRole('button', {name: '重新同步'}));
    await waitFor(() => {
      expect((api.getTimeline as ReturnType<typeof vi.fn>).mock.calls.length)
        .toBeGreaterThan(getTimelineCallsBefore);
    });
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });
});
