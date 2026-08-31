import {act, fireEvent, render, screen} from '@testing-library/react';
import {StrictMode, useMemo} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {TcadApiError} from '../api/client';
import type {
  InitView,
  RuntimeStatus,
  SetStepView,
  StepView,
  TcadApi,
} from '../api/types';
import {AppStateProvider, useAppState} from '../state/AppStateContext';
import {ParameterPanel} from './ParameterPanel';

function step(index: number, overrides: Partial<StepView> = {}): StepView {
  return {
    index,
    name: `step-${index}`,
    instanceName: `Step ${index}`,
    group: '',
    loop: '',
    enabled: true,
    params: {dose: 100 + index},
    parameterSpecs: [{
      key: 'dose',
      label: 'Dose',
      type: 'float',
      minimum: 0,
      maximum: 500,
      step: 0.1,
      decimals: 1,
      units: 'mJ/cm²',
      tooltip: '曝光剂量',
    }],
    runtimeStatus: 'ready',
    ...overrides,
  };
}

function init(recipe: StepView[] = [step(0), step(1)]): InitView {
  return {
    recipe,
    model: {gridShape: [8, 8, 8], voxelSizeNm: 10},
    factories: ['step-0'],
    materials: [],
    uiState: {},
  };
}

function apiStub(initial: InitView, overrides: Partial<TcadApi> = {}): TcadApi {
  return {
    init: vi.fn(async () => initial),
    setStep: vi.fn(async request => ({
      step: {
        ...initial.recipe[request.index],
        params: {...initial.recipe[request.index].params, ...request.params},
      },
      statuses: initial.recipe.map(() => 'dirty' as RuntimeStatus),
      warnings: [],
    })),
    runStep: vi.fn(async () => ({})),
    runTo: vi.fn(async () => ({})),
    runAll: vi.fn(async () => ({})),
    getTimeline: vi.fn(async () => ({items: [], current: -1})),
    restoreTimeline: vi.fn(async () => ({
      timeline: {items: [], current: -1},
      model: initial.model,
      recipe: initial.recipe,
      log: [],
    })),
    getPreviewManifest: vi.fn(async () => ({revision: 1, meshes: []})),
    getMaterialStl: vi.fn(async () => new ArrayBuffer(0)),
    ...overrides,
  };
}

function Harness() {
  const {state, actions} = useAppState();
  const selected = useMemo(
    () => state.recipe.find(item => item.index === state.selectedStepIndex) ?? null,
    [state.recipe, state.selectedStepIndex],
  );
  return (
    <>
      <button type="button" onClick={() => actions.selectStep(1)}>选择步骤 1</button>
      <button type="button" onClick={() => actions.selectStep(0)}>选择步骤 0</button>
      <button type="button" onClick={() => void actions.runAll()}>开始运行</button>
      <output data-testid="statuses">
        {state.recipe.map(item => item.runtimeStatus).join(',')}
      </output>
      <ParameterPanel step={selected} collapsed={false} />
    </>
  );
}

async function mount(initial: InitView, api = apiStub(initial), strict = false) {
  const tree = (
    <AppStateProvider api={api}>
      <Harness />
    </AppStateProvider>
  );
  const result = render(strict ? <StrictMode>{tree}</StrictMode> : tree);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  return {...result, api};
}

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('ParameterPanel', () => {
  it('合法值 349ms 不保存，到 350ms 才保存', async () => {
    vi.useFakeTimers();
    const initial = init();
    const {api, unmount} = await mount(initial);
    const input = screen.getByLabelText('Dose');

    fireEvent.change(input, {target: {value: '125'}});
    await act(async () => vi.advanceTimersByTimeAsync(349));
    expect(api.setStep).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTimeAsync(1));

    expect(api.setStep).toHaveBeenCalledTimes(1);
    expect(api.setStep).toHaveBeenCalledWith(
      {index: 0, params: {dose: 125}},
      expect.any(AbortSignal),
    );
    unmount();
  });

  it('blur 清除 debounce 并立即保存一次', async () => {
    vi.useFakeTimers();
    const initial = init();
    const {api, unmount} = await mount(initial);
    const input = screen.getByLabelText('Dose');

    fireEvent.change(input, {target: {value: '130'}});
    fireEvent.blur(input);
    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTimeAsync(350));

    expect(api.setStep).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('Enter 后紧接 blur 也不会重复提交', async () => {
    vi.useFakeTimers();
    const initial = init();
    const {api, unmount} = await mount(initial);
    const input = screen.getByLabelText('Dose');

    fireEvent.change(input, {target: {value: '131'}});
    fireEvent.keyDown(input, {key: 'Enter'});
    fireEvent.blur(input);
    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTimeAsync(350));

    expect(api.setStep).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('非法输入显示字段错误且 blur 和 debounce 都不请求', async () => {
    vi.useFakeTimers();
    const initial = init();
    const {api, unmount} = await mount(initial);
    const input = screen.getByLabelText('Dose');

    fireEvent.change(input, {target: {value: '600'}});
    fireEvent.blur(input);
    await act(async () => vi.advanceTimersByTimeAsync(500));

    expect(api.setStep).not.toHaveBeenCalled();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('必须小于或等于 500')).toBeInTheDocument();
    unmount();
  });

  it('保存失败保留原始文本并显示 parameter path 与 suggestion', async () => {
    vi.useFakeTimers();
    const initial = init();
    const error = new TcadApiError('剂量不符合服务端约束', {
      status: 400,
      parameterPath: 'params.dose',
      suggestion: '请输入经校准的剂量',
    });
    const api = apiStub(initial, {setStep: vi.fn(async () => { throw error; })});
    const {unmount} = await mount(initial, api);
    const input = screen.getByLabelText('Dose');

    fireEvent.change(input, {target: {value: '125.'}});
    await act(async () => vi.advanceTimersByTimeAsync(350));

    expect(api.setStep).toHaveBeenCalledWith(
      {index: 0, params: {dose: 125}},
      expect.any(AbortSignal),
    );
    expect(input).toHaveValue('125.');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.getAttribute('aria-describedby')).toContain('parameter-server-error-0-dose');
    expect(screen.getByText('剂量不符合服务端约束')).toBeInTheDocument();
    expect(screen.getByText('参数路径：params.dose')).toBeInTheDocument();
    expect(screen.getByText('建议：请输入经校准的剂量')).toBeInTheDocument();
    unmount();
  });

  it('保存失败后切换步骤再返回仍显示原始 draft', async () => {
    vi.useFakeTimers();
    const initial = init();
    const error = new TcadApiError('剂量不符合服务端约束', {
      status: 400,
      parameterPath: 'params.dose',
    });
    const api = apiStub(initial, {setStep: vi.fn(async () => { throw error; })});
    const {unmount} = await mount(initial, api);

    fireEvent.change(screen.getByLabelText('Dose'), {target: {value: '125.'}});
    await act(async () => vi.advanceTimersByTimeAsync(350));
    fireEvent.click(screen.getByRole('button', {name: '选择步骤 1'}));
    fireEvent.click(screen.getByRole('button', {name: '选择步骤 0'}));

    expect(screen.getByLabelText('Dose')).toHaveValue('125.');
    expect(screen.getByText('剂量不符合服务端约束')).toBeInTheDocument();
    unmount();
  });

  it('切换步骤会取消旧步骤尚未触发的 debounce', async () => {
    vi.useFakeTimers();
    const initial = init();
    const {api, unmount} = await mount(initial);

    fireEvent.change(screen.getByLabelText('Dose'), {target: {value: '140'}});
    fireEvent.click(screen.getByRole('button', {name: '选择步骤 1'}));
    await act(async () => vi.advanceTimersByTimeAsync(350));

    expect(api.setStep).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Dose')).toHaveValue('101');
    unmount();
  });

  it('choice 用安全索引区分 string、number 与 null，bool 提交 boolean', async () => {
    vi.useFakeTimers();
    const richStep = step(0, {
      params: {mode: '1', enabledFlag: false},
      parameterSpecs: [
        {
          key: 'mode',
          label: 'Mode',
          type: 'choice',
          choices: [['1', '字符串 1'], [1, '数字 1'], [null, '空值']],
        },
        {key: 'enabledFlag', label: 'Enabled', type: 'bool'},
      ],
    });
    const initial = init([richStep]);
    const {api, unmount} = await mount(initial);

    fireEvent.change(screen.getByLabelText('Mode'), {target: {value: '1'}});
    fireEvent.blur(screen.getByLabelText('Mode'));
    await act(async () => Promise.resolve());
    fireEvent.click(screen.getByLabelText('Enabled'));
    fireEvent.blur(screen.getByLabelText('Enabled'));
    await act(async () => Promise.resolve());

    expect(api.setStep).toHaveBeenNthCalledWith(
      1,
      {index: 0, params: {mode: 1}},
      expect.any(AbortSignal),
    );
    fireEvent.change(screen.getByLabelText('Mode'), {target: {value: '2'}});
    fireEvent.blur(screen.getByLabelText('Mode'));
    await act(async () => Promise.resolve());
    fireEvent.change(screen.getByLabelText('Mode'), {target: {value: '0'}});
    fireEvent.blur(screen.getByLabelText('Mode'));
    await act(async () => Promise.resolve());

    expect(api.setStep).toHaveBeenNthCalledWith(
      2,
      {index: 0, params: {enabledFlag: true}},
      expect.any(AbortSignal),
    );
    expect(api.setStep).toHaveBeenNthCalledWith(
      3,
      {index: 0, params: {mode: null}},
      expect.any(AbortSignal),
    );
    expect(api.setStep).toHaveBeenNthCalledWith(
      4,
      {index: 0, params: {mode: '1'}},
      expect.any(AbortSignal),
    );
    unmount();
  });

  it('choice 按 Enter 立即保存并取消 debounce', async () => {
    vi.useFakeTimers();
    const choiceStep = step(0, {
      params: {mode: '1'},
      parameterSpecs: [{
        key: 'mode',
        label: 'Mode',
        type: 'choice',
        choices: [['1', '字符串 1'], [1, '数字 1']],
      }],
    });
    const initial = init([choiceStep]);
    const {api, unmount} = await mount(initial);
    const select = screen.getByLabelText('Mode');

    fireEvent.change(select, {target: {value: '1'}});
    expect(fireEvent.keyDown(select, {key: 'Enter'})).toBe(true);
    await act(async () => Promise.resolve());

    expect(api.setStep).toHaveBeenCalledTimes(1);
    expect(api.setStep).toHaveBeenCalledWith(
      {index: 0, params: {mode: 1}},
      expect.any(AbortSignal),
    );
    await act(async () => vi.advanceTimersByTimeAsync(350));
    expect(api.setStep).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('卸载会取消尚未触发的 debounce', async () => {
    vi.useFakeTimers();
    const initial = init();
    const {api, unmount} = await mount(initial);

    fireEvent.change(screen.getByLabelText('Dose'), {target: {value: '145'}});
    unmount();
    await act(async () => vi.advanceTimersByTimeAsync(350));

    expect(api.setStep).not.toHaveBeenCalled();
  });

  it('StrictMode effect 重放后 debounce 仍只保存一次', async () => {
    vi.useFakeTimers();
    const initial = init();
    const api = apiStub(initial);
    const {unmount} = await mount(initial, api, true);

    fireEvent.change(screen.getByLabelText('Dose'), {target: {value: '146'}});
    await act(async () => vi.advanceTimersByTimeAsync(350));

    expect(api.setStep).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('运行期间控件禁用且不触发参数保存', async () => {
    vi.useFakeTimers();
    let resolveRun!: () => void;
    const run = new Promise<Record<string, never>>(resolve => { resolveRun = () => resolve({}); });
    const initial = init();
    const api = apiStub(initial, {runAll: vi.fn(() => run)});
    const {unmount} = await mount(initial, api);

    fireEvent.click(screen.getByRole('button', {name: '开始运行'}));
    await act(async () => Promise.resolve());
    const input = screen.getByLabelText('Dose');
    expect(input).toBeDisabled();
    fireEvent.change(input, {target: {value: '150'}});
    await act(async () => vi.advanceTimersByTimeAsync(350));
    expect(api.setStep).not.toHaveBeenCalled();

    await act(async () => resolveRun());
    unmount();
  });

  it('保存成功采用服务端 step 与 statuses，不自行推断 Dirty', async () => {
    vi.useFakeTimers();
    const initial = init();
    const response: SetStepView = {
      step: step(0, {params: {dose: 160}, runtimeStatus: 'ready'}),
      statuses: ['done', 'error'],
      warnings: [],
    };
    const api = apiStub(initial, {setStep: vi.fn(async () => response)});
    const {unmount} = await mount(initial, api);

    fireEvent.change(screen.getByLabelText('Dose'), {target: {value: '160'}});
    fireEvent.blur(screen.getByLabelText('Dose'));
    await act(async () => Promise.resolve());

    expect(screen.getByTestId('statuses')).toHaveTextContent('done,error');
    unmount();
  });

  it('未知类型安全显示复杂初始值且不出现 object Object', async () => {
    const unknownStep = step(0, {
      params: {future: {mode: 'safe'}},
      parameterSpecs: [{key: 'future', label: 'Future', type: 'future-type'}],
    });
    const initial = init([unknownStep]);
    const {unmount} = await mount(initial);

    expect(screen.getByLabelText('Future')).toHaveValue('{"mode":"safe"}');
    expect(screen.queryByDisplayValue('[object Object]')).not.toBeInTheDocument();
    expect(document.getElementById('parameter-0-future-units')).toBeNull();
    unmount();
  });

  it('units 使用稳定 id 并关联到对应控件', async () => {
    const initial = init();
    const {unmount} = await mount(initial);
    const input = screen.getByLabelText('Dose');
    const units = screen.getByText('mJ/cm²');

    expect(units).toHaveAttribute('id', 'parameter-0-dose-units');
    expect(input.getAttribute('aria-describedby')?.split(' ')).toContain(units.id);
    unmount();
  });
});
