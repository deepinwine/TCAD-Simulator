import {useRef, type KeyboardEvent} from 'react';
import type {StepView} from '../api/types';
import {StatusBadge} from './StatusBadge';

interface ProcessFlowPaneProps {
  recipe: StepView[];
  selectedStepIndex: number | null;
  onSelect(index: number): void;
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

export function summarizeParams(params: Record<string, unknown>): string {
  const entries = Object.entries(params).slice(0, 2);
  if (entries.length === 0) return '无参数';
  const summary = entries
    .map(([key, value]) => `${compactText(key, 16)}=${summarizeValue(value)}`)
    .join(' · ');
  const suffix = Object.keys(params).length > 2 ? ' · …' : '';
  return compactText(`${summary}${suffix}`, 92);
}

export function ProcessFlowPane({recipe, selectedStepIndex, onSelect}: ProcessFlowPaneProps) {
  const optionRefs = useRef(new Map<number, HTMLButtonElement>());
  const selectedPosition = recipe.findIndex(step => step.index === selectedStepIndex);
  const tabStopPosition = selectedPosition >= 0 ? selectedPosition : 0;

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
    if (target !== undefined) optionRefs.current.get(target.index)?.focus();
  }

  return (
    <section className="workspace-pane process-pane" aria-label="Process Flow">
      <header className="pane-header">
        <div>
          <span className="pane-kicker">Recipe</span>
          <h2>Process Flow</h2>
        </div>
        <span className="pane-count" aria-label={`${recipe.length} 个步骤`}>{recipe.length}</span>
      </header>
      {recipe.length === 0 ? (
        <p className="pane-empty">当前配方没有工艺步骤</p>
      ) : (
        <div className="process-list" role="listbox" aria-label="Process Flow">
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
              tabIndex={position === tabStopPosition ? 0 : -1}
              data-process-enabled={step.enabled}
              className="process-step"
              onClick={() => onSelect(step.index)}
              onKeyDown={event => handleOptionKeyDown(event, position, step.index)}
            >
              <span className="step-index" aria-hidden="true">
                {String(step.index + 1).padStart(2, '0')}
              </span>
              <span className="step-content">
                <span className="step-heading-row">
                  <strong className="step-title">{step.instanceName}</strong>
                  {!step.enabled && <span className="disabled-copy">已禁用</span>}
                </span>
                <span className="step-subtitle">{step.name} · {summarizeParams(step.params)}</span>
                <StatusBadge status={step.runtimeStatus} />
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
