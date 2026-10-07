import {useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode} from 'react';
import {useI18n} from '../i18n/I18nContext';
const bounds = {left: [220, 420], right: [260, 480]} as const;
const minimumViewerWidth = 260;
type PaneWidths = {left: number; right: number};

function maximumWidth(side: 'left' | 'right', widths: PaneWidths, available: number, collapsed: boolean): number {
  // At <=900px CSS stacks the panes, so their horizontal widths are inactive.
  if (available <= 900) return bounds[side][1];
  const otherWidth = side === 'left' ? (collapsed ? 0 : widths.right) : widths.left;
  const separators = collapsed ? 6 : 12;
  return Math.max(bounds[side][0], Math.min(bounds[side][1], available - otherWidth - minimumViewerWidth - separators));
}

function fitWidths(widths: PaneWidths, available: number, collapsed: boolean): PaneWidths {
  const left = Math.min(widths.left, maximumWidth('left', widths, available, collapsed));
  const right = collapsed ? widths.right : Math.min(widths.right, maximumWidth('right', {...widths, left}, available, collapsed));
  return left === widths.left && right === widths.right ? widths : {left, right};
}
export function WorkspaceLayout({left, viewer, parameters, collapsed}: {left: ReactNode; viewer: ReactNode; parameters: ReactNode; collapsed: boolean}) {
  const {locale} = useI18n();
  const [widths, setWidths] = useState({left: 280, right: 320});
  const [availableWidth, setAvailableWidth] = useState(0);
  const workspace = useRef<HTMLDivElement>(null);
  const drag = useRef<{side: 'left' | 'right'; pointerId: number; startX: number; width: number} | null>(null);
  useLayoutEffect(() => {
    const element = workspace.current;
    if (!element) return;
    const measure = () => {
      const available = element.getBoundingClientRect().width;
      setAvailableWidth(available);
      setWidths(current => fitWidths(current, available, collapsed));
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [collapsed]);
  function resize(side: 'left' | 'right', width: number) {
    const available = workspace.current?.getBoundingClientRect().width ?? availableWidth;
    setAvailableWidth(available);
    setWidths(current => {
      const fitted = fitWidths(current, available, collapsed);
      return {...fitted, [side]: Math.max(bounds[side][0], Math.min(maximumWidth(side, fitted, available, collapsed), width))};
    });
  }
  function separator(side: 'left' | 'right') {
    return <div className="workspace-separator" role="separator" tabIndex={0} aria-orientation="vertical" aria-label={locale === 'en' ? `${side} pane width` : side === 'left' ? '步骤栏宽度' : '参数栏宽度'} aria-valuemin={bounds[side][0]} aria-valuemax={maximumWidth(side, widths, availableWidth, collapsed)} aria-valuenow={widths[side]} hidden={side === 'right' && collapsed}
      onKeyDown={event => {const direction = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0; if (direction) {event.preventDefault(); resize(side, widths[side] + direction * (side === 'left' ? 20 : -20));} else if (event.key === 'Home' || event.key === 'End') {event.preventDefault(); resize(side, bounds[side][event.key === 'Home' ? 0 : 1]);}}}
      onPointerDown={event => {if (event.button !== 0) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = {side, pointerId: event.pointerId, startX: event.clientX, width: widths[side]};}}
      onPointerMove={event => {const active = drag.current; if (!active || active.side !== side || active.pointerId !== event.pointerId) return; resize(side, active.width + (event.clientX - active.startX) * (side === 'left' ? 1 : -1));}}
      onPointerUp={event => {if (drag.current?.pointerId === event.pointerId) {drag.current = null; event.currentTarget.releasePointerCapture(event.pointerId);}}}
      onPointerCancel={() => {drag.current = null;}} onLostPointerCapture={() => {drag.current = null;}} />;
  }
  return <div ref={workspace} className={`studio-workspace resizable-workspace${collapsed ? ' parameters-collapsed' : ''}`} style={{'--flow-width': `${widths.left}px`, '--parameter-width': `${widths.right}px`} as CSSProperties}>
    <div className="workspace-left">{left}</div>{separator('left')}
    <div className="workspace-viewer">{viewer}</div>{separator('right')}
    <div className="workspace-parameters" hidden={collapsed}>{parameters}</div>
  </div>;
}
