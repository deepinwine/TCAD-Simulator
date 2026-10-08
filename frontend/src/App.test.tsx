import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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
    addStep: vi.fn(async () => []),
    removeStep: vi.fn(async () => []),
    duplicateStep: vi.fn(async () => []),
    moveStep: vi.fn(async () => []),
    renameStep: vi.fn(async () => { throw new Error('unused'); }),
    uploadMask: vi.fn(async () => ({
      step: {} as never,
      statuses: [],
      warnings: [],
    })),
    listMaskAssets: vi.fn(async () => []),
    getMaskAsset: vi.fn(async () => { throw new Error('unused'); }),
    saveAndApplyMaskAsset: vi.fn(async () => { throw new Error('unused'); }),
    importAndApplyMaskAsset: vi.fn(async () => { throw new Error('unused'); }),
    deleteMaskAsset: vi.fn(async () => {}),
    exportMaskAsset: vi.fn(async () => new Blob()),
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

function stubViewerRuntime() {
  return {
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
  };
}

describe('App shell', () => {
  it.each([
    {mask_mode: 'Procedural', mask_asset_id: '', mask_asset_revision: 0},
    {mask_mode: 'Custom', mask_asset_id: 'previous_asset', mask_asset_revision: 1},
  ])('opens a new workbench for an Exposure without an active asset binding: $mask_mode', async params => {
    const exposure = step(0, {name: 'Mask Exposure', params});
    const api = apiStub({init: vi.fn(async () => initView([exposure]))});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    fireEvent.click(await screen.findByRole('button', {name: '编辑版图'}));
    await screen.findByRole('dialog', {name: '版图工作台'});
    expect(api.getMaskAsset).not.toHaveBeenCalled();
    expect(screen.getByLabelText('资产名称')).toHaveValue(exposure.instanceName);
    expect(screen.getByLabelText('边界 X 最大值 (nm)')).toHaveValue(80);
  });
  it('opens and saves a Mask Workbench overlay while keeping viewer runtime mounted and selection', async () => {
    const exposure = step(0, {name: 'Mask Exposure', params: {mask_mode: 'Asset', mask_asset_id: 'mask_one', mask_asset_revision: 1}});
    const asset = {version: 1 as const, id: 'mask_one', revision: 1, name: 'M1', coordinateUnit: 'nm' as const, boundsNm: [0, 0, 2000, 2000] as const, layers: [{id: '1/0', layer: 1, datatype: 0, name: 'M1', visible: true}], shapes: [], source: {kind: 'editor'}};
    const api = apiStub({init: vi.fn(async () => initView([exposure])), getMaskAsset: vi.fn(async () => asset), saveAndApplyMaskAsset: vi.fn(async request => ({asset: {...request.asset, revision: 2}, step: {...exposure, params: {...exposure.params, mask_asset_revision: 2}}, statuses: ['dirty'] as RuntimeStatus[], warnings: []}))});
    const camera = {view: 'iso'};
    const runtime = {...stubViewerRuntime(), dispose: vi.fn(), mount: vi.fn(), setStandardView: vi.fn((view: string) => {camera.view = view;})};
    render(<App api={api} viewerRuntimeFactory={() => runtime} />);
    await screen.findByRole('button', {name: '编辑版图'});
    fireEvent.click(screen.getByRole('button', {name: '顶视图'}));
    const opener = screen.getByRole('button', {name: '编辑版图'}); opener.focus();
    fireEvent.click(opener);
    await screen.findByRole('dialog', {name: '版图工作台'});
    expect(document.querySelector('.studio-shell')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('资产名称'), {target: {value: 'New layout'}});
    fireEvent.click(screen.getByRole('button', {name: '保存并应用'}));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(runtime.dispose).not.toHaveBeenCalled(); expect(runtime.mount).toHaveBeenCalledOnce();
    expect(camera.view).toBe('top'); expect(runtime.setStandardView).toHaveBeenCalledOnce();
    expect(opener).toHaveFocus();
    expect(api.getMaskAsset).toHaveBeenCalledWith('mask_one', 1, expect.any(AbortSignal));
    expect(screen.getByText('mask_one · revision 2')).toBeInTheDocument();
  });
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

  it('启动阶段的已知 API 错误码使用本地化安全正文', async () => {
    render(<App api={apiStub({
      init: vi.fn(async () => {
        throw new TcadApiError('raw server connection detail', {
          status: 0,
          code: 'network_error',
        });
      }),
    })} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('无法连接 TCAD 服务。');
    expect(alert).not.toHaveTextContent('raw server connection detail');
  });

  it('Parameters 折叠按钮同步 class、hidden 与 aria-expanded', async () => {
    render(<App api={apiStub()} />);
    const button = await screen.findByRole('button', {name: '折叠 Parameters'});
    const panel = screen.getByRole('region', {name: 'Parameters'});
    const workspace = panel.closest('.studio-workspace');

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

  it('切换语言保留未失焦草稿、选中步骤与 Viewer runtime，且不请求工艺 API', async () => {
    const api = apiStub({
      init: vi.fn(async () => initView([
        step(0, {instanceName: 'Substrate'}),
        step(1, {
          instanceName: 'Etch',
          params: {dose: 5},
          parameterSpecs: [{
            key: 'dose',
            label: 'Dose',
            type: 'float',
            minimum: 0,
          }],
        }),
      ])),
    });
    const runtime = {
      backend: 'WebGL2',
      mount: vi.fn(),
      setStandardView: vi.fn(),
      setProjection: vi.fn(),
      setClipping: vi.fn(),
      setMaterialDisplay: vi.fn(),
      pickAt: vi.fn(() => null),
      setMeasureMarkers: vi.fn(),
      fit: vi.fn(),
      loadMeshes: vi.fn(async () => ({warnings: [], materials: []})),
      dispose: vi.fn(),
    };
    const runtimeFactory = vi.fn(() => runtime);
    render(<App api={api} viewerRuntimeFactory={runtimeFactory} />);

    const etch = await within(await screen.findByRole('listbox', {name: 'Process Flow'})).findByRole('option', {name: /Etch/});
    fireEvent.click(etch);
    const dose = screen.getByRole('textbox', {name: 'Dose'});
    fireEvent.change(dose, {target: {value: '-1'}});
    fireEvent.click(screen.getByRole('button', {name: 'EN'}));

    expect(screen.getByRole('textbox', {name: 'Dose'})).toHaveValue('-1');
    expect(screen.getByText('Must be greater than or equal to 0')).toBeVisible();
    expect(within(screen.getByRole('listbox', {name: 'Process Flow'})).getByRole('option', {name: /Etch/})).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('button', {name: 'Run All'})).toBeVisible();
    expect(window.localStorage.getItem('tcad.locale.v1')).toBe('en');
    expect(api.init).toHaveBeenCalledTimes(1);
    expect(api.setStep).not.toHaveBeenCalled();
    expect(api.runStep).not.toHaveBeenCalled();
    expect(api.runTo).not.toHaveBeenCalled();
    expect(api.runAll).not.toHaveBeenCalled();
    expect(api.getTimeline).toHaveBeenCalledTimes(1);
    expect(runtimeFactory).toHaveBeenCalledTimes(1);
    expect(runtime.loadMeshes).toHaveBeenCalledTimes(1);
    expect(runtime.dispose).not.toHaveBeenCalled();
  });

  it('鼠标切换语言不会让合法参数草稿 blur 并保存', async () => {
    const api = apiStub({
      init: vi.fn(async () => initView([
        step(0, {instanceName: 'Substrate'}),
        step(1, {
          instanceName: 'Etch',
          params: {dose: 5},
          parameterSpecs: [{
            key: 'dose',
            label: 'Dose',
            type: 'float',
            minimum: 0,
          }],
        }),
      ])),
    });
    const runtime = {
      backend: 'WebGL2', mount: vi.fn(), setStandardView: vi.fn(), setProjection: vi.fn(),
      setClipping: vi.fn(), setMaterialDisplay: vi.fn(), pickAt: vi.fn(() => null),
      setMeasureMarkers: vi.fn(), fit: vi.fn(), loadMeshes: vi.fn(async () => ({warnings: [], materials: []})),
      dispose: vi.fn(),
    };
    const runtimeFactory = vi.fn(() => runtime);
    render(<App api={api} viewerRuntimeFactory={runtimeFactory} />);

    const etch = await within(await screen.findByRole('listbox', {name: 'Process Flow'})).findByRole('option', {name: /Etch/});
    fireEvent.click(etch);
    const dose = screen.getByRole('textbox', {name: 'Dose'});
    dose.focus();
    fireEvent.change(dose, {target: {value: '6.00'}});
    const english = screen.getByRole('button', {name: 'EN'});

    const mousedownAllowed = fireEvent.mouseDown(english);
    expect(mousedownAllowed).toBe(false);
    if (mousedownAllowed) {
      english.focus();
      fireEvent.blur(dose);
    }
    fireEvent.mouseUp(english);
    fireEvent.click(english);

    await screen.findByRole('button', {name: 'Run All'});
    expect(screen.getByRole('textbox', {name: 'Dose'})).toHaveValue('6.00');
    expect(within(screen.getByRole('listbox', {name: 'Process Flow'})).getByRole('option', {name: /Etch/})).toHaveAttribute('aria-selected', 'true');
    expect(api.setStep).not.toHaveBeenCalled();
    expect(api.init).toHaveBeenCalledTimes(1);
    expect(api.getTimeline).toHaveBeenCalledTimes(1);
    expect(runtimeFactory).toHaveBeenCalledTimes(1);
    expect(runtime.loadMeshes).toHaveBeenCalledTimes(1);
    expect(runtime.dispose).not.toHaveBeenCalled();
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

    fireEvent.click(screen.getByRole('button', {name: '全部运行'}));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('无法连接 TCAD 服务');

    fireEvent.click(screen.getByRole('button', {name: '重新同步'}));
    await waitFor(() => {
      expect((api.getTimeline as ReturnType<typeof vi.fn>).mock.calls.length)
        .toBeGreaterThan(getTimelineCallsBefore);
    });
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });

  it('已知错误码显示当前语言文案而不暴露原始消息', async () => {
    const api = apiStub({
      runAll: vi.fn(async () => {
        throw new TcadApiError('raw server connection detail', {
          status: 0,
          code: 'network_error',
        });
      }),
    });
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '全部运行'});
    fireEvent.click(screen.getByRole('button', {name: 'EN'}));
    fireEvent.click(screen.getByRole('button', {name: 'Run All'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Unable to connect');
    expect(alert).not.toHaveTextContent('raw server connection detail');
  });

  it('未知错误只显示通用文案与受限诊断元数据', async () => {
    const api = apiStub({
      runAll: vi.fn(async () => {
        throw new TcadApiError('safe diagnostic message', {
          status: 500,
          code: 'unregistered_error',
          details: {stepIndex: 0, secret: '/private/secret-database-path'},
          parameterPath: 'path=/private/secret-database-path',
          suggestion: 'Authorization: Bearer secret-token',
        });
      }),
    });
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '全部运行'});
    fireEvent.click(screen.getByRole('button', {name: 'EN'}));
    fireEvent.click(screen.getByRole('button', {name: 'Run All'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('An unexpected error occurred.');
    expect(alert).toHaveTextContent('code: unregistered_error');
    expect(alert).toHaveTextContent('stepIndex: 0');
    expect(alert).not.toHaveTextContent('safe diagnostic message');
    expect(alert).not.toHaveTextContent('secret-database-path');
    expect(alert).not.toHaveTextContent('Authorization: Bearer');
  });

  it('未知错误的诊断详情不会泄露不安全的错误码', async () => {
    const api = apiStub({
      runAll: vi.fn(async () => {
        throw new TcadApiError('safe diagnostic message', {
          status: 500,
          code: '/private/secret-database-path',
        });
      }),
    });
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '全部运行'});
    fireEvent.click(screen.getByRole('button', {name: '全部运行'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('发生未预期的错误。');
    expect(alert).not.toHaveTextContent('safe diagnostic message');
    expect(alert).not.toHaveTextContent('secret-database-path');
  });
});
