import {act, render, screen, waitFor} from '@testing-library/react';
import {StrictMode, useEffect} from 'react';
import {describe, expect, it, vi} from 'vitest';
import {TcadApiError} from '../api/client';
import type {
  InitView,
  RuntimeStatus,
  RunView,
  SetStepView,
  StepView,
  TcadApi,
  TimelineRestoreView,
  TimelineView,
} from '../api/types';
import {
  AppStateProvider,
  type AppStateContextValue,
  useAppState,
} from './AppStateContext';

function step(index: number, overrides: Partial<StepView> = {}): StepView {
  return {
    index,
    name: `step-${index}`,
    instanceName: `Step ${index}`,
    group: '',
    loop: '',
    enabled: true,
    params: {dose: 100 + index},
    parameterSpecs: [],
    runtimeStatus: 'ready',
    ...overrides,
  };
}

const initView: InitView = {
  recipe: [step(0), step(1)],
  model: {gridShape: [8, 8, 8], voxelSizeNm: 10},
  factories: ['deposit'],
  materials: [],
  uiState: {},
};

const timeline: TimelineView = {
  items: [
    {index: 0, state: 'done', runtimeStatus: 'done', snapshotValid: true},
    {index: 1, state: 'current', runtimeStatus: 'ready', snapshotValid: false},
  ],
  current: 1,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, resolve, reject};
}

function apiStub(overrides: Partial<TcadApi> = {}): TcadApi {
  return {
    init: vi.fn(async () => initView),
    setStep: vi.fn(async request => ({
      step: step(request.index),
      statuses: ['ready', 'ready'] as RuntimeStatus[],
      warnings: [],
    })),
    runStep: vi.fn(async () => ({})),
    runTo: vi.fn(async () => ({})),
    runAll: vi.fn(async () => ({})),
    getTimeline: vi.fn(async () => timeline),
    restoreTimeline: vi.fn(async index => ({
      timeline: {...timeline, current: index},
      model: initView.model,
      recipe: initView.recipe,
      log: [],
    })),
    getPreviewManifest: vi.fn(async () => ({revision: 1, meshes: []})),
    getMaterialStl: vi.fn(async () => new ArrayBuffer(0)),
    ...overrides,
  };
}

let captured: AppStateContextValue | null = null;

function Capture({events}: {events?: string[]}) {
  const context = useAppState();
  captured = context;
  useEffect(() => {
    if (context.state.lastModelRevision !== null) {
      events?.push(`ui:revision:${context.state.lastModelRevision}`);
    }
  }, [context.state.lastModelRevision, events]);
  return (
    <output>
      {context.state.phase}:{context.state.activeMutation ?? 'none'}:
      {context.state.lastModelRevision ?? 'none'}:{context.state.timeline?.current ?? 'none'}
    </output>
  );
}

function mount(api: TcadApi, events?: string[]) {
  captured = null;
  return render(
    <AppStateProvider api={api}>
      <Capture events={events} />
    </AppStateProvider>,
  );
}

async function waitUntilReady() {
  await waitFor(() => expect(captured?.state.phase).toBe('ready'));
}

describe('AppStateProvider bootstrap', () => {
  it('StrictMode effect 重放也只请求一次 init', async () => {
    const pending = deferred<InitView>();
    const api = apiStub({init: vi.fn(() => pending.promise)});

    render(
      <StrictMode>
        <AppStateProvider api={api}>
          <Capture />
        </AppStateProvider>
      </StrictMode>,
    );
    await waitFor(() => expect(api.init).toHaveBeenCalledTimes(1));

    await act(async () => pending.resolve(initView));
    await waitUntilReady();
    expect(api.init).toHaveBeenCalledTimes(1);
  });

  it('失败后显式 bootstrap retry 可以重新请求，未知错误不泄露 raw 值', async () => {
    const raw = {secret: 'do-not-leak'};
    const init = vi.fn()
      .mockRejectedValueOnce(raw)
      .mockResolvedValueOnce(initView);
    mount(apiStub({init}));

    await waitFor(() => expect(captured?.state.phase).toBe('fatal'));
    expect(captured?.state.globalError).toBeInstanceOf(TcadApiError);
    expect(captured?.state.globalError).not.toHaveProperty('causeValue', raw);

    await act(async () => captured?.actions.bootstrap());
    await waitUntilReady();
    expect(init).toHaveBeenCalledTimes(2);
  });
});

describe('AppStateProvider mutation gate 与顺序', () => {
  it('同一 render 内双击也只发送一个运行请求，并阻止运行期间保存', async () => {
    const run = deferred<RunView>();
    const api = apiStub({runAll: vi.fn(() => run.promise)});
    mount(api);
    await waitUntilReady();

    let first!: Promise<void>;
    await act(async () => {
      first = captured!.actions.runAll();
      void captured!.actions.runAll();
      captured!.actions.updateDraft(0, 'dose', 150, {status: 'valid'});
      void captured!.actions.saveParameter(0, 'dose');
    });

    expect(api.runAll).toHaveBeenCalledTimes(1);
    expect(api.setStep).not.toHaveBeenCalled();
    expect(captured?.state.activeMutation).toBe('all');

    await act(async () => run.resolve({modelRevision: 4}));
    await first;
    await waitUntilReady();
    expect(captured?.state.activeMutation).toBeNull();
  });

  it('run 成功先发布 revision/result，再请求并发布 Timeline', async () => {
    const events: string[] = [];
    const timelinePending = deferred<TimelineView>();
    const api = apiStub({
      runAll: vi.fn(async () => {
        events.push('api:run');
        return {modelRevision: 17};
      }),
      getTimeline: vi.fn(() => {
        events.push('api:timeline');
        return timelinePending.promise;
      }),
    });
    mount(api, events);
    await waitUntilReady();

    let operation!: Promise<void>;
    act(() => {
      operation = captured!.actions.runAll();
    });
    await waitFor(() => expect(screen.getByText(/running:all:17:none/)).toBeInTheDocument());
    expect(events.slice(0, 3)).toEqual(['api:run', 'api:timeline', 'ui:revision:17']);
    expect(captured?.state.recipe[0].runtimeStatus).toBe('ready');

    await act(async () => timelinePending.resolve(timeline));
    await operation;
    expect(captured?.state.timeline).toEqual(timeline);
    expect(captured?.state.recipe.map(item => item.runtimeStatus)).toEqual(['done', 'ready']);
    expect(captured?.state.activeMutation).toBeNull();
  });

  it('runStep 的真实最小响应立即更新目标步骤，Timeline 再同步全部状态', async () => {
    const timelinePending = deferred<TimelineView>();
    const api = apiStub({
      runStep: vi.fn(async () => ({
        runtimeStatus: 'done',
        modelRevision: 18,
        result: 'deposited',
      } satisfies RunView)),
      getTimeline: vi.fn(() => timelinePending.promise),
    });
    mount(api);
    await waitUntilReady();

    let operation!: Promise<void>;
    act(() => {
      operation = captured!.actions.runStep(1);
    });
    await waitFor(() => expect(captured?.state.lastModelRevision).toBe(18));
    expect(captured?.state.recipe.map(item => item.runtimeStatus)).toEqual(['ready', 'done']);

    await act(async () => timelinePending.resolve({
      current: 1,
      items: [
        {index: 0, state: 'done', runtimeStatus: 'dirty', snapshotValid: true},
        {index: 1, state: 'current', runtimeStatus: 'done', snapshotValid: true},
      ],
    }));
    await operation;
    expect(captured?.state.recipe.map(item => item.runtimeStatus)).toEqual(['dirty', 'done']);
  });

  it('Timeline 刷新失败仍保留 run 结果并释放 gate', async () => {
    const api = apiStub({
      runStep: vi.fn(async () => ({
        runtimeStatus: 'done',
        modelRevision: 21,
        result: 'ok',
      } satisfies RunView)),
      getTimeline: vi.fn(async () => {
        throw new TcadApiError('时间线不可用', {status: 503});
      }),
    });
    mount(api);
    await waitUntilReady();

    await act(async () => captured!.actions.runStep(0));

    expect(captured?.state.lastModelRevision).toBe(21);
    expect(captured?.state.lastRunResult).toBe('ok');
    expect(captured?.state.recipe[0].runtimeStatus).toBe('done');
    expect(captured?.state.globalError?.message).toBe('时间线不可用');
    expect(captured?.state.phase).toBe('ready');
    expect(captured?.state.activeMutation).toBeNull();
  });

  it('每个字段 sequence 可并发，旧响应不能覆盖新 draft', async () => {
    const oldSave = deferred<SetStepView>();
    const newSave = deferred<SetStepView>();
    const setStep = vi.fn()
      .mockReturnValueOnce(oldSave.promise)
      .mockReturnValueOnce(newSave.promise);
    const api = apiStub({setStep});
    mount(api);
    await waitUntilReady();

    act(() => {
      captured!.actions.updateDraft(1, 'dose', 110, {status: 'valid'});
    });
    const first = captured!.actions.saveParameter(1, 'dose');
    act(() => {
      captured!.actions.updateDraft(1, 'dose', 120, {status: 'valid'});
    });
    const second = captured!.actions.saveParameter(1, 'dose');

    await act(async () => newSave.resolve({
      step: step(1, {params: {dose: 120}, runtimeStatus: 'dirty'}),
      statuses: ['ready', 'dirty'],
      warnings: [],
    }));
    await second;
    await act(async () => oldSave.resolve({
      step: step(1, {params: {dose: 110}, runtimeStatus: 'dirty'}),
      statuses: ['ready', 'dirty'],
      warnings: [],
    }));
    await first;

    expect(setStep).toHaveBeenNthCalledWith(
      1,
      {index: 1, params: {dose: 110}},
      expect.any(AbortSignal),
    );
    expect(captured?.state.recipe[1].params.dose).toBe(120);
    expect(captured?.state.drafts['1:dose']).toBeUndefined();
  });

  it('runStep 与 runTo 默认使用当前选中步骤', async () => {
    const api = apiStub();
    mount(api);
    await waitUntilReady();
    act(() => captured!.actions.selectStep(1));

    await act(async () => captured!.actions.runStep());
    await act(async () => captured!.actions.runTo());

    expect(api.runStep).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    expect(api.runTo).toHaveBeenCalledWith(1, expect.any(AbortSignal));
  });

  it('无效 draft 不发送保存请求', async () => {
    const api = apiStub();
    mount(api);
    await waitUntilReady();
    act(() => {
      captured!.actions.updateDraft(0, 'dose', -1, {
        status: 'invalid',
        message: '必须为正数',
      });
    });

    await act(async () => captured!.actions.saveParameter(0, 'dose'));
    expect(api.setStep).not.toHaveBeenCalled();
    expect(captured?.state.drafts['0:dose'].validation.status).toBe('invalid');
  });
});

describe('AppStateProvider Timeline 与生命周期', () => {
  it('只恢复 snapshotValid 节点，且不调用任何 run API', async () => {
    const restored: TimelineRestoreView = {
      timeline: {...timeline, current: 0},
      model: initView.model,
      recipe: [step(0, {runtimeStatus: 'done'}), step(1)],
      log: ['restored'],
    };
    const api = apiStub({restoreTimeline: vi.fn(async () => restored)});
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());

    await act(async () => captured!.actions.restoreTimeline(1));
    expect(api.restoreTimeline).not.toHaveBeenCalled();

    await act(async () => captured!.actions.restoreTimeline(0));
    expect(api.restoreTimeline).toHaveBeenCalledWith(0, expect.any(AbortSignal));
    expect(api.runStep).not.toHaveBeenCalled();
    expect(api.runTo).not.toHaveBeenCalled();
    expect(api.runAll).not.toHaveBeenCalled();
    expect(captured?.state.timeline?.current).toBe(0);
    expect(captured?.state.selectedStepIndex).toBe(0);
    expect(captured?.state.lastModelRevision).toBeNull();
    expect(captured?.state.previewGeneration).toBe(2);
  });

  it('首次 Timeline load 接受 current=-1 而不进入 fatal', async () => {
    const emptyTimeline: TimelineView = {items: [], current: -1};
    const api = apiStub({getTimeline: vi.fn(async () => emptyTimeline)});
    mount(api);
    await waitUntilReady();

    await act(async () => captured!.actions.loadTimeline());

    expect(captured?.state.timeline).toEqual(emptyTimeline);
    expect(captured?.state.phase).toBe('ready');
    expect(captured?.state.globalError).toBeNull();
  });

  it('unmount 后异步完成不会 dispatch 或产生 React 警告', async () => {
    const pending = deferred<RunView>();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const api = apiStub({runAll: vi.fn(() => pending.promise)});
    const mounted = mount(api);
    await waitUntilReady();
    const operation = captured!.actions.runAll();
    mounted.unmount();

    await act(async () => pending.resolve({modelRevision: 99}));
    await operation;
    expect(api.getTimeline).not.toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
