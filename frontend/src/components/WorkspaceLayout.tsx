import {useRef, useState, type CSSProperties, type ReactNode} from 'react';
import {useI18n} from '../i18n/I18nContext';
const bounds = {left: [220, 420], right: [260, 480]} as const;
export function WorkspaceLayout({left, viewer, parameters, collapsed}: {left: ReactNode; viewer: ReactNode; parameters: ReactNode; collapsed: boolean}) {
  const {locale} = useI18n();
  const [widths, setWidths] = useState({left: 280, right: 320});
  const drag = useRef<{side: 'left' | 'right'; pointerId: number; startX: number; width: number} | null>(null);
  function resize(side: 'left' | 'right', width: number) {setWidths(current => ({...current, [side]: Math.max(bounds[side][0], Math.min(bounds[side][1], width))}));}
  function separator(side: 'left' | 'right') {
    return <div className="workspace-separator" role="separator" tabIndex={0} aria-orientation="vertical" aria-label={locale === 'en' ? `${side} pane width` : side === 'left' ? '步骤栏宽度' : '参数栏宽度'} aria-valuemin={bounds[side][0]} aria-valuemax={bounds[side][1]} aria-valuenow={widths[side]} hidden={side === 'right' && collapsed}
      onKeyDown={event => {const direction = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0; if (direction) {event.preventDefault(); resize(side, widths[side] + direction * (side === 'left' ? 20 : -20));} else if (event.key === 'Home' || event.key === 'End') {event.preventDefault(); resize(side, bounds[side][event.key === 'Home' ? 0 : 1]);}}}
      onPointerDown={event => {if (event.button !== 0) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = {side, pointerId: event.pointerId, startX: event.clientX, width: widths[side]};}}
      onPointerMove={event => {const active = drag.current; if (!active || active.side !== side || active.pointerId !== event.pointerId) return; resize(side, active.width + (event.clientX - active.startX) * (side === 'left' ? 1 : -1));}}
      onPointerUp={event => {if (drag.current?.pointerId === event.pointerId) {drag.current = null; event.currentTarget.releasePointerCapture(event.pointerId);}}}
      onPointerCancel={() => {drag.current = null;}} onLostPointerCapture={() => {drag.current = null;}} />;
  }
  return <div className={`studio-workspace resizable-workspace${collapsed ? ' parameters-collapsed' : ''}`} style={{'--flow-width': `${widths.left}px`, '--parameter-width': `${widths.right}px`} as CSSProperties}>
    <div className="workspace-left">{left}</div>{separator('left')}
    <div className="workspace-viewer">{viewer}</div>{separator('right')}
    <div className="workspace-parameters" hidden={collapsed}>{parameters}</div>
  </div>;
}
