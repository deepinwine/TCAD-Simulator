import type {MaskAsset, MaskAssetShape} from '../api/types';
import type {MaskEditorAction, MaskEditorState} from './types';
function visible(asset: MaskAsset, shape: MaskAssetShape): boolean {
  return asset.layers.some((layer) => layer.id === shape.layerId && layer.visible);
}
function visibleSelection(state: MaskEditorState): MaskEditorState {
  const selection = state.selection.filter((id) =>
    state.asset.shapes.some((shape) => shape.id === id && visible(state.asset, shape)),
  );
  return selection.length === state.selection.length ? state : {...state, selection};
}
export function createMaskEditorState(asset: MaskAsset): MaskEditorState {
  return {
    asset,
    selection: [],
    activeLayerId: asset.layers[0]?.id ?? '',
    tool: 'select',
    gridVisible: true,
    snapNm: 0,
    past: [],
    future: [],
    dirty: false,
  };
}
export function snapValue(value: number, snapNm: number) {
  return snapNm > 0 ? Math.round(value / snapNm) * snapNm : value;
}
function snapped(shape: MaskAssetShape, snapNm: number): MaskAssetShape {
  const snap = (value: number) => snapValue(value, snapNm);
  if (shape.type === 'rectangle')
    return {
      ...shape,
      xNm: snap(shape.xNm),
      yNm: snap(shape.yNm),
      widthNm: Math.max(snapNm || Number.EPSILON, snap(shape.widthNm)),
      heightNm: Math.max(snapNm || Number.EPSILON, snap(shape.heightNm)),
    };
  if ('radiusNm' in shape)
    return {
      ...shape,
      cxNm: snap(shape.cxNm),
      cyNm: snap(shape.cyNm),
      radiusNm: Math.max(snapNm || Number.EPSILON, snap(shape.radiusNm)),
    };
  return {
    ...shape,
    pointsNm: shape.pointsNm.map(([x, y]) => [snap(x), snap(y)] as const),
  };
}
export function translateShape(shape: MaskAssetShape, dxNm: number, dyNm: number): MaskAssetShape {
  if (shape.type === 'rectangle') return {...shape, xNm: shape.xNm + dxNm, yNm: shape.yNm + dyNm};
  if ('radiusNm' in shape) return {...shape, cxNm: shape.cxNm + dxNm, cyNm: shape.cyNm + dyNm};
  return {
    ...shape,
    pointsNm: shape.pointsNm.map(([x, y]) => [x + dxNm, y + dyNm] as const),
  };
}
export function maskEditorReducer(
  state: MaskEditorState,
  action: MaskEditorAction,
): MaskEditorState {
  state = visibleSelection(state);
  const commit = (asset: MaskAsset): MaskEditorState =>
    JSON.stringify(asset) === JSON.stringify(state.asset)
      ? state
      : visibleSelection({
          ...state,
          asset,
          past: [...state.past, state.asset].slice(-100),
          future: [],
          dirty: true,
        });
  switch (action.type) {
    case 'setTool':
      return {...state, tool: action.tool};
    case 'setSelection':
      return {
        ...state,
        selection: [...new Set(action.selection)].filter((id) =>
          state.asset.shapes.some((shape) => shape.id === id && visible(state.asset, shape)),
        ),
      };
    case 'setSnap':
      return {
        ...state,
        snapNm: Number.isFinite(action.snapNm) ? Math.max(0, action.snapNm) : 0,
      };
    case 'setGrid':
      return {...state, gridVisible: action.gridVisible};
    case 'setActiveLayer':
      return state.asset.layers.some((layer) => layer.id === action.layerId)
        ? {...state, activeLayerId: action.layerId}
        : state;
    case 'replaceAsset':
      return createMaskEditorState(action.asset);
    case 'patchAsset':
      return commit({...state.asset, ...action.patch});
    case 'patchLayer': {
      const next = commit({
        ...state.asset,
        layers: state.asset.layers.map((layer) =>
          layer.id === action.id ? {...layer, ...action.patch} : layer,
        ),
      });
      return {
        ...next,
        selection: next.selection.filter((id) =>
          next.asset.shapes.some(
            (shape) =>
              shape.id === id &&
              next.asset.layers.some((layer) => layer.id === shape.layerId && layer.visible),
          ),
        ),
      };
    }
    case 'addLayer':
      return state.asset.layers.some((layer) => layer.id === action.layer.id)
        ? state
        : {
            ...commit({
              ...state.asset,
              layers: [...state.asset.layers, action.layer],
            }),
            activeLayerId: action.layer.id,
          };
    case 'patchShape':
      if (
        !state.asset.shapes.some((shape) => shape.id === action.id && visible(state.asset, shape))
      )
        return state;
      return commit({
        ...state.asset,
        shapes: state.asset.shapes.map((shape) =>
          shape.id === action.id ? ({...shape, ...action.patch} as MaskAssetShape) : shape,
        ),
      });
    case 'addShape': {
      if (
        !state.asset.layers.some((layer) => layer.id === state.activeLayerId && layer.visible) ||
        state.asset.shapes.some((shape) => shape.id === action.shape.id)
      )
        return state;
      const shape = snapped({...action.shape, layerId: state.activeLayerId}, state.snapNm);
      return {
        ...commit({...state.asset, shapes: [...state.asset.shapes, shape]}),
        selection: [shape.id],
      };
    }
    case 'deleteSelection':
      return {
        ...commit({
          ...state.asset,
          shapes: state.asset.shapes.filter((shape) => !state.selection.includes(shape.id)),
        }),
        selection: [],
      };
    case 'moveSelection':
      return commit({
        ...state.asset,
        shapes: state.asset.shapes.map((shape) =>
          state.selection.includes(shape.id) &&
          state.asset.layers.some((layer) => layer.id === shape.layerId && layer.visible)
            ? translateShape(
                shape,
                snapValue(action.dxNm, state.snapNm),
                snapValue(action.dyNm, state.snapNm),
              )
            : shape,
        ),
      });
    case 'undo':
      return state.past.length
        ? {
            ...state,
            asset: state.past[state.past.length - 1],
            activeLayerId: state.past[state.past.length - 1].layers.some(
              (layer) => layer.id === state.activeLayerId,
            )
              ? state.activeLayerId
              : (state.past[state.past.length - 1].layers[0]?.id ?? ''),
            past: state.past.slice(0, -1),
            future: [state.asset, ...state.future],
            selection: [],
            dirty: true,
          }
        : state;
    case 'redo':
      return state.future.length
        ? {
            ...state,
            asset: state.future[0],
            activeLayerId: state.future[0].layers.some((layer) => layer.id === state.activeLayerId)
              ? state.activeLayerId
              : (state.future[0].layers[0]?.id ?? ''),
            past: [...state.past, state.asset].slice(-100),
            future: state.future.slice(1),
            selection: [],
            dirty: true,
          }
        : state;
  }
}
