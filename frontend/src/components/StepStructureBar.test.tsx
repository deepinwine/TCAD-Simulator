import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import type {
  InitView,
  RuntimeStatus,
  StepView,
  TcadApi,
} from '../api/types';
import {AppStateProvider} from '../state/AppStateContext';
import {StepStructureBar} from './StepStructureBar';
import {TcadApiError} from '../api/client';
import {ParameterPanel} from './ParameterPanel';
import {useAppState} from '../state/AppStateContext';
import {ProjectSettings} from './ProjectSettings';
import {I18nProvider} from '../i18n/I18nContext';
import {LanguageSwitcher} from './LanguageSwitcher';
import {processCatalog} from './processCatalog';
// Frozen factory metadata from _webui_serialize_step(PROCESS_STEP_FACTORIES[name](MaterialDatabase())).
import wireFactoryTemplates from '../test/structureFactoryTemplates.json';
import {parseStepEnvelope} from '../api/schemas';
const factoryTemplates = wireFactoryTemplates.map((template, index) => parseStepEnvelope({ok: true, result: template}, index));
function SelectionControls() {const {actions} = useAppState(); return <><button onClick={() => actions.selectStep(0)}>select 0</button><button onClick={() => actions.selectStep(1)}>select 1</button></>;}
function SelectedPanel() {const {state} = useAppState(); return <ParameterPanel step={state.recipe.find(item => item.index === state.selectedStepIndex) ?? null} collapsed={false} />;}

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

const initView = (): InitView => ({
  recipe: [step(0), step(1, {name: 'deposit'}), step(2)],
  model: {gridShape: [8, 8, 8], voxelSizeNm: 10},
  factories: ['Initialize Wafer', 'deposit'],
  materials: [],
  uiState: {},
});

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
    importRecipe: vi.fn(async () => ({
      model: initView().model,
      recipe: initView().recipe,
      currentRecipe: {name: '', id: ''},
      log: [],
    })),
    newRecipe: vi.fn(async () => ({
      model: initView().model,
      recipe: initView().recipe,
      currentRecipe: {name: '', id: ''},
      log: [],
    })),
    saveRecipe: vi.fn(async () => ({saved: true})),
    exportRecipe: vi.fn(async () => new Blob(['{}'])),
    loadRecipe: vi.fn(async () => ({
      model: initView().model,
      recipe: initView().recipe,
      currentRecipe: {name: '', id: ''},
      log: [],
    })),
    addStep: vi.fn(async () => initView().recipe),
    removeStep: vi.fn(async () => initView().recipe),
    duplicateStep: vi.fn(async () => initView().recipe),
    moveStep: vi.fn(async () => initView().recipe),
    renameStep: vi.fn(async index => step(Math.trunc(Number(index)))),
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
    getTimeline: vi.fn(async () => ({items: [], current: -1})),
    restoreTimeline: vi.fn(async () => ({
      timeline: {items: [], current: -1},
      model: initView().model,
      recipe: initView().recipe,
      log: [],
    })),
    getPreviewManifest: vi.fn(async () => ({revision: 1, meshes: []})),
    getMaterialStl: vi.fn(async () => new ArrayBuffer(0)),
    ...overrides,
  };
}

function mount(api: TcadApi) {
  return render(
    <AppStateProvider api={api}>
      <StepStructureBar />
    </AppStateProvider>,
  );
}

describe('配置结构步骤', () => {
  const template: StepView = step(0, {name: 'Structure Deposit', instanceName: 'Structure Deposit', params: {material: 'Silicon', thickness_nm: 100}, parameterSpecs: [{key: 'material', label: 'Material', type: 'enum', choices: [['Silicon', 'Silicon'], ['Silicon Dioxide', 'Silicon Dioxide']]}, {key: 'thickness_nm', label: 'Thickness', type: 'float', minimum: 0, units: 'nm', dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm']}]});
  it('配置后只发一次原子请求，取消不创建', async () => {
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [template], factories: ['Structure Deposit'], factoryTemplates: [template]}))});
    mount(api);
    await waitFor(() => expect(screen.getByLabelText('添加步骤类型')).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText('添加步骤类型'), {target: {value: 'Structure Deposit'}});
    fireEvent.click(screen.getByRole('button', {name: '添加步骤'}));
    expect(api.addStep).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: '取消'}));
    expect(api.addStep).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: '添加步骤'}));
    fireEvent.change(screen.getByLabelText('厚度（nm）'), {target: {value: '80'}});
    fireEvent.change(screen.getByLabelText('厚度单位'), {target: {value: 'µm'}});
    expect(screen.getByLabelText('厚度（µm）')).toHaveValue(0.08);
    fireEvent.change(screen.getByLabelText('材料'), {target: {value: '1'}});
    fireEvent.change(screen.getByLabelText('自定义名称（可选）'), {target: {value: 'Oxide cap'}});
    fireEvent.click(screen.getByRole('button', {name: '确认添加'}));
    await waitFor(() => expect(api.addStep).toHaveBeenCalledWith('Structure Deposit', expect.any(AbortSignal), {params: {material: 'Silicon Dioxide', thickness_nm: 80}, instanceName: 'Oxide cap'}));
    expect(api.addStep).toHaveBeenCalledTimes(1); expect(api.setStep).not.toHaveBeenCalled();
  });
  it('原子创建失败保留对话框和已填写参数供修正', async () => {
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [template], factories: ['Structure Deposit'], factoryTemplates: [template]})), addStep: vi.fn(async () => {throw new TcadApiError('invalid parameters', {status: 400});})});
    mount(api);
    await waitFor(() => expect(screen.getByLabelText('添加步骤类型')).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText('添加步骤类型'), {target: {value: 'Structure Deposit'}});
    fireEvent.click(screen.getByRole('button', {name: '添加步骤'}));
    fireEvent.change(screen.getByLabelText('厚度（nm）'), {target: {value: '80'}});
    fireEvent.click(screen.getByRole('button', {name: '确认添加'}));
    await waitFor(() => expect(api.addStep).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('button', {name: '确认添加'})).not.toBeDisabled());
    expect(screen.getByRole('dialog')).toBeVisible(); expect(screen.getByLabelText('厚度（nm）')).toHaveValue(80);
  });
});

afterEach(() => cleanup());

describe('StepStructureBar', () => {
  it('同类型重新配置确认丢弃会重置参数和名称，拒绝丢弃保留草稿', async () => {
    const target = step(0, {name: 'Structure Etch', instanceName: 'Structure Etch', params: {depth_nm: 20}, parameterSpecs: [{key: 'depth_nm', label: 'Depth', type: 'float', minimum: 0, units: 'nm', dimension: 'length', canonicalUnit: 'nm', displayUnits: ['nm', 'µm']}]});
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [target], factoryTemplates: [target]})), setStep: vi.fn(async () => ({step: target, statuses: ['dirty'] as RuntimeStatus[], warnings: []}))});
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<AppStateProvider api={api}><SelectedPanel /></AppStateProvider>);
    await screen.findByLabelText('工艺类型');
    fireEvent.click(screen.getByRole('button', {name: '配置类型'}));
    fireEvent.change(screen.getByLabelText('刻蚀深度（nm）'), {target: {value: '42'}});
    fireEvent.change(screen.getByLabelText('自定义名称（可选）'), {target: {value: 'draft name'}});
    fireEvent.click(screen.getByRole('button', {name: '配置类型'}));
    expect(screen.getByLabelText('刻蚀深度（nm）')).toHaveValue(42);
    expect(screen.getByLabelText('自定义名称（可选）')).toHaveValue('draft name');
    fireEvent.change(screen.getByLabelText('刻蚀深度单位'), {target: {value: 'µm'}});
    fireEvent.change(screen.getByLabelText('刻蚀深度（µm）'), {target: {value: '-1'}});
    expect(screen.getByRole('button', {name: '确认替换'})).toBeDisabled();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', {name: '配置类型'}));
    expect(screen.getByLabelText('刻蚀深度（nm）')).toHaveValue(20);
    expect(screen.getByLabelText('刻蚀深度单位')).toHaveValue('nm');
    expect(screen.getByLabelText('自定义名称（可选）')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', {name: '确认替换'}));
    await waitFor(() => expect(api.setStep).toHaveBeenCalledWith({index: 0, name: 'Structure Etch', params: {depth_nm: 20}}, expect.any(AbortSignal)));
    confirm.mockRestore();
  });
  it('多个候选表单字段和标题ID唯一，标签绑定各自的输入框', async () => {
    const target = step(0, {name: 'Structure Etch', params: {depth_nm: 20}, parameterSpecs: [{key: 'depth_nm', label: 'Depth', type: 'float', units: 'nm'}]});
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [step(0), step(1)], factoryTemplates: [target]}))});
    const {container} = render(<AppStateProvider api={api}><SelectionControls /><SelectedPanel /></AppStateProvider>);
    await screen.findByLabelText('工艺类型');
    fireEvent.change(screen.getByLabelText('工艺类型'), {target: {value: 'Etch'}});
    fireEvent.click(screen.getByRole('button', {name: 'select 1'}));
    fireEvent.change(screen.getByLabelText('工艺类型'), {target: {value: 'Etch'}});
    const ids = Array.from(container.querySelectorAll('[id]'), element => element.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const label of container.querySelectorAll<HTMLLabelElement>('.type-candidate label')) {
      expect(label.control).not.toBeNull();
      expect(label.closest('.type-candidate')!.contains(label.control)).toBe(true);
    }
  });
  it.each(['Initialize Wafer', 'Structure Wafer'])('stale选中 %s 禁止删除复制上下移动，普通首步不能越过初始化', async initial => {
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [step(0, {name: initial}), step(1, {name: 'Deposit'}), step(2, {name: 'Etch'})]}))});
    render(<AppStateProvider api={api}><SelectionControls /><StepStructureBar /></AppStateProvider>);
    await waitFor(() => expect(screen.getByRole('button', {name: '下移'})).not.toBeDisabled());
    expect(screen.getByRole('button', {name: '上移'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'select 0'}));
    for (const name of ['删除', '复制', '上移', '下移']) expect(screen.getByRole('button', {name})).toBeDisabled();
    expect(api.removeStep).not.toHaveBeenCalled(); expect(api.duplicateStep).not.toHaveBeenCalled(); expect(api.moveStep).not.toHaveBeenCalled();
  });
  it('项目设置无效网格禁用确认，导入失败保留草稿与原配方', async () => {
    const initial = step(0, {name: 'Structure Wafer', params: {thickness_nm: 200}, parameterSpecs: [{key: 'thickness_nm', label: 'Thickness', type: 'float', units: 'nm', minimum: 0}]});
    const blob = {domain: {grid_shape: [32, 32, 64], voxel_size_nm: 5}, steps_full: [{name: initial.name, params_raw: initial.params}]};
    const close = vi.fn(); const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [initial]})), exportRecipe: vi.fn(async () => ({text: async () => JSON.stringify(blob)} as Blob)), importRecipe: vi.fn(async () => {throw new TcadApiError('invalid project', {status: 400});})});
    render(<AppStateProvider api={api}><ProjectSettings api={api} onClose={close} /></AppStateProvider>);
    await screen.findByLabelText('网格 X');
    fireEvent.change(screen.getByLabelText('网格 X'), {target: {value: '1e308'}});
    expect(screen.getByRole('button', {name: '确认项目设置'})).toBeDisabled(); expect(api.importRecipe).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('网格 X'), {target: {value: '64'}});
    fireEvent.click(screen.getByRole('button', {name: '确认项目设置'}));
    await screen.findByText('导入失败，项目草稿已保留。');
    expect(close).not.toHaveBeenCalled(); expect(screen.getByLabelText('网格 X')).toHaveValue(64);
  });
  it.each(processCatalog.flatMap(source => processCatalog.map(target => [source.id, target.id])))('任意八类 %s → %s 同索引原子替换', async (source, target) => {
    const template = {...factoryTemplates.find(item => item.name === `Structure ${target}`)!, index: 0};
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [step(0, {name: `Structure ${source}`, instanceName: `Structure ${source}`, params: {thickness_nm: 999}})], factoryTemplates: [template]})), setStep: vi.fn(async () => ({step: template, statuses: ['dirty'] as RuntimeStatus[], warnings: []}))});
    render(<AppStateProvider api={api}><SelectedPanel /></AppStateProvider>);
    await screen.findByLabelText('工艺类型');
    if (source === target) fireEvent.click(screen.getByRole('button', {name: '配置类型'}));
    else fireEvent.change(screen.getByLabelText('工艺类型'), {target: {value: target}});
    fireEvent.click(screen.getByRole('button', {name: '确认替换'}));
    await waitFor(() => expect(api.setStep).toHaveBeenCalledWith({index: 0, name: `Structure ${target}`, params: template.params}, expect.any(AbortSignal)));
    expect(api.addStep).not.toHaveBeenCalled(); expect(api.removeStep).not.toHaveBeenCalled();
  });
  it('切换步骤及语言保留候选草稿，换目标需明确放弃确认', async () => {
    const target = step(0, {name: 'Structure Etch', params: {depth_nm: 20}, parameterSpecs: [{key: 'depth_nm', label: 'Depth', type: 'float', minimum: 0, units: 'nm'}]});
    const other = step(0, {name: 'Structure Strip'});
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [step(0, {name: 'Legacy'}), step(1)], factoryTemplates: [target, other]}))});
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<I18nProvider><AppStateProvider api={api}><SelectionControls /><LanguageSwitcher /><SelectedPanel /><StepStructureBar /></AppStateProvider></I18nProvider>);
    await screen.findByLabelText('工艺类型');
    fireEvent.change(screen.getByLabelText('工艺类型'), {target: {value: 'Etch'}});
    fireEvent.change(screen.getByLabelText('刻蚀深度（nm）'), {target: {value: '42'}});
    expect(screen.getByRole('button', {name: '上移'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'select 1'}));
    fireEvent.click(screen.getByRole('button', {name: 'select 0'}));
    expect(screen.getByLabelText('刻蚀深度（nm）')).toHaveValue(42);
    fireEvent.change(screen.getByLabelText('工艺类型'), {target: {value: 'Strip'}});
    expect(confirm).toHaveBeenCalledTimes(1); expect(screen.getByLabelText('工艺类型')).toHaveValue('Etch');
    fireEvent.click(screen.getByRole('button', {name: 'EN'}));
    expect(screen.getByLabelText('Etch depth (nm)')).toHaveValue(42);
    confirm.mockRestore();
  });
  it('项目设置读取完整导出，确认一次原子导入并保留所有步骤原始字段', async () => {
    const initial = step(0, {name: 'Initialize Wafer', params: {material: 'Silicon', thickness_nm: 200}, parameterSpecs: [{key: 'material', label: 'material', type: 'enum', choices: [['Silicon', 'Silicon'], ['Poly', 'Poly']]}, {key: 'thickness_nm', label: 'Thickness', type: 'float', minimum: 0, units: 'nm'}]});
    const blob = {domain: {grid_shape: [32, 32, 64], voxel_size_nm: 5, threads: 4}, steps_full: [{name: initial.name, params_raw: {...initial.params, wafer_type: 'SOI', box_thickness_nm: 20}, params: initial.params, enabled: false, instance_name: 'SOI', loop: '2', group: 'start'}, {name: 'Structure Strip', params_raw: {}, instance_name: 'clean', enabled: false, group: 'A'}]};
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [initial]})), exportRecipe: vi.fn(async () => ({text: async () => JSON.stringify(blob)} as Blob))});
    render(<AppStateProvider api={api}><ProjectSettings api={api} onClose={vi.fn()} /></AppStateProvider>);
    await screen.findByLabelText('网格 X');
    fireEvent.change(screen.getByLabelText('网格 X'), {target: {value: '64'}});
    fireEvent.change(screen.getByLabelText('体素尺寸（nm）'), {target: {value: '10'}});
    fireEvent.change(screen.getByLabelText('厚度（nm）'), {target: {value: '300'}});
    fireEvent.click(screen.getByRole('button', {name: '确认项目设置'}));
    await waitFor(() => expect(api.importRecipe).toHaveBeenCalledTimes(1));
    const imported = vi.mocked(api.importRecipe).mock.calls[0][0].recipe as typeof blob;
    expect(imported.domain).toEqual({grid_shape: [64, 32, 64], voxel_size_nm: 10, threads: 4});
    expect(imported.steps_full[1]).toEqual(blob.steps_full[1]);
    expect(imported.steps_full[0]).toMatchObject({params: {thickness_nm: 300, wafer_type: 'SOI'}, params_raw: {thickness_nm: 300, wafer_type: 'SOI'}, enabled: false, loop: '2', group: 'start'});
    expect(api.setStep).not.toHaveBeenCalled();
  });
  it('仅显示八类目录，旧服务器没有模板时禁止新增', async () => {
    const api = apiStub();
    mount(api);
    const select = await screen.findByRole('combobox', {name: '添加步骤类型'});
    const options = Array.from(select.querySelectorAll('option')).map(o => o.textContent);
    expect(options.slice(1)).toEqual(['光刻 / Lithography', '刻蚀 / Etch', '沉积 / Deposition', '氧化 / Oxidation', '外延 / Epitaxy', '去胶 / Strip', 'CMP', '掺杂 / Doping']);
    fireEvent.change(select, {target: {value: 'Structure Deposit'}});
    fireEvent.click(screen.getByRole('button', {name: '添加步骤'}));
    expect(screen.getByRole('button', {name: '添加步骤'})).toBeDisabled();
    expect(api.addStep).not.toHaveBeenCalled();
    expect(screen.getByText(/结构工艺模板不可用/)).toBeVisible();
  });

  it('旧步骤可内联改成任何目录类型，取消不请求且确认原子替换', async () => {
    const source = step(0, {name: 'Legacy', instanceName: 'contact', params: {thickness_nm: 500}});
    const target = step(0, {name: 'Structure Etch', instanceName: 'Structure Etch', params: {depth_nm: 20}, parameterSpecs: [{key: 'depth_nm', label: 'depth', type: 'float', minimum: 0, units: 'nm'}]});
    const api = apiStub({init: vi.fn(async () => ({...initView(), recipe: [source], factoryTemplates: [target]})), setStep: vi.fn(async () => ({step: target, statuses: ['dirty'] as RuntimeStatus[], warnings: []}))});
    render(<AppStateProvider api={api}><SelectedPanel /></AppStateProvider>);
    await screen.findByText('当前为旧配方类型：Legacy');
    fireEvent.change(screen.getByLabelText('工艺类型'), {target: {value: 'Etch'}});
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByLabelText('刻蚀深度（nm）')).toHaveValue(20);
    fireEvent.click(screen.getByRole('button', {name: '取消'}));
    expect(api.setStep).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('工艺类型'), {target: {value: 'Etch'}});
    fireEvent.change(screen.getByLabelText('刻蚀深度（nm）'), {target: {value: '42'}});
    fireEvent.click(screen.getByRole('button', {name: '确认替换'}));
    await waitFor(() => expect(api.setStep).toHaveBeenCalledWith({index: 0, name: 'Structure Etch', instanceName: 'contact', params: {depth_nm: 42}}, expect.any(AbortSignal)));
    expect(api.addStep).not.toHaveBeenCalled(); expect(api.removeStep).not.toHaveBeenCalled(); expect(api.runTo).not.toHaveBeenCalled();
  });

  it('默认选中首步：上移禁用、下移可用，操作按选中索引调用', async () => {
    const api = apiStub();
    mount(api);
    await screen.findByRole('button', {name: '上移'});
    expect(screen.getByRole('button', {name: '上移'})).toBeDisabled();
    expect(screen.getByRole('button', {name: '下移'})).toBeEnabled();

    fireEvent.click(screen.getByRole('button', {name: '下移'}));
    await waitFor(() => expect(api.moveStep).toHaveBeenCalledWith(0, 'down', expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole('button', {name: '复制'}));
    await waitFor(() => expect(api.duplicateStep).toHaveBeenCalledWith(0, expect.any(AbortSignal)));
  });

  it('重命名空名禁用，合法名称触发 renameStep', async () => {
    const api = apiStub();
    mount(api);
    await screen.findByRole('textbox', {name: '步骤重命名'});
    expect(screen.getByRole('button', {name: '应用重命名'})).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox', {name: '步骤重命名'}), {
      target: {value: '  Gate Ox  '},
    });
    fireEvent.click(screen.getByRole('button', {name: '应用重命名'}));
    await waitFor(() => expect(api.renameStep).toHaveBeenCalledWith(
      0,
      'Gate Ox',
      expect.any(AbortSignal),
    ));
  });

  it('删除在仅剩一步时禁用', async () => {
    const api = apiStub({
      init: vi.fn(async () => ({...initView(), recipe: [step(0)]})),
    });
    mount(api);
    await screen.findByRole('button', {name: '删除'});
    expect(screen.getByRole('button', {name: '删除'})).toBeDisabled();
  });
});
