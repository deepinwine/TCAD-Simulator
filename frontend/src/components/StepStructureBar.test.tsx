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
  it('列出工厂类型，选择后添加步骤调用 addStep', async () => {
    const api = apiStub();
    mount(api);
    const select = await screen.findByRole('combobox', {name: '添加步骤类型'});
    const options = Array.from(select.querySelectorAll('option')).map(o => o.textContent);
    expect(options).toContain('Initialize Wafer');

    fireEvent.change(select, {target: {value: 'deposit'}});
    fireEvent.click(screen.getByRole('button', {name: '添加步骤'}));
    await waitFor(() => expect(api.addStep).toHaveBeenCalledWith('deposit', expect.any(AbortSignal)));
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
