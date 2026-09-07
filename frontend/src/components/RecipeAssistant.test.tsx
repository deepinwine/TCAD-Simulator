import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {RecipeAssistant} from './RecipeAssistant';

const {importRecipe} = vi.hoisted(() => ({importRecipe: vi.fn()}));
vi.mock('../state/AppStateContext', () => ({useAppState: () => ({actions: {importRecipe}})}));

function response(overrides = {}) {
  return {ok: true, draft: {version: 1, sourceText: '沉积氧化硅', steps: [
    {type: 'deposit', params: {}, confidence: 1, sourceSpan: '', warnings: [], isDefault: false},
  ], warnings: ['草稿单位警告'], ambiguities: []}, validation: {
    ok: true, errors: [], warnings: ['验证模式警告'], mode_recommendations: [],
  }, ...overrides};
}

beforeEach(() => { importRecipe.mockReset(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function generate(payload = response()) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, json: async () => payload}));
  render(<RecipeAssistant />);
  fireEvent.change(screen.getByRole('textbox', {name: '工艺描述'}), {target: {value: '沉积氧化硅'}});
  fireEvent.click(screen.getByRole('button', {name: '生成 Recipe'}));
  await screen.findByRole('region', {name: 'Proposed Recipe'});
}

it('呈现草稿与验证警告及阻止应用的验证错误', async () => {
  await generate(response({validation: {ok: false, errors: ['材料不存在'], warnings: ['验证模式警告'], mode_recommendations: []}}));
  expect(screen.getByText('材料不存在')).toBeVisible();
  expect(screen.getByText('草稿单位警告')).toBeVisible();
  expect(screen.getByText('验证模式警告')).toBeVisible();
  expect(screen.queryByRole('button', {name: '应用到 Process Flow'})).not.toBeInTheDocument();
});

it('空草稿不能应用', async () => {
  const payload = response();
  payload.draft.steps = [];
  await generate(payload);
  expect(screen.getByRole('button', {name: '应用到 Process Flow'})).toBeDisabled();
});

it('导入等待及失败保留输入，确认成功后才清空', async () => {
  let resolve!: (value: boolean) => void;
  importRecipe.mockImplementationOnce(() => new Promise<boolean>(done => { resolve = done; }));
  await generate();
  fireEvent.click(screen.getByRole('button', {name: '应用到 Process Flow'}));
  expect(screen.getByRole('textbox', {name: '工艺描述'})).toHaveValue('沉积氧化硅');
  expect(screen.getByRole('button', {name: /应用/})).toBeDisabled();
  await act(async () => resolve(false));
  expect(screen.getByRole('textbox', {name: '工艺描述'})).toHaveValue('沉积氧化硅');
  expect(screen.getByRole('region', {name: 'Proposed Recipe'})).toBeVisible();
  importRecipe.mockResolvedValueOnce(true);
  fireEvent.click(screen.getByRole('button', {name: '应用到 Process Flow'}));
  await act(async () => {});
  expect(screen.getByRole('textbox', {name: '工艺描述'})).toHaveValue('');
  expect(screen.queryByRole('region', {name: 'Proposed Recipe'})).not.toBeInTheDocument();
});
