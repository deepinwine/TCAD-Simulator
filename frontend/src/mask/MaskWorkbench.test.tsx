import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import type {MaskAsset, MaskAssetApplyView, TcadApi} from '../api/types';
import {TcadApiError} from '../api/client';
import {I18nProvider} from '../i18n/I18nContext';
import {MaskWorkbench} from './MaskWorkbench';

const asset: MaskAsset = {
  version: 1,
  id: 'mask_test',
  revision: 1,
  name: 'Test mask',
  coordinateUnit: 'nm',
  boundsNm: [0, 0, 2000, 2000],
  layers: [{id: '1/0', layer: 1, datatype: 0, name: 'M1', visible: true}],
  shapes: [
    {
      id: 'rect',
      type: 'rectangle',
      layerId: '1/0',
      xNm: 100,
      yNm: 100,
      widthNm: 200,
      heightNm: 300,
      rotationDeg: 0,
    },
  ],
  source: {kind: 'editor'},
};
const applied: MaskAssetApplyView = {
  asset: {...asset, revision: 2},
  step: {
    index: 3,
    name: 'Mask Exposure',
    instanceName: 'Mask Exposure',
    enabled: true,
    group: '',
    loop: '',
    params: {mask_asset_revision: 2},
    parameterSpecs: [],
    runtimeStatus: 'dirty',
  },
  statuses: ['ready', 'ready', 'ready', 'dirty'],
  warnings: [],
};
function setup(overrides: Partial<TcadApi> = {}) {
  const api = {
    saveAndApplyMaskAsset: vi.fn(async () => applied),
    importAndApplyMaskAsset: vi.fn(async () => applied),
    exportMaskAsset: vi.fn(async () => new Blob()),
    ...overrides,
  } as unknown as TcadApi;
  const onApply = vi.fn();
  const onClose = vi.fn();
  render(
    <I18nProvider>
      <MaskWorkbench
        api={api}
        initialAsset={asset}
        stepIndex={3}
        onApply={onApply}
        onClose={onClose}
      />
    </I18nProvider>,
  );
  return {api, onApply, onClose};
}
describe('Mask Workbench session', () => {
  it('removes the Inspector selection when a shape is moved into a hidden layer', () => {
    setup();
    fireEvent.click(screen.getByRole('button', {name: '新增图层'}));
    fireEvent.click(screen.getByLabelText('可见 L2'));
    fireEvent.pointerDown(screen.getByTestId('mask-shape-rect'), {clientX: 100, clientY: 100});
    fireEvent.pointerUp(screen.getByTestId('mask-canvas'), {clientX: 100, clientY: 100});
    const hiddenId = (screen.getByLabelText('活动图层') as HTMLSelectElement).value;
    fireEvent.change(screen.getByLabelText('图形所属图层'), {target: {value: hiddenId}});
    expect(screen.queryByLabelText('宽度 (nm)')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: '删除所选'})).not.toBeInTheDocument();
    expect(screen.queryByTestId('mask-shape-rect')).not.toBeInTheDocument();
  });
  it('allows zero snapping for precise drawing', () => {
    setup();
    fireEvent.change(screen.getByLabelText('吸附网格 (nm)'), {target: {value: '10'}});
    fireEvent.change(screen.getByLabelText('吸附网格 (nm)'), {target: {value: '0'}});
    expect(screen.getByRole('button', {name: '保存并应用'})).toBeEnabled();
  });
  it('edits canonical geometry and GDS metadata precisely before save', async () => {
    const {api} = setup();
    fireEvent.pointerDown(screen.getByTestId('mask-shape-rect'), {clientX: 100, clientY: 100});
    fireEvent.pointerUp(screen.getByTestId('mask-canvas'), {clientX: 100, clientY: 100});
    fireEvent.change(screen.getByLabelText('宽度 (nm)'), {target: {value: '123.456'}});
    fireEvent.change(screen.getByLabelText('旋转 (°)'), {target: {value: '30'}});
    fireEvent.change(screen.getByLabelText('GDS layer'), {target: {value: '12'}});
    fireEvent.change(screen.getByLabelText('GDS datatype'), {target: {value: '3'}});
    fireEvent.change(screen.getByLabelText('边界 Y 最大值 (nm)'), {target: {value: '3000'}});
    fireEvent.click(screen.getByRole('button', {name: '保存并应用'}));
    await waitFor(() => expect(api.saveAndApplyMaskAsset).toHaveBeenCalled());
    expect(api.saveAndApplyMaskAsset).toHaveBeenCalledWith(
      expect.objectContaining({
        asset: expect.objectContaining({
          boundsNm: [0, 0, 2000, 3000],
          layers: [expect.objectContaining({layer: 12, datatype: 3})],
          shapes: [expect.objectContaining({widthNm: 123.456, rotationDeg: 30})],
        }),
      }),
      expect.any(AbortSignal),
    );
  });
  it('selection does not clear incomplete asset bounds validation', () => {
    setup();
    fireEvent.change(screen.getByLabelText('边界 X 最大值 (nm)'), {target: {value: ''}});
    fireEvent.pointerDown(screen.getByTestId('mask-shape-rect'), {clientX: 100, clientY: 100});
    fireEvent.pointerUp(screen.getByTestId('mask-canvas'), {clientX: 100, clientY: 100});
    expect(screen.getByLabelText('边界 X 最大值 (nm)')).toHaveValue(null);
    expect(screen.getByRole('button', {name: '保存并应用'})).toBeDisabled();
  });
  it('Undo restores canonical field text as well as validity after incomplete input', () => {
    setup();
    fireEvent.change(screen.getByLabelText('资产名称'), {target: {value: 'Other'}});
    fireEvent.change(screen.getByLabelText('边界 X 最大值 (nm)'), {target: {value: ''}});
    fireEvent.click(screen.getByRole('button', {name: '撤销'}));
    expect(screen.getByLabelText('边界 X 最大值 (nm)')).toHaveValue(2000);
    expect(screen.getByRole('button', {name: '保存并应用'})).toBeEnabled();
  });
  it('an unfinished polygon disables save, asks before abandonment and clears when changing tools', () => {
    setup();
    fireEvent.click(screen.getByRole('button', {name: '多边形'}));
    fireEvent.pointerDown(screen.getByTestId('mask-canvas'), {clientX: 20, clientY: 20});
    fireEvent.pointerDown(screen.getByTestId('mask-canvas'), {clientX: 50, clientY: 20});
    expect(screen.getByRole('button', {name: '保存并应用'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: '放弃并返回'}));
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: '继续编辑'}));
    fireEvent.click(screen.getByRole('button', {name: '矩形'}));
    expect(screen.getByRole('button', {name: '保存并应用'})).toBeEnabled();
    expect(screen.getByTestId('mask-canvas').querySelector('polyline')).toBeNull();
  });
  it('keeps edits and history when changing language, then saves authoritative revision', async () => {
    const {api, onApply, onClose} = setup();
    fireEvent.change(screen.getByLabelText('资产名称'), {
      target: {value: 'Edited'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'EN'}));
    expect(screen.getByLabelText('Asset name')).toHaveValue('Edited');
    fireEvent.click(screen.getByRole('button', {name: 'Undo'}));
    expect(screen.getByLabelText('Asset name')).toHaveValue('Test mask');
    fireEvent.click(screen.getByRole('button', {name: 'Redo'}));
    fireEvent.click(screen.getByRole('button', {name: 'Save and apply'}));
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(api.saveAndApplyMaskAsset).toHaveBeenCalledWith(
      expect.objectContaining({
        asset: expect.objectContaining({name: 'Edited', revision: 1}),
        stepIndex: 3,
      }),
      expect.any(AbortSignal),
    );
    expect(onApply).toHaveBeenCalledWith(applied);
  });
  it('retains draft and old revision after save failure', async () => {
    const {onClose} = setup({
      saveAndApplyMaskAsset: vi.fn(async () => {
        throw new TcadApiError('failed', {code: 'invalid_mask', status: 400});
      }),
    });
    fireEvent.change(screen.getByLabelText('资产名称'), {
      target: {value: 'Keep'},
    });
    fireEvent.click(screen.getByRole('button', {name: '保存并应用'}));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('资产名称')).toHaveValue('Keep');
    expect(screen.getByText('mask_test · revision 1')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
  it('Escape confirms abandonment and returns focus without applying', () => {
    const {api, onClose} = setup();
    fireEvent.change(screen.getByLabelText('资产名称'), {
      target: {value: 'Discard'},
    });
    fireEvent.keyDown(screen.getByRole('dialog'), {key: 'Escape'});
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: '确认放弃'}));
    expect(onClose).toHaveBeenCalledOnce();
    expect(api.saveAndApplyMaskAsset).not.toHaveBeenCalled();
  });
  it('import synchronizes the applied step immediately and resets revision/history honestly', async () => {
    const {api, onApply, onClose} = setup();
    fireEvent.change(screen.getByLabelText('导入并应用文件'), {
      target: {
        files: [new File(['{}'], 'mask.json', {type: 'application/json'})],
      },
    });
    await waitFor(() => expect(onApply).toHaveBeenCalledWith(applied));
    expect(api.importAndApplyMaskAsset).toHaveBeenCalled();
    expect(screen.getByText('mask_test · revision 2')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('导入已应用到工艺步骤');
    expect(onClose).not.toHaveBeenCalled();
  });
  it('traps tab focus inside dialog and rejects empty/non-finite geometry edits', () => {
    setup();
    const dialog = screen.getByRole('dialog');
    const first = screen.getByRole('button', {name: '撤销'});
    const last = screen.getByRole('button', {name: '放弃并返回'});
    last.focus();
    fireEvent.keyDown(dialog, {key: 'Tab'});
    expect(screen.getByRole('button', {name: '中文'})).toHaveFocus();
    fireEvent.keyDown(dialog, {key: 'Tab', shiftKey: true});
    expect(last).toHaveFocus();
    fireEvent.change(screen.getByLabelText('边界 X 最大值 (nm)'), {
      target: {value: ''},
    });
    expect(screen.getByRole('button', {name: '保存并应用'})).toBeDisabled();
    expect(first).toBeDisabled();
  });
  it('does not discard an unsaved draft when selecting an import until explicitly confirmed', async () => {
    const {api, onApply} = setup();
    fireEvent.change(screen.getByLabelText('资产名称'), {
      target: {value: 'Draft'},
    });
    fireEvent.change(screen.getByLabelText('导入并应用文件'), {
      target: {files: [new File(['{}'], 'new.json')]},
    });
    expect(api.importAndApplyMaskAsset).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: '确认放弃'}));
    await waitFor(() => expect(onApply).toHaveBeenCalledWith(applied));
  });
  it('keeps the draft on import failure and localizes missing GDS dependencies', async () => {
    setup({
      importAndApplyMaskAsset: vi.fn(async () => {
        throw new TcadApiError('gdstk', {
          code: 'dependency_missing',
          status: 400,
        });
      }),
    });
    fireEvent.change(screen.getByLabelText('导入并应用文件'), {
      target: {files: [new File(['GDS'], 'mask.gds')]},
    });
    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent('GDS 需要安装 gdstk');
    expect(screen.getByText('mask_test · revision 1')).toBeInTheDocument();
    expect(screen.getByLabelText('资产名称')).toHaveValue('Test mask');
  });
  it('exports the exact saved revision and forbids exporting an unsaved draft', async () => {
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const {api} = setup();
    fireEvent.click(screen.getByRole('button', {name: '导出 JSON'}));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    expect(api.exportMaskAsset).toHaveBeenCalledWith(
      'mask_test',
      1,
      'json',
      expect.any(AbortSignal),
    );
    expect(create).toHaveBeenCalled();
    expect(revoke).toHaveBeenCalledWith('blob:test');
    fireEvent.change(screen.getByLabelText('资产名称'), {
      target: {value: 'Dirty'},
    });
    expect(screen.getByRole('button', {name: '导出 GDS'})).toBeDisabled();
    create.mockRestore();
    revoke.mockRestore();
    click.mockRestore();
  });
});
