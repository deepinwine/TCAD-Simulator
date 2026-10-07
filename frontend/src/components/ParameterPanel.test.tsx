import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
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
import {MaskControl} from './MaskControl';
import {ErrorNotice} from './ErrorNotice';
import {I18nProvider, useI18n} from '../i18n/I18nContext';

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
      {state.globalError !== null && <ErrorNotice title="操作失败" error={state.globalError} />}
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

it.each([[1, '0'], [2, '1'], [14, '2']])('renders numeric Structure material ID %s and saves a changed material name', async (id, selected) => {
  const initial = init([step(0, {name: 'Structure Deposit', params: {material: id}, parameterSpecs: [{key: 'material', label: 'Material', type: 'enum', choices: [['Silicon', 'Silicon'], ['Silicon Dioxide', 'Silicon Dioxide'], ['Copper', 'Copper']]}]})]);
  initial.materials = [{id: 1, name: 'Silicon', color: [1,1,1], enabled: true}, {id: 2, name: 'Silicon Dioxide', color: [1,1,1], enabled: true}, {id: 14, name: 'Copper', color: [1,1,1], enabled: true}];
  const api = apiStub(initial, {setStep: vi.fn(async request => ({
    step: {...initial.recipe[0], params: {material: request.params?.material === 'Copper' ? 14 : 1}},
    statuses: ['dirty'], warnings: [],
  }))});
  await mount(initial, api);
  const material = screen.getByRole('combobox', {name: '材料'});
  expect(material).toHaveValue(selected);
  fireEvent.change(material, {target: {value: id === 14 ? '0' : '2'}});
  fireEvent.blur(material);
  await waitFor(() => expect(api.setStep).toHaveBeenCalledWith(expect.objectContaining({params: {material: id === 14 ? 'Silicon' : 'Copper'}}), expect.any(AbortSignal)));
  await waitFor(() => expect(material).toHaveValue(id === 14 ? '0' : '2'));
});

describe('Mask preview binding', () => {
  it('refreshes same-name revisions and retries failed previews when binding changes', async () => {
    const api = apiStub(init());
    const tree = (id: string, revision: number, index = 0) => (
      <AppStateProvider api={api}>
        <MaskControl stepIndex={index} maskName="M1" disabled={false} assetId={id} assetRevision={revision} />
      </AppStateProvider>
    );
    const view = render(tree('mask_a', 1));
    const image = screen.getByRole('img');
    const original = image.getAttribute('src');
    view.rerender(tree('mask_a', 2));
    expect(screen.getByRole('img').getAttribute('src')).not.toBe(original);
    fireEvent.error(screen.getByRole('img'));
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    view.rerender(tree('mask_b', 2));
    await waitFor(() => expect(screen.getByRole('img')).toBeInTheDocument());
    fireEvent.error(screen.getByRole('img'));
    view.rerender(tree('mask_b', 2, 1));
    await waitFor(() => expect(screen.getByRole('img')).toBeInTheDocument());
  });
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  localStorage.clear();
});

describe('per-field canonical units', () => {
  it.each(['s', 'µm', 'bogus'])('does not convert inconsistent length canonical unit %s', async canonicalUnit => {
    await mount(init([step(0, {params: {value: 1000}, parameterSpecs: [{key: 'value', label: 'Value', type: 'float', units: canonicalUnit, dimension: 'length', canonicalUnit, displayUnits: ['nm', 'µm']}]})]));
    expect(screen.queryByRole('combobox', {name: 'Value 单位'})).toBeNull();
    expect(screen.getByLabelText('Value')).toHaveValue('1000');
  });

  it('flushes the canonical draft once after edit, unit switch, unit blur, then permits runAll', async () => {
    vi.useFakeTimers();
    const initial = init([step(0, {params: {value: 1000}, parameterSpecs: [{key: 'value', label: 'Value', type: 'int', minimum: 1, maximum: 2000, dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm']}]})]);
    const {api} = await mount(initial);
    const input = screen.getByLabelText('Value');
    const unit = screen.getByRole('combobox', {name: 'Value 单位'});
    fireEvent.change(unit, {target: {value: 'µm'}});
    fireEvent.change(input, {target: {value: '0.5'}});
    expect(input).toHaveAttribute('aria-invalid', 'false');
    fireEvent.blur(input, {relatedTarget: unit});
    fireEvent.focus(unit);
    fireEvent.change(unit, {target: {value: 'nm'}});
    fireEvent.blur(unit);
    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTimeAsync(400));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(api.setStep).toHaveBeenCalledTimes(1);
    expect(input).toHaveValue('500.00');
    expect(api.setStep).toHaveBeenCalledWith(expect.objectContaining({params: {value: 500}}), expect.anything());
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: '开始运行'}));
      await Promise.resolve();
    });
    expect(api.runAll).toHaveBeenCalledTimes(1);
  });

  it('unit-only changes never save, including unit blur', async () => {
    const initial = init([step(0, {params: {value: 1000}, parameterSpecs: [{key: 'value', label: 'Value', type: 'float', dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm']}]})]);
    const {api} = await mount(initial);
    const unit = screen.getByRole('combobox', {name: 'Value 单位'});
    fireEvent.change(unit, {target: {value: 'µm'}});
    fireEvent.blur(unit);
    await act(async () => Promise.resolve());
    expect(api.setStep).not.toHaveBeenCalled();
  });

  it('does not display unrecognized capability values', async () => {
    const initial = {...init([step(0, {parameterSpecs: [{key: 'dose', label: 'Dose', type: 'float', capabilityKey: 'future'}]})]), backendCapabilities: {future: 'toString'}};
    await mount(initial);
    expect(screen.getByLabelText('Dose')).toBeVisible();
    expect(document.querySelector('.parameter-capability')).toBeNull();
  });
  it.each([
    ['length', 'nm', ['nm', 'µm'], 'µm', '1', 1000],
    ['time', 's', ['ms', 's', 'min'], 'min', '2', 120],
    ['angle', 'degree', ['°', 'rad'], 'rad', String(Math.PI), 180],
    ['rate', 'nm/s', ['nm/s', 'µm/min'], 'µm/min', '0.6', 10],
  ])('saves %s canonically', async (dimension, canonicalUnit, displayUnits, selectedUnit, raw, expected) => {
    const initial = init([step(0, {params: {value: 0}, parameterSpecs: [{key: 'value', label: 'Value', type: 'float', dimension: dimension as string, canonicalUnit: canonicalUnit as string, displayUnits: displayUnits as string[]}]})]);
    const {api} = await mount(initial);
    const selector = screen.getByRole('combobox', {name: 'Value 单位'});
    fireEvent.change(selector, {target: {value: selectedUnit}});
    expect(api.setStep).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Value'), {target: {value: raw}});
    fireEvent.blur(screen.getByLabelText('Value'));
    await waitFor(() => expect(api.setStep).toHaveBeenCalled());
    const sent = vi.mocked(api.setStep).mock.calls[0][0].params?.value;
    expect(sent).toBeCloseTo(expected as number, 10);
    expect(localStorage.getItem('tcad.unit.v1:step-0:value')).toBe(selectedUnit);
  });

  it('retains independent units and drafts across language changes, failed saves, and remounts', async () => {
    const initial = init([step(0, {params: {a: 1000, b: 2000}, parameterSpecs: ['a', 'b'].map(key => ({key, label: key, type: 'float', dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm'], decimals: 3}))}), step(1)]);
    const api = apiStub(initial, {setStep: vi.fn(async () => {throw new TcadApiError('failed', {status: 400});})});
    function LocaleSwitch() { const {setLocale} = useI18n(); return <button onClick={() => setLocale('en')}>English</button>; }
    localStorage.setItem('tcad.locale.v1', 'zh-CN');
    render(<I18nProvider><AppStateProvider api={api}><LocaleSwitch /><Harness /></AppStateProvider></I18nProvider>);
    const a = await screen.findByLabelText('a');
    fireEvent.change(screen.getByRole('combobox', {name: 'a 单位'}), {target: {value: 'µm'}});
    expect(a).toHaveValue('1.000');
    expect(screen.getByRole('combobox', {name: 'b 单位'})).toHaveValue('nm');
    fireEvent.change(a, {target: {value: '1.23456789'}});
    fireEvent.blur(a);
    await waitFor(() => expect(api.setStep).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('English'));
    expect(a).toHaveValue('1.23456789');
    expect(screen.getByRole('combobox', {name: 'a unit'})).toHaveValue('µm');
    fireEvent.click(screen.getByText('选择步骤 1'));
    fireEvent.click(screen.getByText('选择步骤 0'));
    expect(screen.getByLabelText('a')).toHaveValue('1.23456789');
    fireEvent.change(screen.getByRole('combobox', {name: 'a unit'}), {target: {value: 'nm'}});
    fireEvent.change(screen.getByRole('combobox', {name: 'a unit'}), {target: {value: 'µm'}});
    expect(screen.getByLabelText('a')).toHaveValue('1.235');
    expect(api.setStep).toHaveBeenCalledTimes(1);
    fireEvent.blur(screen.getByLabelText('a'));
    await waitFor(() => expect(api.setStep).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.setStep).mock.calls[1][0].params?.a).toBeCloseTo(1234.56789, 10);
  });

  it('shows unsupported capability and rejects nonzero incidence while keeping field editable', async () => {
    const initial = {...init([step(0, {params: {incidence: 0}, parameterSpecs: [{key: 'incidence', label: 'Incidence', type: 'float', dimension: 'angle', canonicalUnit: 'degree', displayUnits: ['°', 'rad'], capabilityKey: 'etch.incidence_angle'}]})]), backendCapabilities: {'etch.incidence_angle': 'unsupported'}};
    const {api} = await mount(initial);
    expect(screen.getByText('不支持')).toBeVisible();
    const input = screen.getByLabelText('Incidence');
    expect(input).toBeEnabled();
    fireEvent.change(input, {target: {value: '3'}});
    fireEvent.blur(input);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(api.setStep).not.toHaveBeenCalled();
  });

  it('allows clearing optional target depth to restore time mode', async () => {
    const initial = init([step(0, {params: {depth: 10}, parameterSpecs: [{key: 'depth', label: 'Depth', type: 'float', defaultValue: null, dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm']}]})]);
    const {api} = await mount(initial);
    fireEvent.change(screen.getByLabelText('Depth'), {target: {value: ''}});
    fireEvent.blur(screen.getByLabelText('Depth'));
    await waitFor(() => expect(api.setStep).toHaveBeenCalledWith(expect.objectContaining({params: {depth: null}}), expect.anything()));
  });
});

const maskInitView = (): InitView => ({
  recipe: [step(0), step(1), step(2)],
  model: {gridShape: [8, 8, 8], voxelSizeNm: 10},
  factories: [],
  materials: [],
  uiState: {},
});

describe('ParameterPanel 掩膜控件', () => {
  it('按稳定步骤名和参数键本地化帮助，未知帮助在中文下不泄露英文', async () => {
    const exposure = step(2, {
      name: 'Mask Exposure',
      params: {advanced_enable: 0, opc_enable: 1, future_option: 1},
      parameterSpecs: [
        {key: 'advanced_enable', label: 'Advanced', type: 'enum', choices: [[0, 'Off'], [1, 'On']], tooltip: 'When disabled, optical/dose/OPC override parameters are ignored.'},
        {key: 'opc_enable', label: 'OPC', type: 'enum', choices: [[0, 'Off'], [1, 'On']], tooltip: 'Lightweight OPC-style bias applied to procedural masks.'},
        {key: 'future_option', label: 'Future', type: 'float', tooltip: 'Future third-party technical help.'},
      ],
    });
    render(
      <AppStateProvider api={apiStub(init([exposure]))}>
        <ParameterPanel step={exposure} collapsed={false} />
      </AppStateProvider>,
    );
    expect(await screen.findByText('关闭时将忽略光学、剂量和 OPC 覆盖参数。')).toBeVisible();
    expect(screen.getByText('对程序化掩膜应用轻量级 OPC 偏置。')).toBeVisible();
    expect(screen.getByText('查看技术参数说明')).toBeVisible();
    expect(screen.queryByText('Future third-party technical help.')).not.toBeInTheDocument();
  });

  it('覆盖真实 SOI 与 Etch 稳定 tooltip 键', async () => {
    const etch = step(3, {
      name: 'Etch',
      params: {rate_model: 'Advanced', rate_override: 0, stop_on_material: ''},
      parameterSpecs: [
        {key: 'rate_model', label: 'Rate model', type: 'enum', choices: [['Advanced', 'Advanced']], tooltip: 'Advanced uses the built-in plasma proxy model.'},
        {key: 'rate_override', label: 'Override rate', type: 'float', tooltip: 'Optional: directly specify vertical etch rate.'},
        {key: 'stop_on_material', label: 'Stop', type: 'enum', choices: [['', 'None']], tooltip: 'If set, the etch will never remove this material.'},
      ],
    });
    render(
      <AppStateProvider api={apiStub(init([etch]))}>
        <ParameterPanel step={etch} collapsed={false} />
      </AppStateProvider>,
    );
    expect(await screen.findByText(/Advanced 使用内置等离子体代理模型/)).toBeVisible();
    expect(screen.getByText(/直接指定垂直刻蚀速率/)).toBeVisible();
    expect(screen.getByText(/刻蚀不会移除此材料/)).toBeVisible();
  });

  it('含 mask_mode 的步骤显示掩膜控件并触发上传', async () => {
    const exposure = step(2, {
      name: 'Mask Exposure',
      params: {mask_mode: 'Custom', mask_name: 'lines'},
    });
    const api = apiStub(maskInitView());
    render(
      <AppStateProvider api={api}>
        <ParameterPanel step={exposure} collapsed={false} />
      </AppStateProvider>,
    );
    const uploadButton = await screen.findByRole('button', {name: '上传掩膜'});
    expect(screen.getByText('lines')).toBeVisible();
    const img = document.querySelector('img.mask-preview') as HTMLImageElement;
    expect(img.getAttribute('src')).toContain('/api/mask/preview_step?step_index=2');

    const input = screen.getByLabelText('掩膜文件') as HTMLInputElement;
    fireEvent.change(input, {
      target: {files: [new File([new Uint8Array([1, 2])], 'lines.png', {type: 'image/png'})]},
    });
    await waitFor(() => expect(api.uploadMask).toHaveBeenCalledTimes(1));
  });

  it('无掩膜参数的步骤不渲染掩膜控件', async () => {
    render(
      <AppStateProvider api={apiStub(maskInitView())}>
        <ParameterPanel step={step(0, {name: 'Etch'})} collapsed={false} />
      </AppStateProvider>,
    );
    await screen.findByRole('region', {name: 'Parameters'});
    expect(screen.queryByRole('button', {name: '上传掩膜'})).toBeNull();
  });
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
    fireEvent.click(screen.getByRole('button', {name: '开始运行'}));
    expect(screen.getByText('请先修正无效参数，再运行工艺。')).toBeVisible();
    expect(api.runAll).not.toHaveBeenCalled();
    unmount();
  });

  it('保存失败保留输入 draft 并显示安全 parameter path', async () => {
    vi.useFakeTimers();
    const initial = init();
    const error = new TcadApiError('剂量不符合服务端约束', {
      status: 400,
      parameterPath: 'params["dose"]',
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
    expect(screen.getByText('发生未预期的错误。')).toBeInTheDocument();
    expect(screen.queryByText(/剂量不符合服务端约束/)).not.toBeInTheDocument();
    expect(screen.getByText('参数路径：params["dose"]')).toBeInTheDocument();
    expect(screen.queryByText('建议：请输入经校准的剂量')).not.toBeInTheDocument();
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
    expect(screen.getByText('发生未预期的错误。')).toBeInTheDocument();
    expect(screen.queryByText(/剂量不符合服务端约束/)).not.toBeInTheDocument();
    unmount();
  });

  it('保存失败后再次编辑会立即清除该字段旧服务端错误', async () => {
    vi.useFakeTimers();
    const initial = init();
    const error = new TcadApiError('旧剂量错误', {status: 400});
    const api = apiStub(initial, {setStep: vi.fn(async () => { throw error; })});
    const {unmount} = await mount(initial, api);
    const input = screen.getByLabelText('Dose');

    fireEvent.change(input, {target: {value: '125'}});
    await act(async () => vi.advanceTimersByTimeAsync(350));
    expect(screen.getByText('发生未预期的错误。')).toBeInTheDocument();
    expect(screen.queryByText(/旧剂量错误/)).not.toBeInTheDocument();

    fireEvent.change(input, {target: {value: '126'}});
    expect(screen.queryByText('发生未预期的错误。')).not.toBeInTheDocument();
    expect(input).toHaveAttribute('aria-invalid', 'false');
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

  it.each([
    [true, true],
    [1, true],
    ['1', true],
    ['true', true],
    ['yes', true],
    ['on', true],
    [false, false],
    [0, false],
    ['0', false],
    ['false', false],
    ['no', false],
    ['off', false],
  ])('bool legacy 初始值 %j 显示为 checked=%j', async (raw, checked) => {
    const booleanStep = step(0, {
      params: {enabledFlag: raw},
      parameterSpecs: [{key: 'enabledFlag', label: 'Enabled', type: 'bool'}],
    });
    const initial = init([booleanStep]);
    const {unmount} = await mount(initial);

    expect(screen.getByLabelText('Enabled')).toHaveProperty('checked', checked);
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
