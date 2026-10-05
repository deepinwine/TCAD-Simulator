import {useReducer} from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {MaskCanvas} from './MaskCanvas';
import {createMaskEditorState, maskEditorReducer} from './editorReducer';
import type {MaskAsset} from '../api/types';
const asset: MaskAsset = {
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
import type {MaskEditorState} from './types';
function Harness({initial}: {initial: MaskEditorState}) {
  const [state, dispatch] = useReducer(maskEditorReducer, initial);
  return (
    <>
      <MaskCanvas state={state} dispatch={dispatch} />
      <output data-testid="state">{JSON.stringify(state)}</output>
    </>
  );
}
const current = () => JSON.parse(screen.getByTestId('state').textContent!);
describe('MaskCanvas', () => {
  it('does not start a transient drawing gesture on a hidden active layer', () => {
    render(
      <Harness
        initial={{
          ...createMaskEditorState({...asset, layers: [{...asset.layers[0], visible: false}]}),
          tool: 'rectangle',
        }}
      />,
    );
    const canvas = screen.getByTestId('mask-canvas');
    fireEvent.pointerDown(canvas, {clientX: 10, clientY: 10});
    fireEvent.pointerMove(canvas, {clientX: 50, clientY: 50});
    expect(canvas.querySelector('g[opacity]')).toBeNull();
    fireEvent.pointerUp(canvas, {clientX: 50, clientY: 50});
    expect(current().asset.shapes).toEqual([]);
    expect(current().past).toEqual([]);
  });
  it('commits one history item on pointerup and selects, clears and deletes', () => {
    render(<Harness initial={{...createMaskEditorState(asset), tool: 'rectangle'}} />);
    const canvas = screen.getByTestId('mask-canvas');
    fireEvent.pointerDown(canvas, {clientX: 20, clientY: 30});
    fireEvent.pointerMove(canvas, {clientX: 100, clientY: 120});
    expect(current().past).toHaveLength(0);
    fireEvent.pointerUp(canvas, {clientX: 100, clientY: 120});
    expect(current().asset.shapes[0]).toMatchObject({
      xNm: 20,
      yNm: 30,
      widthNm: 80,
      heightNm: 90,
    });
    expect(current().past).toHaveLength(1);
    fireEvent.keyDown(canvas, {key: 'Delete'});
    expect(current().asset.shapes).toHaveLength(0);
  });
  it.each(['circle', 'hole', 'line'] as const)('draws %s', (tool) => {
    render(<Harness initial={{...createMaskEditorState(asset), tool}} />);
    const canvas = screen.getByTestId('mask-canvas');
    fireEvent.pointerDown(canvas, {clientX: 50, clientY: 50});
    fireEvent.pointerUp(canvas, {clientX: 80, clientY: 90});
    expect(current().asset.shapes[0]).toMatchObject(
      tool === 'line'
        ? {
            type: tool,
            widthNm: 10,
            pointsNm: [
              [50, 50],
              [80, 90],
            ],
          }
        : {type: tool, cxNm: 50, cyNm: 50, radiusNm: 50},
    );
  });
  it('closes polygons on double click and does not render hidden shapes', () => {
    render(<Harness initial={{...createMaskEditorState(asset), tool: 'polygon'}} />);
    const canvas = screen.getByTestId('mask-canvas');
    for (const [x, y] of [
      [10, 10],
      [100, 10],
      [100, 100],
    ])
      fireEvent.pointerDown(canvas, {clientX: x, clientY: y});
    fireEvent.doubleClick(canvas);
    expect(current().asset.shapes[0].pointsNm).toEqual([
      [10, 10],
      [100, 10],
      [100, 100],
      [10, 10],
    ]);
  });
  it('selects with shift and clears on background; hidden layers cannot be hit', () => {
    const shape = {
      id: 'r',
      type: 'rectangle' as const,
      layerId: '1',
      xNm: 0,
      yNm: 0,
      widthNm: 20,
      heightNm: 20,
      rotationDeg: 0,
    };
    const {unmount} = render(
      <Harness initial={createMaskEditorState({...asset, shapes: [shape]})} />,
    );
    fireEvent.pointerDown(screen.getByTestId('mask-shape-r'));
    expect(current().selection).toEqual(['r']);
    fireEvent.pointerDown(screen.getByTestId('mask-canvas'));
    expect(current().selection).toEqual([]);
    unmount();
    render(
      <Harness
        initial={createMaskEditorState({
          ...asset,
          layers: [{...asset.layers[0], visible: false}],
          shapes: [shape],
        })}
      />,
    );
    expect(screen.queryByTestId('mask-shape-r')).toBeNull();
  });
  it('uses SVG CTM inverse coordinates', () => {
    render(<Harness initial={{...createMaskEditorState(asset), tool: 'rectangle'}} />);
    const canvas = screen.getByTestId('mask-canvas') as unknown as SVGSVGElement;
    Object.defineProperty(canvas, 'getScreenCTM', {
      value: () => ({inverse: () => ({scale: 2})}),
    });
    Object.defineProperty(canvas, 'createSVGPoint', {
      value: () => ({
        x: 0,
        y: 0,
        matrixTransform(this: {x: number; y: number}, matrix: {scale: number}) {
          return {x: this.x * matrix.scale, y: this.y * matrix.scale};
        },
      }),
    });
    fireEvent.pointerDown(canvas, {clientX: 10, clientY: 20});
    fireEvent.pointerUp(canvas, {clientX: 30, clientY: 50});
    expect(current().asset.shapes[0]).toMatchObject({
      xNm: 20,
      yNm: 40,
      widthNm: 40,
      heightNm: 60,
    });
  });
  it('moves a shift selection with one history entry', () => {
    const rectangle = {
      type: 'rectangle' as const,
      layerId: '1',
      xNm: 0,
      yNm: 0,
      widthNm: 20,
      heightNm: 20,
      rotationDeg: 0,
    };
    render(
      <Harness
        initial={createMaskEditorState({
          ...asset,
          shapes: [
            {...rectangle, id: 'a'},
            {...rectangle, id: 'b'},
          ],
        })}
      />,
    );
    fireEvent.pointerDown(screen.getByTestId('mask-shape-a'), {
      clientX: 0,
      clientY: 0,
    });
    fireEvent.pointerUp(screen.getByTestId('mask-canvas'), {
      clientX: 0,
      clientY: 0,
    });
    fireEvent.pointerDown(screen.getByTestId('mask-shape-b'), {
      clientX: 0,
      clientY: 0,
      shiftKey: true,
    });
    expect(current().selection).toEqual(['a', 'b']);
    fireEvent.pointerMove(screen.getByTestId('mask-canvas'), {
      clientX: 10,
      clientY: 20,
    });
    expect(current().past).toHaveLength(0);
    fireEvent.pointerUp(screen.getByTestId('mask-canvas'), {
      clientX: 10,
      clientY: 20,
    });
    expect(current().asset.shapes.map((s: {xNm: number}) => s.xNm)).toEqual([10, 10]);
    expect(current().past).toHaveLength(1);
  });
});
