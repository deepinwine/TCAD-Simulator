import {useEffect} from 'react';
import type {TimelineItemView} from '../api/types';
import {hasUnsavedDrafts} from '../state/appReducer';
import {useAppState} from '../state/AppStateContext';
import {ErrorNotice} from './ErrorNotice';
import {StatusBadge} from './StatusBadge';

const restoreDraftGuidanceId = 'mutation-draft-guidance';

function validNeighbors(
  items: TimelineItemView[],
  current: number,
): {previous?: number; next?: number} {
  const valid = items
    .filter(item => item.snapshotValid)
    .map(item => item.index)
    .sort((left, right) => left - right);
  if (current < 0) return {next: valid[0]};
  return {
    previous: valid.filter(index => index < current).at(-1),
    next: valid.find(index => index > current),
  };
}

export function TimelineBar() {
  const {state, actions} = useAppState();
  const timeline = state.timeline;
  const draftBlocked = hasUnsavedDrafts(state);
  const mutationActive = state.phase === 'running' || state.activeMutation !== null;
  const restoreDisabled = mutationActive || draftBlocked;
  const neighbors = timeline === null
    ? {}
    : validNeighbors(timeline.items, timeline.current);

  useEffect(() => {
    if (
      state.phase === 'ready'
      && state.activeMutation === null
      && state.timelineStatus === 'idle'
    ) {
      void actions.loadTimeline();
    }
  }, [actions, state.activeMutation, state.phase, state.timelineStatus]);

  return (
    <nav
      className="timeline-bar"
      aria-label="Process Timeline"
      aria-busy={state.timelineStatus === 'loading' || state.activeMutation === 'timeline'}
    >
      <div className="timeline-heading">
        <span className="pane-kicker">History</span>
        <strong>Timeline</strong>
        {state.historicalStepIndex !== null && (
          <span className="timeline-history-state">
            历史快照 Step {state.historicalStepIndex + 1}
          </span>
        )}
      </div>
      <div className="timeline-navigation">
        <button
          type="button"
          className="timeline-nav-button"
          disabled={restoreDisabled || neighbors.previous === undefined}
          aria-describedby={draftBlocked ? restoreDraftGuidanceId : undefined}
          onClick={() => {
            if (neighbors.previous !== undefined) void actions.restoreTimeline(neighbors.previous);
          }}
        >
          上一个有效快照
        </button>
        <button
          type="button"
          className="timeline-nav-button"
          disabled={restoreDisabled || neighbors.next === undefined}
          aria-describedby={draftBlocked ? restoreDraftGuidanceId : undefined}
          onClick={() => {
            if (neighbors.next !== undefined) void actions.restoreTimeline(neighbors.next);
          }}
        >
          下一个有效快照
        </button>
      </div>
      <div className="timeline-content">
        {state.timelineStatus === 'loading' && timeline === null && (
          <p className="timeline-empty" role="status">正在加载 Timeline…</p>
        )}
        {state.timelineError !== null && (
          <div className="timeline-error">
            <ErrorNotice
              title="Timeline 加载失败"
              message={state.timelineError.message}
              parameterPath={state.timelineError.parameterPath}
              suggestion={state.timelineError.suggestion}
              rolledBack={state.timelineError.rolledBack}
              actionLabel="重试 Timeline"
              onAction={() => void actions.loadTimeline()}
            />
          </div>
        )}
        {timeline !== null && timeline.items.length === 0 && (
          <p className="timeline-empty">当前没有 Timeline 快照</p>
        )}
        {timeline !== null && timeline.items.length > 0 && (
          <ol className="timeline-items">
            {timeline.items.map(item => {
              const current = item.index === timeline.current;
              return (
                <li
                  key={`${item.index}:${item.state}`}
                  className={current ? 'timeline-item is-current' : 'timeline-item'}
                  aria-current={current ? 'step' : undefined}
                >
                  <button
                    type="button"
                    className="timeline-restore-button"
                    aria-label={`恢复步骤 ${item.index + 1}`}
                    aria-describedby={draftBlocked ? restoreDraftGuidanceId : undefined}
                    disabled={restoreDisabled || !item.snapshotValid}
                    onClick={() => void actions.restoreTimeline(item.index)}
                  >
                    <span>#{item.index + 1} {item.state}</span>
                    <StatusBadge status={item.runtimeStatus} />
                    <span>{item.snapshotValid ? '快照有效' : '无有效快照'}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </nav>
  );
}
