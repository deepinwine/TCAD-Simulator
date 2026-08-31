import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {StrictMode} from 'react';
import {describe, expect, it, vi} from 'vitest';
import {App} from '../App';
import {TcadApiError} from '../api/client';
import type {
  InitView,
  RuntimeStatus,
  StepView,
  TcadApi,
  TimelineRestoreView,
  TimelineView,
} from '../api/types';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(resolvePromise => {
    resolve = resolvePromise;
  });
  return {promise, resolve};
}

function step(index: number, overrides: Partial<StepView> = {}): StepView {
  return {
    index,
    name: `step-${index}`,
    instanceName: `Step ${index + 1}`,
    group: '',
    loop: '',
    enabled: true,
    params: {},
    parameterSpecs: [],
    runtimeStatus: 'ready',
    ...overrides,
  };
}

const recipe = [step(0), step(1), step(2), step(3)];

const initView: InitView = {
  recipe,
  model: {gridShape: [8, 8, 8], voxelSizeNm: 10},
  factories: ['deposit'],
  materials: [],
  uiState: {},
};

const timeline: TimelineView = {
  current: 1,
  items: [
    {index: 0, state: 'done', runtimeStatus: 'done', snapshotValid: true},
    {index: 1, state: 'current', runtimeStatus: 'done', snapshotValid: false},
    {index: 2, state: 'dirty', runtimeStatus: 'dirty', snapshotValid: false},
    {index: 3, state: 'ready', runtimeStatus: 'ready', snapshotValid: true},
  ],
};

function restored(index: number): TimelineRestoreView {
  return {
    timeline: {...timeline, current: index},
    model: initView.model,
    recipe,
    log: ['restored'],
  };
}

function apiStub(overrides: Partial<TcadApi> = {}): TcadApi {
  return {
    init: vi.fn(async () => initView),
    setStep: vi.fn(async request => ({
      step: recipe[request.index],
      statuses: recipe.map(() => 'ready' as RuntimeStatus),
      warnings: [],
    })),
    runStep: vi.fn(async () => ({})),
    runTo: vi.fn(async () => ({})),
    runAll: vi.fn(async () => ({})),
    getTimeline: vi.fn(async () => timeline),
    restoreTimeline: vi.fn(async index => restored(index)),
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

describe('TimelineBar', () => {
  it('ready 后在 StrictMode 中也只初始加载一次 Timeline', async () => {
    const api = apiStub();
    render(<StrictMode><App api={api} viewerRuntimeFactory={stubViewerRuntime} /></StrictMode>);

    await screen.findByRole('button', {name: '恢复步骤 1'});
    expect(api.getTimeline).toHaveBeenCalledTimes(1);
  });

  it('显示加载、失败与可访问 retry', async () => {
    const getTimeline = vi.fn()
      .mockRejectedValueOnce(new TcadApiError('Timeline 暂不可用', {status: 503}))
      .mockResolvedValueOnce(timeline);
    const api = apiStub({getTimeline});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Timeline 暂不可用');
    fireEvent.click(screen.getByRole('button', {name: '重试 Timeline'}));

    expect(await screen.findByRole('button', {name: '恢复步骤 1'})).toBeEnabled();
    expect(getTimeline).toHaveBeenCalledTimes(2);
  });

  it('初始请求挂起时显示可访问 loading 状态', async () => {
    const pending = deferred<TimelineView>();
    const api = apiStub({getTimeline: vi.fn(() => pending.promise)});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    expect(await screen.findByText('正在加载 Timeline…')).toHaveAttribute('role', 'status');
    expect(screen.getByRole('navigation', {name: 'Process Timeline'})).toHaveAttribute(
      'aria-busy',
      'true',
    );
    pending.resolve(timeline);
    await screen.findByRole('button', {name: '恢复步骤 1'});
  });

  it('只允许恢复有效快照，Previous 与 Next 跳过无效节点', async () => {
    const api = apiStub();
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    expect(await screen.findByRole('button', {name: '恢复步骤 1'})).toBeEnabled();
    expect(screen.getByRole('button', {name: '恢复步骤 2'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '恢复步骤 3'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '恢复步骤 4'})).toBeEnabled();

    fireEvent.click(screen.getByRole('button', {name: '上一个有效快照'}));
    await waitFor(() => expect(api.restoreTimeline).toHaveBeenCalledWith(
      0,
      expect.any(AbortSignal),
    ));
    expect(api.runStep).not.toHaveBeenCalled();
    expect(api.runTo).not.toHaveBeenCalled();
    expect(api.runAll).not.toHaveBeenCalled();
  });

  it('Next 跳过无效节点，成功后显示历史快照并刷新 Viewer', async () => {
    const api = apiStub();
    const viewerRuntime = recordingViewerRuntime();
    render(<App api={api} viewerRuntimeFactory={viewerRuntime.factory} />);
    await screen.findByRole('button', {name: '恢复步骤 4'});
    await waitFor(() => expect(viewerRuntime.loadedTokens).toEqual([1]));

    fireEvent.click(screen.getByRole('button', {name: '下一个有效快照'}));

    await waitFor(() => expect(api.restoreTimeline).toHaveBeenCalledWith(
      3,
      expect.any(AbortSignal),
    ));
    expect(await screen.findByText('历史快照 Step 4')).toBeVisible();
    await waitFor(() => expect(viewerRuntime.loadedTokens).toEqual([1, 2]));
  });

  it('restore 同步 gate 防止双击并禁用全部恢复操作', async () => {
    const pending = deferred<TimelineRestoreView>();
    const restoreTimeline = vi.fn(() => pending.promise);
    const api = apiStub({restoreTimeline});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    const restore = await screen.findByRole('button', {name: '恢复步骤 1'});

    fireEvent.click(restore);
    fireEvent.click(restore);

    await waitFor(() => expect(restoreTimeline).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', {name: '恢复步骤 4'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '上一个有效快照'})).toBeDisabled();
    pending.resolve(restored(0));
    await screen.findByText('历史快照 Step 1');
  });

  it('restore 失败保持当前位置与最后成功几何，并可见结构化错误', async () => {
    const api = apiStub({
      restoreTimeline: vi.fn(async () => {
        throw new TcadApiError('快照恢复失败', {
          status: 409,
          suggestion: '请选择其他有效快照',
          rolledBack: false,
        });
      }),
    });
    const viewerRuntime = recordingViewerRuntime();
    render(<App api={api} viewerRuntimeFactory={viewerRuntime.factory} />);
    await screen.findByRole('button', {name: '恢复步骤 1'});
    await waitFor(() => expect(viewerRuntime.loadedTokens).toEqual([1]));

    fireEvent.click(screen.getByRole('button', {name: '恢复步骤 1'}));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('快照恢复失败');
    expect(alert).toHaveTextContent('请选择其他有效快照');
    expect(screen.getByText('#2 current').closest('li')).toHaveAttribute('aria-current', 'step');
    // restore 失败不刷新几何：仍只有初始加载
    expect(viewerRuntime.loadedTokens).toEqual([1]);
  });

  it('current=-1 时 Previous 安全禁用，Next 指向第一个有效节点', async () => {
    const noCurrent = {...timeline, current: -1};
    const api = apiStub({getTimeline: vi.fn(async () => noCurrent)});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '恢复步骤 1'});

    expect(screen.getByRole('button', {name: '上一个有效快照'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '下一个有效快照'})).toBeEnabled();
    fireEvent.click(screen.getByRole('button', {name: '下一个有效快照'}));
    await waitFor(() => expect(api.restoreTimeline).toHaveBeenCalledWith(
      0,
      expect.any(AbortSignal),
    ));
  });

  it('无序重复 Timeline 使用首项语义且只渲染一个节点，导航跳过无效项', async () => {
    const unordered: TimelineView = {
      current: 1,
      items: [
        {index: 3, state: 'ready', runtimeStatus: 'ready', snapshotValid: true},
        {index: 1, state: 'first-invalid', runtimeStatus: 'done', snapshotValid: false},
        {index: 1, state: 'duplicate-valid', runtimeStatus: 'error', snapshotValid: true},
        {index: 0, state: 'done', runtimeStatus: 'done', snapshotValid: true},
      ],
    };
    const api = apiStub({getTimeline: vi.fn(async () => unordered)});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    const duplicate = await screen.findAllByRole('button', {name: '恢复步骤 2'});
    expect(duplicate).toHaveLength(1);
    expect(duplicate[0]).toBeDisabled();
    expect(screen.getByText('#2 first-invalid').closest('li')).toHaveAttribute(
      'aria-current',
      'step',
    );
    expect(screen.getAllByRole('listitem').map(item => item.textContent?.slice(0, 2)))
      .toEqual(['#1', '#2', '#4']);

    fireEvent.click(screen.getByRole('button', {name: '上一个有效快照'}));
    await waitFor(() => expect(api.restoreTimeline).toHaveBeenCalledWith(
      0,
      expect.any(AbortSignal),
    ));
  });

  it('底栏错误使用紧凑容器渲染，超长消息不丢失且 retry 可达', async () => {
    const longMessage = 'x'.repeat(600);
    const getTimeline = vi.fn()
      .mockRejectedValue(new TcadApiError(longMessage, {status: 500}));
    const api = apiStub({getTimeline});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);

    const alert = await screen.findByRole('alert');
    const compact = alert.closest('.timeline-error');
    expect(compact).not.toBeNull();
    expect(alert).toHaveTextContent('Timeline 加载失败');
    expect(alert).toHaveTextContent(longMessage);
    const retry = screen.getByRole('button', {name: '重试 Timeline'});
    expect(retry).toBeEnabled();
    expect(compact).toContainElement(retry);
  });

  it('current 不存在时按 -1 计算 Next，不保留伪 aria-current', async () => {
    const missingCurrent: TimelineView = {
      current: 8,
      items: [
        {index: 3, state: 'ready', runtimeStatus: 'ready', snapshotValid: true},
        {index: 1, state: 'done', runtimeStatus: 'done', snapshotValid: false},
      ],
    };
    const api = apiStub({getTimeline: vi.fn(async () => missingCurrent)});
    render(<App api={api} viewerRuntimeFactory={stubViewerRuntime} />);
    await screen.findByRole('button', {name: '恢复步骤 2'});

    expect(screen.queryByRole('listitem', {current: 'step'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: '上一个有效快照'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: '下一个有效快照'}));
    await waitFor(() => expect(api.restoreTimeline).toHaveBeenCalledWith(
      3,
      expect.any(AbortSignal),
    ));
  });
});
