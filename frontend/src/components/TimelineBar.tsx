import {useEffect} from 'react';
import type {TimelineItemView} from '../api/types';
import {hasUnsavedDrafts} from '../state/appReducer';
import {useAppState} from '../state/AppStateContext';
import {useI18n} from '../i18n/I18nContext';
import {ErrorNotice} from './ErrorNotice';
import {StatusBadge} from './StatusBadge';
import type {TranslationKey} from '../i18n/catalogs';

const restoreDraftGuidanceId = 'mutation-draft-guidance';
const timelineStateKeys: Partial<Record<string, TranslationKey>> = {
  current: 'timeline.state.current',
  pending: 'timeline.state.pending',
  ready: 'timeline.state.ready',
  dirty: 'timeline.state.dirty',
  done: 'timeline.state.done',
  error: 'timeline.state.error',
};

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
  const {t} = useI18n();
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
      aria-label={t('timeline.region')}
      aria-busy={state.timelineStatus === 'loading' || state.activeMutation === 'timeline'}
    >
      <div className="timeline-heading">
        <span className="pane-kicker">{t('timeline.kicker')}</span>
        <strong>{t('timeline.title')}</strong>
        {state.historicalStepIndex !== null && (
          <span className="timeline-history-state">
            {t('timeline.historySnapshot', {step: state.historicalStepIndex + 1})}
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
          {t('timeline.previous')}
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
          {t('timeline.next')}
        </button>
      </div>
      <div className="timeline-content">
        {state.timelineStatus === 'loading' && timeline === null && (
          <p className="timeline-empty" role="status">{t('timeline.loading')}</p>
        )}
        {state.timelineError !== null && (
          <div className="timeline-error">
            <ErrorNotice
              title={t('timeline.loadError')}
              error={state.timelineError}
              parameterPath={state.timelineError.parameterPath}
              suggestion={state.timelineError.suggestion}
              rolledBack={state.timelineError.rolledBack}
              actionLabel={t('timeline.retry')}
              onAction={() => void actions.loadTimeline()}
            />
          </div>
        )}
        {timeline !== null && timeline.items.length === 0 && (
          <p className="timeline-empty">{t('timeline.empty')}</p>
        )}
        {timeline !== null && timeline.items.length > 0 && (
          <ol className="timeline-items">
            {timeline.items.map(item => {
              const current = item.index === timeline.current;
              const stateKey = timelineStateKeys[item.state];
              return (
                <li
                  key={`${item.index}:${item.state}`}
                  className={current ? 'timeline-item is-current' : 'timeline-item'}
                  aria-current={current ? 'step' : undefined}
                >
                  <button
                    type="button"
                    className="timeline-restore-button"
                    aria-label={t('timeline.restoreStep', {step: item.index + 1})}
                    aria-describedby={draftBlocked ? restoreDraftGuidanceId : undefined}
                    disabled={restoreDisabled || !item.snapshotValid}
                    onClick={() => void actions.restoreTimeline(item.index)}
                  >
                    <span>#{item.index + 1} {stateKey === undefined ? t('timeline.state.unknown') : t(stateKey)}</span>
                    <StatusBadge status={item.runtimeStatus} />
                    <span>{item.snapshotValid ? t('timeline.valid') : t('timeline.invalid')}</span>
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
