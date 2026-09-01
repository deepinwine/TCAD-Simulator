import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {App} from '../App';
import {TcadApiError} from '../api/client';
import type {
  InitView,
  RuntimeStatus,
  RunView,
  StepView,
  TcadApi,
  TimelineView,
} from '../api/types';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, resolve, reject};
}

function step(index: number, overrides: Partial<StepView> = {}): StepView {
  return {
    index,
    name: `step-${index}`,
    instanceName: `Step ${index + 1}`,
    group: '',
    loop: '',
    enabled: true,
    params: {dose: 100},
    parameterSpecs: [{
      key: 'dose',
      label: 'Dose',
      type: 'float',
      minimum: 0,
    }],
    runtimeStatus: 'ready',
    ...overrides,
  };
}

function initView(recipe: StepView[] = [step(0), step(1)]): InitView {
  return {
    recipe,
    model: {gridShape: [8, 8, 8], voxelSizeNm: 10},
    factories: ['deposit'],
    materials: [],
    uiState: {},
  };
}

const initialTimeline: TimelineView = {
  current: 0,
  items: [
    {index: 0, state: 'current', runtimeStatus: 'ready', snapshotValid: true},
    {index: 1, state: 'pending', runtimeStatus: 'ready', snapshotValid: false},
  ],
};

function apiStub(overrides: Partial<TcadApi> = {}): TcadApi {
  return {
    init: vi.fn(async () => initView()),
    setStep: vi.fn(async request => ({
      step: step(request.index),
      statuses: ['ready', 'ready'] as RuntimeStatus[],
      warnings: [],
    })),
    runStep: vi.fn(async () => ({})),
    runTo: vi.fn(async () => ({})),
    runAll: vi.fn(async () => ({})),
    undo: vi.fn(async () => ({applied: false, log: []})),
    redo: vi.fn(async () => ({applied: false, log: []})),
    importRecipe: vi.fn(async () => ({
      model: initView().model,
      recipe: initView().recipe,
      currentRecipe: {name: 'Basic Trench', id: ''},
      log: [],
    })),
    newRecipe: vi.fn(async () => ({
      model: initView().model,
      recipe: initView().recipe,
      currentRecipe: {name: 'New', id: ''},
      log: [],
    })),
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
    exportRecipe: vi.fn(async () => new Blob(['{}'], {type: 'application/json'})),
    loadRecipe: vi.fn(async () => ({
      model: initView().model,
      recipe: initView().recipe,
      currentRecipe: {name: 'Loaded', id: 'h1'},
      log: [],
    })),
    getTimeline: vi.fn(async () => initialTimeline),
    restoreTimeline: vi.fn(async index => ({
      timeline: {...initialTimeline, current: index},
      model: initView().model,
      recipe: initView().recipe,
      log: [],
    })),
    getPreviewManifest: vi.fn(async () => ({revision: 1, meshes: []})),
    getMaterialStl: vi.fn(async () => new ArrayBuffer(0)),
    ...overrides,
  };
}

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

function recordingViewerRuntime() {
  const loadedTokens: number[] = [];
  return {
    loadedTokens,
    factory: () => ({
      backend: 'WebGL2',
      mount: () => {},
      setStandardView: () => {},
      setProjection: () => {},
      setClipping: () => {},
      setMaterialDisplay: () => {},
      pickAt: () => null,
      setMeasureMarkers: () => {},
      fit: () => {},
      loadMeshes: async (token: number) => {
        loadedTokens.push(token);
        return {warnings: [], materials: []};
      },
      dispose: () => {},
    }),
  };
}

describe('Toolbar 配方管理', () => {
  it('Demo 列表来自 init，选择后加载触发 importRecipe', async () => {
    const api = apiStub({
      init: vi.fn(async () => ({
        ...initView(),
        demoRecipes: {
          'Basic Trench': {description: '基础沟槽', steps: []},
          'Spacer Formation': {steps: []},
        },
      })),
    });
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    const select = await screen.findByRole('combobox', {name: 'Demo 配方'});
    expect(select).toHaveDisplayValue('-- 选择 Demo 配方 --');
    const options = Array.from(select.querySelectorAll('option')).map(o => o.textContent);
    expect(options).toContain('Basic Trench — 基础沟槽');
    expect(options).toContain('Spacer Formation');

    fireEvent.change(select, {target: {value: 'Basic Trench'}});
    fireEvent.click(screen.getByRole('button', {name: '加载 Demo'}));
    await waitFor(() => expect(api.importRecipe).toHaveBeenCalledTimes(1));
  });

  it('保存与导出触发对应调用', async () => {
    const api = apiStub();
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '保存配方'});
    fireEvent.change(screen.getByRole('textbox', {name: '配方名称'}), {
      target: {value: 'My Recipe'},
    });
    fireEvent.click(screen.getByRole('button', {name: '保存配方'}));
    await waitFor(() => expect(api.saveRecipe).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', {name: '导出配方'}));
    await waitFor(() => expect(api.exportRecipe).toHaveBeenCalledTimes(1));
  });

  it('导入读取本地 JSON 文件并触发 importRecipe', async () => {
    const api = apiStub();
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '导入配方'});
    const input = screen.getByLabelText('导入配方文件') as HTMLInputElement;
    const file = new File([JSON.stringify({steps: []})], 'recipe.json', {
      type: 'application/json',
    });
    fireEvent.change(input, {target: {files: [file]}});
    await waitFor(() => expect(api.importRecipe).toHaveBeenCalledTimes(1));
  });

  it('新建配方以输入名调用 newRecipe', async () => {
    const api = apiStub();
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    const nameInput = await screen.findByRole('textbox', {name: '配方名称'});
    fireEvent.change(nameInput, {target: {value: 'My Process'}});
    fireEvent.click(screen.getByRole('button', {name: '新建配方'}));
    await waitFor(() => expect(api.newRecipe).toHaveBeenCalledWith('My Process'));
  });
});

describe('Toolbar undo/redo', () => {
  it('撤销与重做按钮触发对应 API 调用', async () => {
    const api = apiStub();
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '运行全部'});

    fireEvent.click(screen.getByRole('button', {name: '撤销'}));
    await waitFor(() => expect(api.undo).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', {name: '重做'}));
    await waitFor(() => expect(api.redo).toHaveBeenCalledTimes(1));
  });

  it('运行中撤销/重做禁用', async () => {
    const pending = new Promise<never>(() => undefined);
    const api = apiStub({runAll: vi.fn(() => pending)});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '运行全部'});
    fireEvent.click(screen.getByRole('button', {name: '运行全部'}));
    await waitFor(() => expect(screen.getByRole('button', {name: '撤销'})).toBeDisabled());
    expect(screen.getByRole('button', {name: '重做'})).toBeDisabled();
  });
});

describe('Toolbar 执行操作', () => {
  it('三个运行按钮分别调用选中步骤、运行至步骤和运行全部', async () => {
    const api = apiStub();
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '运行选中步骤'});

    fireEvent.click(screen.getByRole('button', {name: '运行选中步骤'}));
    await waitFor(() => expect(api.runStep).toHaveBeenCalledWith(0, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole('button', {name: '运行至选中步骤'}));
    await waitFor(() => expect(api.runTo).toHaveBeenCalledWith(0, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole('button', {name: '运行全部'}));
    await waitFor(() => expect(api.runAll).toHaveBeenCalledWith(expect.any(AbortSignal)));
  });

  it('Run All 进行中锁住参数和其他运行按钮，双击也只调用一次', async () => {
    const pending = deferred<RunView>();
    const api = apiStub({runAll: vi.fn(() => pending.promise)});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    const runAll = await screen.findByRole('button', {name: '运行全部'});
    fireEvent.click(runAll);
    fireEvent.click(runAll);

    await waitFor(() => expect(api.runAll).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', {name: '运行选中步骤'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '运行至选中步骤'})).toBeDisabled();
    expect(runAll).toBeDisabled();
    expect(screen.getByRole('region', {name: 'Parameters'})).toHaveAttribute(
      'aria-busy',
      'true',
    );

    pending.resolve({modelRevision: 7});
    await waitFor(() => expect(runAll).toBeEnabled());
  });

  it('没有选中步骤时只禁用依赖选择的两个操作', async () => {
    const api = apiStub({init: vi.fn(async () => initView([]))});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    expect(await screen.findByRole('button', {name: '运行选中步骤'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '运行至选中步骤'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '运行全部'})).toBeEnabled();
  });

  it('存在未保存 draft 时禁用全部运行与恢复，并解释处理方式', async () => {
    const api = apiStub();
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    const dose = await screen.findByRole('textbox', {name: 'Dose'});
    await screen.findByRole('button', {name: '恢复步骤 1'});

    fireEvent.change(dose, {target: {value: '-1'}});

    const guidance = screen.getByText('请先保存或修正参数');
    expect(guidance).toBeVisible();
    for (const label of ['运行选中步骤', '运行至选中步骤', '运行全部']) {
      const button = screen.getByRole('button', {name: label});
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('aria-describedby', guidance.id);
    }
    expect(screen.getByRole('button', {name: '恢复步骤 1'})).toBeDisabled();
    expect(api.runStep).not.toHaveBeenCalled();
    expect(api.runTo).not.toHaveBeenCalled();
    expect(api.runAll).not.toHaveBeenCalled();
    expect(api.restoreTimeline).not.toHaveBeenCalled();
  });

  it.each([
    [false, '模型未回滚，状态可能已改变'],
    [true, '服务端报告：本次失败已回滚'],
  ] as const)('步骤错误显示结构字段和 rolledBack=%s', async (rolledBack, rollbackCopy) => {
    const api = apiStub({
      runStep: vi.fn(async () => {
        throw new TcadApiError('沉积失败', {
          status: 400,
          parameterPath: 'params.dose',
          suggestion: '减小剂量后重试',
          rolledBack,
          details: {stepIndex: 1},
        });
      }),
    });
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    fireEvent.click(await screen.findByRole('option', {name: /Step 2/}));
    fireEvent.click(screen.getByRole('button', {name: '运行选中步骤'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('沉积失败');
    expect(alert).toHaveTextContent('参数路径：params.dose');
    expect(alert).toHaveTextContent('建议：减小剂量后重试');
    expect(alert).toHaveTextContent(rollbackCopy);
    expect(screen.getByRole('option', {name: /Step 2/})).toHaveTextContent('Error');
  });

  it('成功后先采用真实 run 结果，再刷新权威 Timeline 和 Viewer generation', async () => {
    const refreshed: TimelineView = {
      current: 1,
      items: [
        {index: 0, state: 'done', runtimeStatus: 'done', snapshotValid: true},
        {index: 1, state: 'current', runtimeStatus: 'done', snapshotValid: true},
      ],
    };
    const getTimeline = vi.fn()
      .mockResolvedValueOnce(initialTimeline)
      .mockResolvedValueOnce(refreshed);
    const api = apiStub({
      runStep: vi.fn(async () => ({
        index: 1,
        runtimeStatus: 'done',
        modelRevision: 12,
        result: {server: 'authoritative'},
      } satisfies RunView)),
      getTimeline,
    });
    const viewerRuntime = recordingViewerRuntime();
    render(<App api={api} viewerRuntimeFactory={viewerRuntime.factory} />);
    fireEvent.click(await screen.findByRole('option', {name: /Step 2/}));
    await waitFor(() => expect(getTimeline).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', {name: '运行选中步骤'}));

    await waitFor(() => expect(getTimeline).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      expect(screen.getByRole('navigation', {name: 'Process Timeline'}))
        .toHaveTextContent('#2 current');
    });
    await waitFor(() => expect(viewerRuntime.loadedTokens).toEqual([1, 2]));
  });

  it('Run All 的无步骤结构化错误显示为全局错误', async () => {
    const api = apiStub({
      runAll: vi.fn(async () => {
        throw new TcadApiError('全局执行失败', {
          status: 500,
          suggestion: '检查 Worker 日志',
          rolledBack: false,
        });
      }),
    });
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    fireEvent.click(await screen.findByRole('button', {name: '运行全部'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('全局执行失败');
    expect(alert).toHaveTextContent('检查 Worker 日志');
    expect(alert).toHaveTextContent('模型未回滚，状态可能已改变');
  });

  it('运行中通过 live region 播报当前操作，连接指示切换为 Running，结束后恢复', async () => {
    const pending = deferred<RunView>();
    const api = apiStub({runAll: vi.fn(() => pending.promise)});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    const runAll = await screen.findByRole('button', {name: '运行全部'});
    expect(screen.getByText('已连接 Connected')).toBeInTheDocument();
    fireEvent.click(runAll);

    const announcement = await screen.findByText('正在运行：运行全部…');
    const liveRegion = announcement.closest('[role="status"]');
    expect(liveRegion).not.toBeNull();
    expect(liveRegion).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('运行中 Running')).toBeInTheDocument();

    pending.resolve({});
    await waitFor(() => expect(screen.queryByText('正在运行：运行全部…')).toBeNull());
    expect(screen.getByText('已连接 Connected')).toBeInTheDocument();
    expect(runAll).toBeEnabled();
  });
});
