import {describe, expect, it} from 'vitest';
import type {MaskAsset} from '../api/types';
import {createMaskEditorState, maskEditorReducer as reduce} from './editorReducer';
export const asset: MaskAsset = {
  version: 1,
  id: 'a',
  revision: 1,
  name: 'Mask',
  coordinateUnit: 'nm',
  boundsNm: [0, 0, 2000, 2000],
  layers: [{id: '1', layer: 1, datatype: 0, name: 'L1', visible: true}],
  shapes: [],
  source: {kind: 'manual'},
};
describe('mask reducer', () => {
  it('keeps the active layer valid when undo removes a newly added layer', () => {
    const added = reduce(createMaskEditorState(asset), {
      type: 'addLayer',
      layer: {id: '2', layer: 2, datatype: 0, name: 'New', visible: true},
    });
    const undone = reduce(added, {type: 'undo'});
    expect(undone.activeLayerId).toBe('1');
  });
  it('removes hidden layers from selection and cannot move a hidden shape through stale selection', () => {
    const shape = {
      id: 'hidden',
      type: 'rectangle' as const,
      layerId: '1',
      xNm: 10,
      yNm: 10,
      widthNm: 20,
      heightNm: 20,
      rotationDeg: 0,
    };
    const before = {...createMaskEditorState({...asset, shapes: [shape]}), selection: ['hidden']};
    const hidden = reduce(before, {type: 'patchLayer', id: '1', patch: {visible: false}});
    expect(hidden.selection).toEqual([]);
    const stale = reduce(
      {...hidden, selection: ['hidden']},
      {type: 'moveSelection', dxNm: 100, dyNm: 100},
    );
    expect(stale.asset.shapes[0]).toEqual(shape);
  });
  it('adds on active layer with snapping and preserves exact undo/redo JSON', () => {
    const initial = createMaskEditorState(asset);
    const next = reduce(reduce(initial, {type: 'setSnap', snapNm: 10}), {
      type: 'addShape',
      shape: {
        id: 'r',
        type: 'rectangle',
        layerId: 'ignored',
        xNm: 13,
        yNm: 17,
        widthNm: 31,
        heightNm: 44,
        rotationDeg: 0,
      },
    });
    expect(next.asset.shapes[0]).toMatchObject({
      layerId: '1',
      xNm: 10,
      yNm: 20,
      widthNm: 30,
      heightNm: 40,
    });
    expect(JSON.stringify(reduce(next, {type: 'undo'}).asset)).toBe(JSON.stringify(asset));
    expect(JSON.stringify(reduce(reduce(next, {type: 'undo'}), {type: 'redo'}).asset)).toBe(
      JSON.stringify(next.asset),
    );
  });
  it('moves multi-selection, edits geometry and metadata, and deletes without changing hidden layers', () => {
    let state = createMaskEditorState({
      ...asset,
      shapes: [
        {
          id: 'r',
          type: 'rectangle',
          layerId: '1',
          xNm: 0,
          yNm: 0,
          widthNm: 20,
          heightNm: 20,
          rotationDeg: 0,
        },
        {
          id: 'c',
          type: 'circle',
          layerId: '1',
          cxNm: 20,
          cyNm: 20,
          radiusNm: 10,
        },
      ],
    });
    state = reduce(state, {type: 'setSelection', selection: ['r', 'c']});
    state = reduce(state, {type: 'moveSelection', dxNm: 10, dyNm: 20});
    expect(state.asset.shapes[0]).toMatchObject({xNm: 10, yNm: 20});
    expect(state.asset.shapes[1]).toMatchObject({cxNm: 30, cyNm: 40});
    state = reduce(state, {
      type: 'patchShape',
      id: 'r',
      patch: {widthNm: 40, rotationDeg: 45},
    });
    expect(state.asset.shapes[0]).toMatchObject({
      widthNm: 40,
      rotationDeg: 45,
    });
    state = reduce(state, {
      type: 'patchLayer',
      id: '1',
      patch: {layer: 2, datatype: 3, visible: false},
    });
    expect(state.asset.shapes).toHaveLength(2);
    expect(state.asset.layers[0]).toMatchObject({
      layer: 2,
      datatype: 3,
      visible: false,
    });
    state = reduce(state, {type: 'patchAsset', patch: {name: 'Renamed'}});
    expect(state.asset.name).toBe('Renamed');
    expect(reduce(state, {type: 'deleteSelection'}).asset.shapes).toHaveLength(2);
    state = reduce(state, {type: 'patchLayer', id: '1', patch: {visible: true}});
    state = reduce(state, {type: 'setSelection', selection: ['r', 'c']});
    expect(reduce(state, {type: 'deleteSelection'}).asset.shapes).toHaveLength(0);
  });
  it('clears redo on branch and limits history to 100', () => {
    let state = createMaskEditorState(asset);
    for (let i = 0; i < 105; i++)
      state = reduce(state, {type: 'patchAsset', patch: {name: String(i)}});
    expect(state.past).toHaveLength(100);
    state = reduce(reduce(state, {type: 'undo'}), {
      type: 'patchAsset',
      patch: {name: 'fork'},
    });
    expect(state.future).toEqual([]);
  });
});
