import {useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode} from 'react';
import type {MaterialView, StepView} from '../api/types';
import {presentStep} from './stepPresentation';
import {useI18n} from '../i18n/I18nContext';
import {zhCN} from '../i18n/catalogs';
import {StatusBadge} from './StatusBadge';

interface ProcessFlowPaneProps {
  recipe: StepView[];
  selectedStepIndex: number | null;
  onSelect(index: number): void;
  children?: ReactNode;
  materials?: MaterialView[];
}

function compactText(value: string, limit = 28): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length <= limit ? normalized : `${normalized.slice(0, limit - 1)}…`;
}

function summarizeValue(value: unknown, depth = 0): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return compactText(value);
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (value === undefined) return '—';
  if (depth >= 1) return '…';
  if (Array.isArray(value)) {
    const values = value.slice(0, 3).map(item => summarizeValue(item, depth + 1));
    return `[${values.join(', ')}${value.length > 3 ? ', …' : ''}]`;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).slice(0, 2);
    if (entries.length === 0) return '{}';
    const body = entries.map(([key, item]) => `${compactText(key, 12)}: ${summarizeValue(item, depth + 1)}`);
    return `{${body.join(', ')}${Object.keys(value).length > 2 ? ', …' : ''}}`;
  }
  return '—';
}

export function summarizeParams(
  params: Record<string, unknown>,
  emptyLabel: string = zhCN['process.noParams'],
): string {
  const entries = Object.entries(params).slice(0, 2);
  if (entries.length === 0) return emptyLabel;
  const summary = entries
    .map(([key, value]) => `${compactText(key, 16)}=${summarizeValue(value)}`)
    .join(' · ');
  const suffix = Object.keys(params).length > 2 ? ' · …' : '';
  return compactText(`${summary}${suffix}`, 92);
}

export function ProcessFlowPane({recipe, selectedStepIndex, onSelect, children, materials = []}: ProcessFlowPaneProps) {
  const {t, locale} = useI18n();
  const optionRefs = useRef(new Map<number, HTMLButtonElement>());
  const pendingFocusRef = useRef<number | null>(null);
  const [activeStepIndex, setActiveStepIndex] = useState<number | null>(() => {
    const selectedExists = recipe.some(step => step.index === selectedStepIndex);
    return selectedExists ? selectedStepIndex : recipe[0]?.index ?? null;
  });

  useLayoutEffect(() => {
    const selectedExists = recipe.some(step => step.index === selectedStepIndex);
    const nextActive = selectedExists ? selectedStepIndex : recipe[0]?.index ?? null;
    setActiveStepIndex(current => current === nextActive ? current : nextActive);
    if (!recipe.some(step => step.index === pendingFocusRef.current)) {
      pendingFocusRef.current = null;
    }
  }, [recipe, selectedStepIndex]);

  useLayoutEffect(() => {
    if (pendingFocusRef.current !== activeStepIndex || activeStepIndex === null) return;
    const target = optionRefs.current.get(activeStepIndex);
    pendingFocusRef.current = null;
    target?.focus();
  }, [activeStepIndex, recipe]);

  function handleOptionKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    position: number,
    stepIndex: number,
  ) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (!event.repeat) onSelect(stepIndex);
      return;
    }

    let nextPosition: number | null = null;
    if (event.key === 'ArrowDown') nextPosition = Math.min(recipe.length - 1, position + 1);
    if (event.key === 'ArrowUp') nextPosition = Math.max(0, position - 1);
    if (event.key === 'Home') nextPosition = 0;
    if (event.key === 'End') nextPosition = recipe.length - 1;
    if (nextPosition === null) return;

    event.preventDefault();
    const target = recipe[nextPosition];
    if (target === undefined) return;
    if (target.index === activeStepIndex) {
      optionRefs.current.get(target.index)?.focus();
      return;
    }
    pendingFocusRef.current = target.index;
    setActiveStepIndex(target.index);
  }

  return (
    <section className="workspace-pane process-pane" aria-label={t('process.region')}>
      <header className="pane-header">
        <div>
          <span className="pane-kicker">{t('process.kicker')}</span>
          <h2>{t('process.title')}</h2>
        </div>
        <span className="pane-count" aria-label={t('process.stepCount', {count: recipe.length})}>{recipe.length}</span>
      </header>
      {recipe.length === 0 ? (
        <p className="pane-empty">{t('process.empty')}</p>
      ) : (
        <div className="process-list" role="listbox" aria-label={t('process.region')}>
          {recipe.map((step, position) => (
            <button
              key={step.index}
              ref={element => {
                if (element === null) optionRefs.current.delete(step.index);
                else optionRefs.current.set(step.index, element);
              }}
              type="button"
              role="option"
              aria-selected={step.index === selectedStepIndex}
              tabIndex={step.index === activeStepIndex ? 0 : -1}
              data-process-enabled={step.enabled}
              className="process-step"
              onClick={() => onSelect(step.index)}
              onFocus={() => setActiveStepIndex(step.index)}
              onKeyDown={event => handleOptionKeyDown(event, position, step.index)}
            >
              <span className="step-index" aria-hidden="true">
                {String(step.index + 1).padStart(2, '0')}
              </span>
              <span className="step-content">
                <span className="step-heading-row">
                  <strong className="step-title">{presentStep(step, materials, locale).title}</strong>
                  {!step.enabled && <span className="disabled-copy">{t('process.disabled')}</span>}
                </span>
                <span className="step-subtitle">{presentStep(step, materials, locale).type} · {summarizeParams(step.params, t('process.noParams'))}</span>
                <StatusBadge status={step.runtimeStatus} />
              </span>
            </button>
          ))}
        </div>
      )}
      {children}
    </section>
  );
}
