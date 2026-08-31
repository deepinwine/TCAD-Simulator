import type {TimelineView} from '../api/types';
import {StatusBadge} from './StatusBadge';

interface TimelineBarProps {
  timeline: TimelineView | null;
}

export function TimelineBar({timeline}: TimelineBarProps) {
  return (
    <nav className="timeline-bar" aria-label="Process Timeline">
      <div className="timeline-heading">
        <span className="pane-kicker">History</span>
        <strong>Timeline</strong>
      </div>
      {timeline === null ? (
        <p className="timeline-empty">Timeline 尚未加载</p>
      ) : timeline.items.length === 0 ? (
        <p className="timeline-empty">当前没有 Timeline 快照</p>
      ) : (
        <ol className="timeline-items">
          {timeline.items.map(item => (
            <li
              key={`${item.index}:${item.state}`}
              className={item.index === timeline.current ? 'timeline-item is-current' : 'timeline-item'}
              aria-current={item.index === timeline.current ? 'step' : undefined}
            >
              <span>#{item.index + 1} {item.state}</span>
              <StatusBadge status={item.runtimeStatus} />
              <span>{item.snapshotValid ? '快照有效' : '无有效快照'}</span>
            </li>
          ))}
        </ol>
      )}
    </nav>
  );
}
