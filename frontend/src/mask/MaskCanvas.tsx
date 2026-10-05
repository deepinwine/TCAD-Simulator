import {useId, useEffect, useRef, useState, type Dispatch, type PointerEvent} from 'react';
import type {MaskAssetShape} from '../api/types';
import type {MaskEditorAction, MaskEditorState} from './types';
import {snapValue, translateShape} from './editorReducer';
import {useI18n} from '../i18n/I18nContext';
type Point = readonly [number, number];
export function MaskCanvas({
  state,
  dispatch,
  onTransientChanged,
}: {
  state: MaskEditorState;
  dispatch: Dispatch<MaskEditorAction>;
  onTransientChanged?(pending: boolean): void;
}) {
  const {t} = useI18n();
  const svg = useRef<SVGSVGElement>(null);
  const gridId = useId();
  const sequence = useRef(0);
  const [gesture, setGesture] = useState<{
    start: Point;
    end: Point;
    moving: boolean;
  } | null>(null);
  const [vertices, setVertices] = useState<Point[]>([]);
  useEffect(() => {
    setGesture(null);
    setVertices([]);
  }, [state.tool, state.asset.id, state.asset.revision]);
  useEffect(() => {
    onTransientChanged?.(gesture !== null || vertices.length > 0);
  }, [gesture, vertices.length, onTransientChanged]);
  useEffect(() => () => onTransientChanged?.(false), [onTransientChanged]);
  const [minX, minY, maxX, maxY] = state.asset.boundsNm;
  const point = (event: PointerEvent<SVGSVGElement>): Point => {
    const node = svg.current!;
    const matrix = node.getScreenCTM?.();
    let x = event.clientX,
      y = event.clientY;
    if (matrix && node.createSVGPoint) {
      const p = node.createSVGPoint();
      p.x = x;
      p.y = y;
      const transformed = p.matrixTransform(matrix.inverse());
      x = transformed.x;
      y = transformed.y;
    } else {
      const box = node.getBoundingClientRect();
      x = box.width ? minX + ((x - box.left) * (maxX - minX)) / box.width : x;
      y = box.height ? minY + ((y - box.top) * (maxY - minY)) / box.height : y;
    }
    return [snapValue(x, state.snapNm), snapValue(y, state.snapNm)];
  };
  const geometry = (start: Point, end: Point): MaskAssetShape | null => {
    const base = {id: 'preview', layerId: state.activeLayerId};
    if (state.tool === 'rectangle')
      return {
        ...base,
        type: 'rectangle',
        xNm: Math.min(start[0], end[0]),
        yNm: Math.min(start[1], end[1]),
        widthNm: Math.abs(end[0] - start[0]),
        heightNm: Math.abs(end[1] - start[1]),
        rotationDeg: 0,
      };
    if (state.tool === 'circle' || state.tool === 'hole')
      return {
        ...base,
        type: state.tool,
        cxNm: start[0],
        cyNm: start[1],
        radiusNm: Math.hypot(end[0] - start[0], end[1] - start[1]),
      };
    if (state.tool === 'line')
      return {
        ...base,
        type: 'line',
        pointsNm: [start, end],
        widthNm: state.snapNm || 10,
      };
    return null;
  };
  const draw = (shape: MaskAssetShape, preview = false) => {
    const common = {
      'data-testid': preview ? undefined : `mask-shape-${shape.id}`,
      fill: shape.type === 'hole' ? '#fff' : shape.type === 'line' ? 'none' : '#60a5fa',
      stroke: state.selection.includes(shape.id) ? '#f59e0b' : '#2563eb',
      strokeWidth: 2,
      vectorEffect: 'non-scaling-stroke' as const,
    };
    if (shape.type === 'rectangle')
      return (
        <rect
          {...common}
          x={shape.xNm}
          y={shape.yNm}
          width={shape.widthNm}
          height={shape.heightNm}
          transform={`rotate(${shape.rotationDeg} ${shape.xNm + shape.widthNm / 2} ${shape.yNm + shape.heightNm / 2})`}
        />
      );
    if ('radiusNm' in shape)
      return <circle {...common} cx={shape.cxNm} cy={shape.cyNm} r={shape.radiusNm} />;
    const points = shape.pointsNm.map((p) => p.join(',')).join(' ');
    return shape.type === 'line' ? (
      <polyline {...common} points={points} strokeWidth={shape.widthNm} vectorEffect={undefined} />
    ) : (
      <polygon {...common} points={points} />
    );
  };
  const preview = gesture && !gesture.moving ? geometry(gesture.start, gesture.end) : null;
  const dx = gesture ? gesture.end[0] - gesture.start[0] : 0,
    dy = gesture ? gesture.end[1] - gesture.start[1] : 0;
  return (
    <svg
      ref={svg}
      data-testid="mask-canvas"
      aria-label={t('workbench.canvas')}
      tabIndex={0}
      viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 320,
        touchAction: 'none',
        background: '#f8fafc',
      }}
      onKeyDown={(event) => {
        if (event.key === 'Delete' || event.key === 'Backspace') {
          event.preventDefault();
          dispatch({type: 'deleteSelection'});
        }
        if (event.key === 'Escape') {
          setGesture(null);
          setVertices([]);
        }
      }}
      onPointerDown={(event) => {
        svg.current?.focus();
        const p = point(event);
        const target = (event.target as Element).closest('[data-shape-id]');
        if (state.tool === 'select') {
          if (target) {
            const id = target.getAttribute('data-shape-id')!;
            const selection = event.shiftKey
              ? state.selection.includes(id)
                ? state.selection.filter((selected) => selected !== id)
                : [...state.selection, id]
              : state.selection.includes(id)
                ? state.selection
                : [id];
            dispatch({type: 'setSelection', selection});
            setGesture({start: p, end: p, moving: true});
          } else dispatch({type: 'setSelection', selection: []});
        } else if (state.tool === 'polygon')
          setVertices((previous) =>
            previous.length &&
            previous[previous.length - 1][0] === p[0] &&
            previous[previous.length - 1][1] === p[1]
              ? previous
              : [...previous, p],
          );
        else setGesture({start: p, end: p, moving: false});
        svg.current?.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (gesture) setGesture({...gesture, end: point(event)});
      }}
      onPointerCancel={() => setGesture(null)}
      onPointerUp={(event) => {
        if (!gesture) return;
        const end = point(event);
        if (gesture.moving)
          dispatch({
            type: 'moveSelection',
            dxNm: end[0] - gesture.start[0],
            dyNm: end[1] - gesture.start[1],
          });
        else {
          const shape = geometry(gesture.start, end);
          if (
            shape &&
            Math.hypot(end[0] - gesture.start[0], end[1] - gesture.start[1]) > 0 &&
            (shape.type !== 'rectangle' || (shape.widthNm > 0 && shape.heightNm > 0))
          )
            dispatch({
              type: 'addShape',
              shape: {
                ...shape,
                id: `shape-${Date.now()}-${++sequence.current}`,
              },
            });
        }
        setGesture(null);
      }}
      onDoubleClick={() => {
        if (state.tool === 'polygon' && vertices.length >= 3) {
          dispatch({
            type: 'addShape',
            shape: {
              id: `shape-${Date.now()}-${++sequence.current}`,
              layerId: state.activeLayerId,
              type: 'polygon',
              pointsNm: [...vertices, vertices[0]],
            },
          });
          setVertices([]);
        }
      }}
    >
      <defs>
        <pattern
          id={gridId}
          width={state.snapNm || 100}
          height={state.snapNm || 100}
          patternUnits="userSpaceOnUse"
        >
          <path
            d={`M ${state.snapNm || 100} 0 L 0 0 0 ${state.snapNm || 100}`}
            fill="none"
            stroke="#cbd5e1"
            strokeWidth="0.5"
          />
        </pattern>
      </defs>
      {state.gridVisible && (
        <rect
          x={minX}
          y={minY}
          width={maxX - minX}
          height={maxY - minY}
          fill={`url(#${gridId})`}
          pointerEvents="none"
        />
      )}
      {state.asset.shapes
        .filter((shape) =>
          state.asset.layers.some((layer) => layer.id === shape.layerId && layer.visible),
        )
        .map((shape) => (
          <g key={shape.id} data-shape-id={shape.id}>
            {draw(
              gesture?.moving && state.selection.includes(shape.id)
                ? translateShape(shape, dx, dy)
                : shape,
            )}
          </g>
        ))}
      {preview && (
        <g opacity={0.6} pointerEvents="none">
          {draw(preview, true)}
        </g>
      )}
      {vertices.length > 0 && (
        <polyline
          points={vertices.map((p) => p.join(',')).join(' ')}
          fill="none"
          stroke="#f59e0b"
          pointerEvents="none"
        />
      )}
    </svg>
  );
}
