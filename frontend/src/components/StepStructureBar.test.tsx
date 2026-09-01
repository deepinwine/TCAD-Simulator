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
