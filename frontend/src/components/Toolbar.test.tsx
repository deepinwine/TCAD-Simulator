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

describe('Toolbar 执行操作', () => {
  it('三个运行按钮分别调用选中步骤、运行至步骤和运行全部', async () => {
    const api = apiStub();
    render(<App api={api} />);
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
    render(<App api={api} />);

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
    render(<App api={api} />);

    expect(await screen.findByRole('button', {name: '运行选中步骤'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '运行至选中步骤'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '运行全部'})).toBeEnabled();
  });

  it('存在未保存 draft 时禁用全部运行与恢复，并解释处理方式', async () => {
    const api = apiStub();
    render(<App api={api} />);
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
    render(<App api={api} />);
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
    render(<App api={api} />);
    fireEvent.click(await screen.findByRole('option', {name: /Step 2/}));
    await waitFor(() => expect(getTimeline).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', {name: '运行选中步骤'}));

    await waitFor(() => expect(getTimeline).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      expect(screen.getByRole('navigation', {name: 'Process Timeline'}))
        .toHaveTextContent('#2 current');
    });
    expect(screen.getByRole('region', {name: '3D Viewer'})).toHaveAttribute(
      'data-refresh-token',
      '2',
    );
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
    render(<App api={api} />);
    fireEvent.click(await screen.findByRole('button', {name: '运行全部'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('全局执行失败');
    expect(alert).toHaveTextContent('检查 Worker 日志');
    expect(alert).toHaveTextContent('模型未回滚，状态可能已改变');
  });
});
