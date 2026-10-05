import type {MaskAsset, MaskAssetLayer, MaskAssetShape} from '../api/types';
export type MaskTool = 'select' | 'rectangle' | 'circle' | 'hole' | 'line' | 'polygon';
export interface MaskEditorState {
  asset: MaskAsset;
  selection: readonly string[];
  activeLayerId: string;
  tool: MaskTool;
  gridVisible: boolean;
  snapNm: number;
  past: readonly MaskAsset[];
  future: readonly MaskAsset[];
  dirty: boolean;
}
export type ShapePatch = Partial<MaskAssetShape> & {
  xNm?: number;
  yNm?: number;
  widthNm?: number;
  heightNm?: number;
  rotationDeg?: number;
  cxNm?: number;
  cyNm?: number;
  radiusNm?: number;
  pointsNm?: readonly (readonly [number, number])[];
};
export type MaskEditorAction =
  | {type: 'patchAsset'; patch: Partial<MaskAsset>}
  | {type: 'patchShape'; id: string; patch: ShapePatch}
  | {type: 'setTool'; tool: MaskTool}
  | {type: 'setSelection'; selection: readonly string[]}
  | {type: 'setSnap'; snapNm: number}
  | {type: 'setGrid'; gridVisible: boolean}
  | {type: 'setActiveLayer'; layerId: string}
  | {type: 'patchLayer'; id: string; patch: Partial<MaskAssetLayer>}
  | {type: 'addLayer'; layer: MaskAssetLayer}
  | {type: 'addShape'; shape: MaskAssetShape}
  | {type: 'deleteSelection'}
  | {type: 'moveSelection'; dxNm: number; dyNm: number}
  | {type: 'undo'}
  | {type: 'redo'}
  | {type: 'replaceAsset'; asset: MaskAsset};
