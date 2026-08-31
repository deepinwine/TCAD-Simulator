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
    undo: vi.fn(async () => ({applied: false, log: []})),
    redo: vi.fn(async () => ({applied: false, log: []})),
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

describe('AppStateProvider undo/redo', () => {
  it('undo 成功后重拉 timeline 并刷新 Viewer 几何', async () => {
    const api = apiStub({
      undo: vi.fn(async () => ({
        applied: true,
        model: initView.model,
        log: ['undo'],
      })),
    });
    mount(api);
    await waitUntilReady();
    const generationBefore = captured!.state.previewGeneration;
    const timelineCalls = (api.getTimeline as ReturnType<typeof vi.fn>).mock.calls.length;

    await captured!.actions.undo();

    expect(api.undo).toHaveBeenCalledTimes(1);
    expect(
      (api.getTimeline as ReturnType<typeof vi.fn>).mock.calls.length,
    ).toBeGreaterThan(timelineCalls);
    await waitFor(() => {
      expect(captured!.state.previewGeneration).toBe(generationBefore + 1);
    });
  });

  it('undo 无可撤销时静默 no-op（不重拉、不刷新）', async () => {
    const api = apiStub({undo: vi.fn(async () => ({applied: false, log: []}))});
    mount(api);
    await waitUntilReady();
    const generationBefore = captured!.state.previewGeneration;
    const timelineCalls = (api.getTimeline as ReturnType<typeof vi.fn>).mock.calls.length;

    await captured!.actions.undo();

    expect(api.undo).toHaveBeenCalledTimes(1);
    expect(
      (api.getTimeline as ReturnType<typeof vi.fn>).mock.calls.length,
    ).toBe(timelineCalls);
    expect(captured!.state.previewGeneration).toBe(generationBefore);
  });

  it('运行中 undo 被变更 gate 拦截', async () => {
    const pending = deferred<RunView>();
    const api = apiStub({runStep: vi.fn(() => pending.promise)});
    mount(api);
    await waitUntilReady();
    void captured!.actions.runStep(0);
    await waitFor(() => expect(captured!.state.activeMutation).toBe('step'));

    await captured!.actions.undo();
    expect(api.undo).not.toHaveBeenCalled();

    pending.resolve({});
    await waitFor(() => expect(captured!.state.activeMutation).toBeNull());
  });

  it('undo 失败显示结构化错误且几何不刷新', async () => {
    const api = apiStub({
      undo: vi.fn(async () => {
        throw new TcadApiError('撤销失败：历史不可用', {
          status: 409,
          code: 'undo_unavailable',
        });
      }),
    });
    mount(api);
    await waitUntilReady();
    const generationBefore = captured!.state.previewGeneration;

    await captured!.actions.undo();

    await waitFor(() => {
      expect(captured!.state.globalError?.message).toBe('撤销失败：历史不可用');
    });
    expect(captured!.state.previewGeneration).toBe(generationBefore);
  });
});

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
  it('历史视图中的真实运行开始立即退出，运行失败也不恢复历史标识', async () => {
    const run = deferred<RunView>();
    const api = apiStub({runAll: vi.fn(() => run.promise)});
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());
    await act(async () => captured!.actions.restoreTimeline(0));
    expect(captured?.state.historicalStepIndex).toBe(0);

    let operation!: Promise<void>;
    act(() => {
      operation = captured!.actions.runAll();
    });
    expect(api.runAll).toHaveBeenCalledTimes(1);
    expect(captured?.state.historicalStepIndex).toBeNull();

    await act(async () => run.reject(new TcadApiError('运行失败', {status: 500})));
    await operation;
    expect(captured?.state.historicalStepIndex).toBeNull();
  });

  it('历史视图中的运行被 draft gate 拒绝时保留历史标识', async () => {
    const api = apiStub();
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());
    await act(async () => captured!.actions.restoreTimeline(0));
    expect(captured?.state.historicalStepIndex).toBe(0);

    act(() => {
      captured!.actions.updateDraft(0, 'dose', -1, {
        status: 'invalid',
        message: '必须为正数',
      });
    });
    await act(async () => captured!.actions.runAll());

    expect(api.runAll).not.toHaveBeenCalled();
    expect(captured?.state.historicalStepIndex).toBe(0);
  });

  it('任意未清除 draft 会阻止 run 与 restore，保存成功清除后才允许运行', async () => {
    const api = apiStub();
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());

    act(() => {
      captured!.actions.updateDraft(0, 'dose', 150, {status: 'valid'}, '150');
    });
    await act(async () => {
      await Promise.all([
        captured!.actions.runStep(0),
        captured!.actions.runTo(0),
        captured!.actions.runAll(),
        captured!.actions.restoreTimeline(0),
      ]);
    });

    expect(api.runStep).not.toHaveBeenCalled();
    expect(api.runTo).not.toHaveBeenCalled();
    expect(api.runAll).not.toHaveBeenCalled();
    expect(api.restoreTimeline).not.toHaveBeenCalled();

    act(() => {
      captured!.actions.updateDraft(0, 'dose', -1, {status: 'invalid'}, '-1');
    });
    await act(async () => captured!.actions.runAll());
    expect(api.runAll).not.toHaveBeenCalled();

    act(() => {
      captured!.actions.updateDraft(0, 'dose', 150, {status: 'valid'}, '150');
    });
    await act(async () => captured!.actions.saveParameter(0, 'dose'));
    expect(captured?.state.drafts).toEqual({});
    await act(async () => captured!.actions.runStep(0));
    expect(api.runStep).toHaveBeenCalledTimes(1);
  });

  it('同一 render 内双击也只发送一个运行请求，并阻止运行期间保存', async () => {
    const run = deferred<RunView>();
    const api = apiStub({runAll: vi.fn(() => run.promise)});
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());
    await act(async () => captured!.actions.restoreTimeline(0));
    expect(captured?.state.historicalStepIndex).toBe(0);

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
    expect(captured?.state.historicalStepIndex).toBeNull();

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

  it('服务端返回当前 recipe 中的步骤索引时精确映射步骤错误', async () => {
    const error = new TcadApiError('步骤 1 失败', {
      status: 400,
      details: {stepIndex: 0},
    });
    const api = apiStub({runTo: vi.fn(async () => { throw error; })});
    mount(api);
    await waitUntilReady();

    await act(async () => captured!.actions.runTo(1));

    expect(captured?.state.stepErrors[0]).toBe(error);
    expect(captured?.state.globalError).toBeNull();
  });

  it('服务端返回 recipe 外步骤索引时显示全局错误且不回退请求步骤', async () => {
    const error = new TcadApiError('未知步骤失败', {
      status: 400,
      details: {stepIndex: 99},
    });
    const api = apiStub({runStep: vi.fn(async () => { throw error; })});
    mount(api);
    await waitUntilReady();

    await act(async () => captured!.actions.runStep(1));

    expect(captured?.state.stepErrors).toEqual({});
    expect(captured?.state.globalError).toBe(error);
  });

  it('服务端缺失步骤索引时只有 runStep 回退到请求步骤', async () => {
    const stepError = new TcadApiError('单步失败', {status: 400});
    const stepApi = apiStub({runStep: vi.fn(async () => { throw stepError; })});
    const first = mount(stepApi);
    await waitUntilReady();

    await act(async () => captured!.actions.runStep(1));
    expect(captured?.state.stepErrors[1]).toBe(stepError);
    expect(captured?.state.globalError).toBeNull();
    first.unmount();

    const toError = new TcadApiError('运行至目标失败', {status: 400});
    const toApi = apiStub({runTo: vi.fn(async () => { throw toError; })});
    mount(toApi);
    await waitUntilReady();

    await act(async () => captured!.actions.runTo(1));
    expect(captured?.state.stepErrors).toEqual({});
    expect(captured?.state.globalError).toBe(toError);
  });

  it('同字段新版保存排在旧版之后，网络请求严格串行且最终采用新版', async () => {
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
    await waitFor(() => expect(setStep).toHaveBeenCalledTimes(1));
    act(() => {
      captured!.actions.updateDraft(1, 'dose', 120, {status: 'valid'});
    });
    const second = captured!.actions.saveParameter(1, 'dose');

    expect(setStep).toHaveBeenCalledTimes(1);
    await act(async () => oldSave.resolve({
      step: step(1, {params: {dose: 110}, runtimeStatus: 'dirty'}),
      statuses: ['ready', 'dirty'],
      warnings: [],
    }));
    await first;
    await waitFor(() => expect(setStep).toHaveBeenCalledTimes(2));
    await act(async () => newSave.resolve({
      step: step(1, {params: {dose: 120}, runtimeStatus: 'dirty'}),
      statuses: ['ready', 'dirty'],
      warnings: [],
    }));
    await second;

    expect(setStep).toHaveBeenNthCalledWith(
      1,
      {index: 1, params: {dose: 110}},
      expect.any(AbortSignal),
    );
    expect(captured?.state.recipe[1].params.dose).toBe(120);
    expect(captured?.state.drafts['1:dose']).toBeUndefined();
  });

  it('跨字段保存同样串行，后端完整 step 响应不会反序覆盖', async () => {
    const firstSave = deferred<SetStepView>();
    const secondSave = deferred<SetStepView>();
    const setStep = vi.fn()
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise);
    const api = apiStub({setStep});
    mount(api);
    await waitUntilReady();

    act(() => captured!.actions.updateDraft(1, 'dose', 120, {status: 'valid'}));
    const doseSave = captured!.actions.saveParameter(1, 'dose');
    await waitFor(() => expect(setStep).toHaveBeenCalledTimes(1));
    act(() => captured!.actions.updateDraft(1, 'temperature', 350, {status: 'valid'}));
    const temperatureSave = captured!.actions.saveParameter(1, 'temperature');

    expect(setStep).toHaveBeenCalledTimes(1);
    await act(async () => captured!.actions.runAll());
    expect(api.runAll).not.toHaveBeenCalled();
    await act(async () => firstSave.resolve({
      step: step(1, {params: {dose: 120, temperature: 300}, runtimeStatus: 'dirty'}),
      statuses: ['ready', 'dirty'],
      warnings: [],
    }));
    await doseSave;
    await waitFor(() => expect(setStep).toHaveBeenCalledTimes(2));
    await act(async () => secondSave.resolve({
      step: step(1, {params: {dose: 120, temperature: 350}, runtimeStatus: 'dirty'}),
      statuses: ['ready', 'dirty'],
      warnings: [],
    }));
    await temperatureSave;

    expect(captured?.state.recipe[1].params).toEqual({dose: 120, temperature: 350});
  });

  it('存在执行中或排队保存时 run 与 restore 均不发起请求', async () => {
    const pendingSave = deferred<SetStepView>();
    const api = apiStub({setStep: vi.fn(() => pendingSave.promise)});
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());
    await act(async () => captured!.actions.restoreTimeline(0));
    expect(captured?.state.historicalStepIndex).toBe(0);

    act(() => captured!.actions.updateDraft(0, 'dose', 130, {status: 'valid'}));
    const save = captured!.actions.saveParameter(0, 'dose');
    await waitFor(() => expect(api.setStep).toHaveBeenCalledTimes(1));

    await act(async () => {
      await captured!.actions.runAll();
      await captured!.actions.restoreTimeline(0);
    });
    expect(api.runAll).not.toHaveBeenCalled();
    expect(api.restoreTimeline).toHaveBeenCalledTimes(1);
    expect(captured?.state.historicalStepIndex).toBe(0);

    await act(async () => pendingSave.resolve({
      step: step(0, {params: {dose: 130}}),
      statuses: ['dirty', 'ready'],
      warnings: [],
    }));
    await save;
  });

  it('mutation 期间 standalone loadTimeline 直接返回', async () => {
    const pendingRun = deferred<RunView>();
    const api = apiStub({runAll: vi.fn(() => pendingRun.promise)});
    mount(api);
    await waitUntilReady();

    const operation = captured!.actions.runAll();
    await waitFor(() => expect(api.runAll).toHaveBeenCalledTimes(1));
    await act(async () => captured!.actions.loadTimeline());
    expect(api.getTimeline).not.toHaveBeenCalled();

    await act(async () => pendingRun.resolve({modelRevision: 22}));
    await operation;
    expect(api.getTimeline).toHaveBeenCalledTimes(1);
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
  it('历史恢复失败时继续显示原历史步骤', async () => {
    const restoreTimeline = vi.fn()
      .mockResolvedValueOnce({
        timeline: {...timeline, current: 0},
        model: initView.model,
        recipe: initView.recipe,
        log: [],
      } satisfies TimelineRestoreView)
      .mockRejectedValueOnce(new TcadApiError('恢复失败', {status: 409}));
    const api = apiStub({restoreTimeline});
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());
    await act(async () => captured!.actions.restoreTimeline(0));
    expect(captured?.state.historicalStepIndex).toBe(0);

    await act(async () => captured!.actions.restoreTimeline(0));

    expect(captured?.state.historicalStepIndex).toBe(0);
    expect(captured?.state.globalError?.message).toBe('恢复失败');
  });

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

  it('新 Timeline load 取消旧请求，旧响应即使晚到也不能覆盖', async () => {
    const oldLoad = deferred<TimelineView>();
    const newLoad = deferred<TimelineView>();
    const signals: AbortSignal[] = [];
    const api = apiStub({
      getTimeline: vi.fn((_signal?: AbortSignal) => {
        if (_signal) signals.push(_signal);
        return signals.length === 1 ? oldLoad.promise : newLoad.promise;
      }),
    });
    mount(api);
    await waitUntilReady();

    const first = captured!.actions.loadTimeline();
    await waitFor(() => expect(api.getTimeline).toHaveBeenCalledTimes(1));
    const second = captured!.actions.loadTimeline();
    await waitFor(() => expect(api.getTimeline).toHaveBeenCalledTimes(2));
    expect(signals[0].aborted).toBe(true);

    const newest = {...timeline, current: 0};
    await act(async () => newLoad.resolve(newest));
    await second;
    await act(async () => oldLoad.resolve({...timeline, current: 1}));
    await first;
    expect(captured?.state.timeline?.current).toBe(0);
  });

  it('standalone Timeline 旧响应不能覆盖随后 restore 的结果', async () => {
    const staleLoad = deferred<TimelineView>();
    const staleSignals: AbortSignal[] = [];
    const getTimeline = vi.fn()
      .mockResolvedValueOnce(timeline)
      .mockImplementationOnce((signal?: AbortSignal) => {
        if (signal) staleSignals.push(signal);
        return staleLoad.promise;
      });
    const api = apiStub({getTimeline});
    mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());

    const stale = captured!.actions.loadTimeline();
    await waitFor(() => expect(getTimeline).toHaveBeenCalledTimes(2));
    await act(async () => captured!.actions.restoreTimeline(0));
    expect(staleSignals[0].aborted).toBe(true);
    expect(captured?.state.timeline?.current).toBe(0);

    await act(async () => staleLoad.resolve({...timeline, current: 1}));
    await stale;
    expect(captured?.state.timeline?.current).toBe(0);
  });

  it('Timeline 失败后 retry 成功会清除对应 globalError', async () => {
    const getTimeline = vi.fn()
      .mockRejectedValueOnce(new TcadApiError('时间线暂不可用', {status: 503}))
      .mockResolvedValueOnce({...timeline, current: 0});
    const api = apiStub({getTimeline});
    mount(api);
    await waitUntilReady();

    await act(async () => captured!.actions.loadTimeline());
    expect(captured?.state.globalError?.message).toBe('时间线暂不可用');
    await act(async () => captured!.actions.loadTimeline());
    expect(captured?.state.timeline?.current).toBe(0);
    expect(captured?.state.globalError).toBeNull();
  });

  it('unmount 会 abort bootstrap 请求且不发布失败态', async () => {
    const pending = deferred<InitView>();
    let signal: AbortSignal | undefined;
    const api = apiStub({
      init: vi.fn((requestSignal?: AbortSignal) => {
        signal = requestSignal;
        return pending.promise;
      }),
    });
    const mounted = mount(api);
    await waitFor(() => expect(signal).toBeDefined());

    mounted.unmount();
    await waitFor(() => expect(signal?.aborted).toBe(true));
    await act(async () => pending.reject(new DOMException('aborted', 'AbortError')));
  });

  it('unmount 会 abort save 请求且不写入响应', async () => {
    const pending = deferred<SetStepView>();
    let signal: AbortSignal | undefined;
    const api = apiStub({
      setStep: vi.fn((_request, requestSignal?: AbortSignal) => {
        signal = requestSignal;
        return pending.promise;
      }),
    });
    const mounted = mount(api);
    await waitUntilReady();
    act(() => captured!.actions.updateDraft(0, 'dose', 140, {status: 'valid'}));
    const operation = captured!.actions.saveParameter(0, 'dose');
    await waitFor(() => expect(signal).toBeDefined());

    mounted.unmount();
    await waitFor(() => expect(signal?.aborted).toBe(true));
    await act(async () => pending.reject(new DOMException('aborted', 'AbortError')));
    await operation;
  });

  it('unmount 会 abort standalone Timeline 请求', async () => {
    const pending = deferred<TimelineView>();
    let signal: AbortSignal | undefined;
    const api = apiStub({
      getTimeline: vi.fn((requestSignal?: AbortSignal) => {
        signal = requestSignal;
        return pending.promise;
      }),
    });
    const mounted = mount(api);
    await waitUntilReady();
    const operation = captured!.actions.loadTimeline();
    await waitFor(() => expect(signal).toBeDefined());

    mounted.unmount();
    await waitFor(() => expect(signal?.aborted).toBe(true));
    await act(async () => pending.reject(new DOMException('aborted', 'AbortError')));
    await operation;
  });

  it('unmount 会 abort restore 请求', async () => {
    const pending = deferred<TimelineRestoreView>();
    let signal: AbortSignal | undefined;
    const api = apiStub({
      restoreTimeline: vi.fn((_index, requestSignal?: AbortSignal) => {
        signal = requestSignal;
        return pending.promise;
      }),
    });
    const mounted = mount(api);
    await waitUntilReady();
    await act(async () => captured!.actions.loadTimeline());
    const operation = captured!.actions.restoreTimeline(0);
    await waitFor(() => expect(signal).toBeDefined());

    mounted.unmount();
    await waitFor(() => expect(signal?.aborted).toBe(true));
    await act(async () => pending.reject(new DOMException('aborted', 'AbortError')));
    await operation;
  });

  it('unmount 后异步完成不会 dispatch 或产生 React 警告', async () => {
    const pending = deferred<RunView>();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let signal: AbortSignal | undefined;
    const api = apiStub({
      runAll: vi.fn((requestSignal?: AbortSignal) => {
        signal = requestSignal;
        return pending.promise;
      }),
    });
    const mounted = mount(api);
    await waitUntilReady();
    const operation = captured!.actions.runAll();
    await waitFor(() => expect(signal).toBeDefined());
    mounted.unmount();
    await waitFor(() => expect(signal?.aborted).toBe(true));

    await act(async () => pending.resolve({modelRevision: 99}));
    await operation;
    expect(api.getTimeline).not.toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
