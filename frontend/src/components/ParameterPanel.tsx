import {type KeyboardEvent, useEffect, useRef, useState} from 'react';
import type {TcadApiError} from '../api/client';
import type {ParameterChoiceValue, ParameterSpecView, StepView} from '../api/types';
import {parameterDraftKey} from '../state/appReducer';
import {useAppState} from '../state/AppStateContext';
import {ErrorNotice} from './ErrorNotice';
import {StatusBadge} from './StatusBadge';
import {validateParameter} from './parameterValidation';

interface ParameterPanelProps {
  step: StepView | null;
  collapsed: boolean;
}

interface ParameterFieldProps {
  stepIndex: number;
  spec: ParameterSpecView;
  serverValue: unknown;
  disabled: boolean;
  serverError?: TcadApiError;
}

type DisplayValue = string | boolean;

interface ParameterControlProps {
  spec: ParameterSpecView;
  inputId: string;
  displayValue: DisplayValue;
  disabled: boolean;
  hasError: boolean;
  describedBy?: string;
  onUpdate(raw: unknown, display: DisplayValue): void;
  onFlush(): void;
}

function safeText(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  try {
    const serialized = JSON.stringify(value);
    return serialized ?? '';
  } catch {
    return '无法显示的复杂值';
  }
}

function isChoice(spec: ParameterSpecView): boolean {
  return spec.type === 'choice' || spec.type === 'enum';
}

function isBoolean(spec: ParameterSpecView): boolean {
  return spec.type === 'bool' || spec.type === 'boolean';
}

function choiceIndex(
  choices: readonly (readonly [ParameterChoiceValue, string])[] | undefined,
  value: unknown,
): string {
  const index = choices?.findIndex(([candidate]) => Object.is(candidate, value)) ?? -1;
  return index < 0 ? '' : String(index);
}

function initialDisplayValue(spec: ParameterSpecView, value: unknown): DisplayValue {
  if (isChoice(spec)) return choiceIndex(spec.choices, value);
  if (isBoolean(spec)) {
    if (value === true || value === 1) return true;
    if (typeof value === 'string') {
      return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
    }
    return false;
  }
  return safeText(value);
}

function parameterDescription(spec: ParameterSpecView): string {
  const parts: string[] = [];
  if (spec.tooltip) parts.push(spec.tooltip);
  if (spec.minimum !== undefined || spec.maximum !== undefined) {
    const minimum = spec.minimum === undefined ? '不限' : String(spec.minimum);
    const maximum = spec.maximum === undefined ? '不限' : String(spec.maximum);
    parts.push(`范围 ${minimum} 至 ${maximum}`);
  }
  if (spec.step !== undefined) parts.push(`步进 ${spec.step}`);
  if (spec.decimals !== undefined) parts.push(`显示精度 ${spec.decimals} 位小数`);
  return parts.join('；');
}

function ParameterControl({
  spec,
  inputId,
  displayValue,
  disabled,
  hasError,
  describedBy,
  onUpdate,
  onFlush,
}: ParameterControlProps) {
  const handleKeyDown = (
    event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    if (event.key !== 'Enter') return;
    if (event.currentTarget.tagName !== 'SELECT') event.preventDefault();
    onFlush();
  };

  const accessibility = {
    disabled,
    'aria-invalid': hasError,
    'aria-describedby': describedBy,
  };

  if (isChoice(spec)) {
    return (
      <select
        id={inputId}
        value={typeof displayValue === 'string' ? displayValue : ''}
        {...accessibility}
        onChange={event => {
          const selectedIndex = Number(event.currentTarget.value);
          const value = spec.choices?.[selectedIndex]?.[0];
          onUpdate(value, event.currentTarget.value);
        }}
        onBlur={onFlush}
        onKeyDown={handleKeyDown}
      >
        <option value="" disabled>请选择</option>
        {spec.choices?.map(([value, label], index) => (
          <option key={index} value={String(index)}>{label || safeText(value)}</option>
        ))}
      </select>
    );
  }

  if (isBoolean(spec)) {
    return (
      <input
        id={inputId}
        type="checkbox"
        checked={displayValue === true}
        {...accessibility}
        onChange={event => onUpdate(event.currentTarget.checked, event.currentTarget.checked)}
        onBlur={onFlush}
      />
    );
  }

  if (spec.type === 'text' || spec.type === 'string') {
    return (
      <textarea
        id={inputId}
        value={typeof displayValue === 'string' ? displayValue : ''}
        {...accessibility}
        title={spec.tooltip}
        onChange={event => onUpdate(event.currentTarget.value, event.currentTarget.value)}
        onBlur={onFlush}
        onKeyDown={handleKeyDown}
      />
    );
  }

  const numeric = spec.type === 'float' || spec.type === 'int' || spec.type === 'integer';
  return (
    <input
      id={inputId}
      type="text"
      inputMode={numeric ? 'decimal' : 'text'}
      value={typeof displayValue === 'string' ? displayValue : ''}
      {...accessibility}
      title={spec.tooltip}
      onChange={event => onUpdate(event.currentTarget.value, event.currentTarget.value)}
      onBlur={onFlush}
      onKeyDown={handleKeyDown}
    />
  );
}

function ParameterField({
  stepIndex,
  spec,
  serverValue,
  disabled,
  serverError,
}: ParameterFieldProps) {
  const {state, actions} = useAppState();
  const key = parameterDraftKey(stepIndex, spec.key);
  const draft = state.drafts[key];
  const inputId = `parameter-${stepIndex}-${spec.key}`;
  const unitsId = spec.units ? `${inputId}-units` : undefined;
  const descriptionId = `${inputId}-description`;
  const validationId = `${inputId}-validation`;
  const serverErrorId = serverError === undefined
    ? undefined
    : `parameter-server-error-${stepIndex}-${spec.key}`;
  const initialValue = serverValue === undefined ? spec.defaultValue : serverValue;
  const [displayValue, setDisplayValue] = useState<DisplayValue>(
    () => draft?.rawValue ?? initialDisplayValue(spec, initialValue),
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const validDraftRef = useRef(false);
  const description = parameterDescription(spec);
  const clientError = draft?.validation.status === 'invalid'
    ? draft.validation.message ?? '参数值无效'
    : undefined;
  const hasError = clientError !== undefined || serverErrorId !== undefined;
  const describedBy = [
    unitsId,
    description ? descriptionId : undefined,
    clientError ? validationId : undefined,
    serverErrorId,
  ];
  const uniqueDescriptions = [...new Set(
    describedBy.filter((value): value is string => value !== undefined),
  )].join(' ') || undefined;

  const clearTimer = () => {
    if (timerRef.current === null) return;
    clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  useEffect(() => {
    if (draft !== undefined) {
      if (draft.rawValue !== undefined) setDisplayValue(draft.rawValue);
      validDraftRef.current = draft.validation.status === 'valid';
      return;
    }
    setDisplayValue(initialDisplayValue(spec, initialValue));
    validDraftRef.current = false;
  }, [draft, initialValue, spec]);

  useEffect(() => {
    if (disabled) clearTimer();
  }, [disabled]);

  useEffect(() => () => clearTimer(), []);

  const update = (raw: unknown, display: DisplayValue) => {
    if (disabled) return;
    clearTimer();
    setDisplayValue(display);
    const validation = validateParameter(spec, raw);
    validDraftRef.current = validation.ok;
    if (!validation.ok) {
      actions.updateDraft(
        stepIndex,
        spec.key,
        raw,
        {status: 'invalid', message: validation.message},
        display,
      );
      return;
    }
    actions.updateDraft(
      stepIndex,
      spec.key,
      validation.value,
      {status: 'valid'},
      display,
    );
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void actions.saveParameter(stepIndex, spec.key);
    }, 350);
  };

  const flush = () => {
    clearTimer();
    if (!disabled && validDraftRef.current) {
      void actions.saveParameter(stepIndex, spec.key);
    }
  };

  return (
    <div className={`parameter-field${hasError ? ' has-error' : ''}`}>
      <div className="parameter-label-row">
        <label htmlFor={inputId}>{spec.label || spec.key}</label>
        {spec.units && (
          <span id={unitsId} className="parameter-units">{spec.units}</span>
        )}
      </div>
      <ParameterControl
        spec={spec}
        inputId={inputId}
        displayValue={displayValue}
        disabled={disabled}
        hasError={hasError}
        describedBy={uniqueDescriptions}
        onUpdate={update}
        onFlush={flush}
      />
      {description && <p id={descriptionId} className="parameter-help">{description}</p>}
      {clientError && <p id={validationId} className="parameter-error">{clientError}</p>}
      {serverError !== undefined && (
        <div id={serverErrorId} className="parameter-server-error" role="alert">
          <strong>{serverError.message}</strong>
          {serverError.parameterPath && <span>参数路径：{serverError.parameterPath}</span>}
          {serverError.suggestion && <span>建议：{serverError.suggestion}</span>}
        </div>
      )}
    </div>
  );
}

export function ParameterPanel({step, collapsed}: ParameterPanelProps) {
  const {state} = useAppState();
  const disabled = state.phase === 'running' || state.activeMutation !== null;
  const runError = step === null ? undefined : state.stepErrors[step.index];

  return (
    <section
      id="parameter-panel"
      className="workspace-pane parameter-pane"
      aria-label="Parameters"
      aria-busy={disabled}
      hidden={collapsed}
    >
      <header className="pane-header">
        <div>
          <span className="pane-kicker">Inspector</span>
          <h2>Parameters</h2>
        </div>
      </header>
      {step === null ? (
        <p className="pane-empty">选择一个工艺步骤以查看参数</p>
      ) : (
        <div className="parameter-summary">
          <div className="selected-step-heading">
            <div>
              <span className="selection-label">当前步骤</span>
              <h3>{step.instanceName}</h3>
              <p>{step.name}</p>
            </div>
            <StatusBadge status={step.runtimeStatus} />
          </div>
          {runError !== undefined && (
            <ErrorNotice
              title="步骤执行失败"
              message={runError.message}
              parameterPath={runError.parameterPath}
              suggestion={runError.suggestion}
              rolledBack={runError.rolledBack}
            />
          )}
          {step.parameterSpecs.length === 0 ? (
            <p className="pane-empty">此步骤没有可编辑参数</p>
          ) : (
            <form className="parameter-form" onSubmit={event => event.preventDefault()}>
              {step.parameterSpecs.map(spec => {
                const serverValue = Object.hasOwn(step.params, spec.key)
                  ? step.params[spec.key]
                  : spec.defaultValue;
                return (
                  <ParameterField
                    key={`${step.index}:${spec.key}`}
                    stepIndex={step.index}
                    spec={spec}
                    serverValue={serverValue}
                    disabled={disabled}
                    serverError={state.parameterErrors[
                      parameterDraftKey(step.index, spec.key)
                    ]?.error}
                  />
                );
              })}
            </form>
          )}
        </div>
      )}
    </section>
  );
}
