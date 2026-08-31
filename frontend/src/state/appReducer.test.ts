import {describe, expect, it} from 'vitest';
import {TcadApiError} from '../api/client';
import type {
  InitView,
  RunView,
  SetStepView,
  StepView,
  TimelineRestoreView,
  TimelineView,
} from '../api/types';
import {appReducer, initialAppState} from './appReducer';

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
    {index: 1, state: 'current', runtimeStatus: 'ready', snapshotValid: true},
  ],
  current: 1,
};

function readyState() {
  return appReducer(initialAppState, {type: 'bootstrap/succeeded', payload: initView});
}

describe('appReducer bootstrap 与本地编辑', () => {
  it('bootstrap 成功后选择首步、进入 ready 并请求首轮预览', () => {
    const state = appReducer(initialAppState, {type: 'bootstrap/succeeded', payload: initView});

    expect(state.phase).toBe('ready');
    expect(state.selectedStepIndex).toBe(0);
    expect(state.recipe).toEqual(initView.recipe);
    expect(state.previewGeneration).toBe(1);
  });

  it('空 recipe 的 bootstrap 成功态不伪造选中步骤', () => {
    const state = appReducer(initialAppState, {
      type: 'bootstrap/succeeded',
      payload: {...initView, recipe: []},
    });

    expect(state.phase).toBe('ready');
    expect(state.selectedStepIndex).toBeNull();
  });

  it('bootstrap 失败进入可重试 fatal 并安全保存结构化错误', () => {
    const error = new TcadApiError('初始化失败', {status: 503, code: 'offline'});
    const state = appReducer(initialAppState, {type: 'bootstrap/failed', error});

    expect(state.phase).toBe('fatal');
    expect(state.globalError).toBe(error);

    const retrying = appReducer(state, {type: 'bootstrap/started'});
    expect(retrying.phase).toBe('booting');
    expect(retrying.globalError).toBeNull();
  });

  it('选择步骤只修改本地状态', () => {
    const state = appReducer(readyState(), {type: 'step/selected', index: 1});

    expect(state.selectedStepIndex).toBe(1);
    expect(state.recipe).toEqual(initView.recipe);
  });
});

describe('appReducer 参数序号', () => {
  it('保存成功只接受最新 field sequence 并使用服务端 step/statuses', () => {
    const editing = appReducer(readyState(), {
      type: 'parameter/draftChanged',
      index: 1,
      key: 'dose',
      value: 120,
      sequence: 2,
      validation: {status: 'valid'},
    });
    const stale = appReducer(editing, {
      type: 'parameter/saveSucceeded',
      index: 1,
      key: 'dose',
      sequence: 1,
      payload: {
        step: step(1, {params: {dose: 110}, runtimeStatus: 'dirty'}),
        statuses: ['done', 'dirty'],
        warnings: [],
      } satisfies SetStepView,
    });

    expect(stale.drafts['1:dose'].value).toBe(120);
    expect(stale.recipe).toEqual(editing.recipe);

    const accepted = appReducer(stale, {
      type: 'parameter/saveSucceeded',
      index: 1,
      key: 'dose',
      sequence: 2,
      payload: {
        step: step(1, {params: {dose: 120}, runtimeStatus: 'dirty'}),
        statuses: ['done', 'dirty'],
        warnings: [],
      },
    });
    expect(accepted.drafts['1:dose']).toBeUndefined();
    expect(accepted.recipe.map(item => item.runtimeStatus)).toEqual(['done', 'dirty']);
    expect(accepted.recipe[1].params.dose).toBe(120);
  });

  it('最新保存失败保留 draft、validation 和 rolledBack step error', () => {
    const error = new TcadApiError('剂量无效', {
      status: 400,
      parameterPath: 'params.dose',
      suggestion: '请输入正数',
      rolledBack: true,
    });
    const editing = appReducer(readyState(), {
      type: 'parameter/draftChanged',
      index: 1,
      key: 'dose',
      value: -1,
      sequence: 3,
      validation: {status: 'invalid', message: '必须为正数'},
    });
    const failed = appReducer(editing, {
      type: 'parameter/saveFailed',
      index: 1,
      key: 'dose',
      sequence: 3,
      error,
    });

    expect(failed.drafts['1:dose']).toEqual({
      value: -1,
      sequence: 3,
      validation: {status: 'invalid', message: '必须为正数'},
    });
    expect(failed.stepErrors[1]).toBe(error);
    expect(failed.stepErrors[1].rolledBack).toBe(true);
  });

  it('旧保存失败不能给更新后的 draft 写入错误', () => {
    const error = new TcadApiError('旧请求失败', {status: 400});
    const editing = appReducer(readyState(), {
      type: 'parameter/draftChanged',
      index: 1,
      key: 'dose',
      value: 120,
      sequence: 2,
      validation: {status: 'valid'},
    });
    const stale = appReducer(editing, {
      type: 'parameter/saveFailed',
      index: 1,
      key: 'dose',
      sequence: 1,
      error,
    });

    expect(stale).toBe(editing);
    expect(stale.stepErrors[1]).toBeUndefined();
  });
});

describe('appReducer 执行与 Timeline', () => {
  it('mutation gate 标记运行中，并在成功时只采用真实 revision 与目标状态', () => {
    const running = appReducer(readyState(), {
      type: 'run/started',
      operation: 'all',
    });
    expect(running.phase).toBe('running');
    expect(running.activeMutation).toBe('all');

    const response: RunView = {
      modelRevision: 42,
      index: 1,
      runtimeStatus: 'done',
      result: {server: 'authoritative'},
    };
    const succeeded = appReducer(running, {type: 'run/succeeded', payload: response});
    expect(succeeded.lastModelRevision).toBe(42);
    expect(succeeded.recipe[0].runtimeStatus).toBe('ready');
    expect(succeeded.recipe[1].runtimeStatus).toBe('done');
    expect(succeeded.lastRunResult).toEqual({server: 'authoritative'});
    expect(succeeded.previewGeneration).toBe(2);
    expect(succeeded.activeMutation).toBe('all');
  });

  it('未返回 modelRevision 时不覆盖已知 revision', () => {
    const withRevision = {...readyState(), lastModelRevision: 9};
    const state = appReducer(withRevision, {
      type: 'run/succeeded',
      payload: {skipped: true, reason: 'disabled'},
    });

    expect(state.lastModelRevision).toBe(9);
  });

  it('运行失败保留最后几何并映射结构化 step error', () => {
    const error = new TcadApiError('刻蚀失败', {
      status: 400,
      rolledBack: false,
      details: {stepIndex: 1},
    });
    const before = {...readyState(), previewGeneration: 7, lastModelRevision: 12};
    const failed = appReducer(before, {type: 'run/failed', index: 1, error});

    expect(failed.previewGeneration).toBe(7);
    expect(failed.lastModelRevision).toBe(12);
    expect(failed.stepErrors[1]).toBe(error);
    expect(failed.stepErrors[1].rolledBack).toBe(false);
  });

  it('Timeline load 与有效快照恢复采用服务端 current/recipe 并刷新预览', () => {
    const loaded = appReducer(readyState(), {type: 'timeline/loaded', payload: timeline});
    expect(loaded.timeline).toEqual(timeline);

    const restoredPayload: TimelineRestoreView = {
      timeline: {...timeline, current: -1},
      model: initView.model,
      recipe: [step(0, {runtimeStatus: 'done'}), step(1)],
      log: ['restored'],
    };
    const restored = appReducer({...loaded, lastModelRevision: 19}, {
      type: 'timeline/restoreSucceeded',
      payload: restoredPayload,
    });
    expect(restored.timeline?.current).toBe(-1);
    expect(restored.selectedStepIndex).toBeNull();
    expect(restored.recipe).toEqual(restoredPayload.recipe);
    expect(restored.lastModelRevision).toBe(19);
    expect(restored.previewGeneration).toBe(2);
  });

  it('Timeline 按 item.index 同步权威 runtimeStatus，重复项首个生效并忽略越界项', () => {
    const payload: TimelineView = {
      current: 1,
      items: [
        {index: 1, state: 'error-label-is-ignored', runtimeStatus: 'done', snapshotValid: true},
        {index: 1, state: 'duplicate', runtimeStatus: 'error', snapshotValid: false},
        {index: 99, state: 'out-of-range', runtimeStatus: 'error', snapshotValid: false},
        {index: 0, state: 'not-a-runtime-status', runtimeStatus: 'dirty', snapshotValid: true},
      ],
    };
    const loaded = appReducer(readyState(), {type: 'timeline/loaded', payload});

    expect(loaded.recipe.map(item => item.runtimeStatus)).toEqual(['dirty', 'done']);
    expect(loaded.timeline).toEqual(payload);
  });

  it('mutation 完成可靠释放 gate，但保留步骤错误', () => {
    const error = new TcadApiError('运行失败', {status: 400});
    const failed = appReducer(
      appReducer(readyState(), {type: 'run/started', operation: 'step'}),
      {type: 'run/failed', index: 0, error},
    );
    const finished = appReducer(failed, {type: 'mutation/finished'});

    expect(finished.phase).toBe('ready');
    expect(finished.activeMutation).toBeNull();
    expect(finished.stepErrors[0]).toBe(error);
  });
});
