import {type KeyboardEvent, useEffect, useRef, useState} from 'react';
import type {TcadApiError} from '../api/client';
import type {ParameterChoiceValue, ParameterSpecView, StepView} from '../api/types';
import {parameterDraftKey} from '../state/appReducer';
import {useAppState} from '../state/AppStateContext';
import {type I18nContextValue, useI18n} from '../i18n/I18nContext';
import type {TranslationKey} from '../i18n/catalogs';
import {MaskControl} from './MaskControl';
import {ErrorNotice} from './ErrorNotice';
import {StatusBadge} from './StatusBadge';
import {validateParameter} from './parameterValidation';
import {toCanonical, fromCanonical, formatDisplayValue, type Dimension, type DisplayUnit} from '../units/units';

interface ParameterPanelProps {
  step: StepView | null;
  collapsed: boolean;
}

interface ParameterFieldProps {
  stepIndex: number;
  stepName: string;
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
  tooltip?: string;
  onUpdate(raw: unknown, display: DisplayValue): void;
  onFlush(): void;
}

type Translate = I18nContextValue['t'];

function conversionSpec(spec: ParameterSpecView): {dimension: Dimension; units: DisplayUnit[]; preferred: DisplayUnit} | null {
  if (!['float', 'int', 'integer'].includes(spec.type) || !spec.dimension || !spec.canonicalUnit || !spec.displayUnits?.length) return null;
  const dimension = spec.dimension as Dimension;
  const canonicalUnits: Record<Dimension, string> = {length: 'nm', time: 's', angle: 'degree', rate: 'nm/s'};
  if (!Object.hasOwn(canonicalUnits, dimension) || canonicalUnits[dimension] !== spec.canonicalUnit) return null;
  const units = spec.displayUnits as DisplayUnit[];
  const canonicalDisplay = spec.canonicalUnit === 'degree' ? '°' : spec.canonicalUnit;
  try {
    for (const unit of units) toCanonical(0, dimension, unit);
    return {dimension, units, preferred: units.includes(canonicalDisplay as DisplayUnit) ? canonicalDisplay as DisplayUnit : units[0]};
  } catch { return null; }
}

const capabilityKeys: Record<string, TranslationKey> = {
  exact: 'capability.exact', approximate: 'capability.approximate',
  estimated: 'capability.estimated', unsupported: 'capability.unsupported',
};

function safeText(value: unknown, t: Translate): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  try {
    const serialized = JSON.stringify(value);
    return serialized ?? '';
  } catch {
    return t('parameter.unavailableValue');
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

function initialDisplayValue(spec: ParameterSpecView, value: unknown, t: Translate): DisplayValue {
  if (isChoice(spec)) return choiceIndex(spec.choices, value);
  if (isBoolean(spec)) {
    if (value === true || value === 1) return true;
    if (typeof value === 'string') {
      return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
    }
    return false;
  }
  return safeText(value, t);
}

const tooltipKeys: Record<string, TranslationKey> = {
  'Initialize Wafer.box_thickness_nm': 'parameter.tooltip.initializeWafer.boxThickness',
  'Etch.rate_model': 'parameter.tooltip.etch.rateModel',
  'Etch.rate_override': 'parameter.tooltip.etch.rateOverride',
  'Etch.stop_on_material': 'parameter.tooltip.etch.stopOnMaterial',
  'Mask Exposure.advanced_enable': 'parameter.tooltip.maskExposure.advancedEnable',
  'Mask Exposure.opc_enable': 'parameter.tooltip.maskExposure.opcEnable',
};

function resolvedTooltip(
  stepName: string,
  spec: ParameterSpecView,
  locale: I18nContextValue['locale'],
  t: Translate,
): string | undefined {
  if (!spec.tooltip) return undefined;
  const key = tooltipKeys[`${stepName}.${spec.key}`];
  if (key !== undefined) return t(key);
  return locale === 'en' ? spec.tooltip : t('parameter.technicalHelp');
}

function parameterDescription(spec: ParameterSpecView, tooltip: string | undefined, t: Translate): string {
  const parts: string[] = [];
  if (tooltip) parts.push(tooltip);
  if (spec.minimum !== undefined || spec.maximum !== undefined) {
    const minimum = spec.minimum === undefined ? t('parameter.unbounded') : String(spec.minimum);
    const maximum = spec.maximum === undefined ? t('parameter.unbounded') : String(spec.maximum);
    parts.push(t('parameter.range', {minimum, maximum}));
  }
  if (spec.step !== undefined) parts.push(t('parameter.step', {step: spec.step}));
  if (spec.decimals !== undefined) parts.push(t('parameter.decimals', {decimals: spec.decimals}));
  return parts.join(t('common.listSeparator'));
}

function validationMessage(
  messageKey: string | undefined,
  spec: ParameterSpecView,
  t: Translate,
): string {
  switch (messageKey) {
    case 'validation.finite':
    case 'validation.integer':
    case 'validation.safeInteger':
    case 'validation.boolean':
    case 'validation.choice':
    case 'validation.unsupported':
      return t(messageKey);
    case 'validation.minimum':
      return t(messageKey, {minimum: spec.minimum ?? ''});
    case 'validation.maximum':
      return t(messageKey, {maximum: spec.maximum ?? ''});
    default:
      return t('parameter.invalid');
  }
}

function ParameterControl({
  spec,
  inputId,
  displayValue,
  disabled,
  hasError,
  describedBy,
  tooltip,
  onUpdate,
  onFlush,
}: ParameterControlProps) {
  const {t} = useI18n();
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
        title={tooltip}
        {...accessibility}
        onChange={event => {
          const selectedIndex = Number(event.currentTarget.value);
          const value = spec.choices?.[selectedIndex]?.[0];
          onUpdate(value, event.currentTarget.value);
        }}
        onBlur={onFlush}
        onKeyDown={handleKeyDown}
      >
        <option value="" disabled>{t('parameter.choicePlaceholder')}</option>
        {spec.choices?.map(([value, label], index) => (
          <option key={index} value={String(index)}>{label || safeText(value, t)}</option>
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
        title={tooltip}
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
        title={tooltip}
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
      title={tooltip}
      onChange={event => onUpdate(event.currentTarget.value, event.currentTarget.value)}
      onBlur={event => {
        if (event.relatedTarget?.getAttribute('data-unit-control') !== 'true') onFlush();
      }}
      onKeyDown={handleKeyDown}
    />
  );
}

function ParameterField({
  stepIndex,
  stepName,
  spec,
  serverValue,
  disabled,
  serverError,
}: ParameterFieldProps) {
  const {state, actions} = useAppState();
  const {locale, t} = useI18n();
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
  const conversion = conversionSpec(spec);
  const preferenceKey = `tcad.unit.v1:${stepName}:${spec.key}`;
  const [displayUnit, setDisplayUnit] = useState<DisplayUnit | undefined>(() => {
    if (!conversion) return undefined;
    let stored: string | null = null;
    try { stored = window.localStorage.getItem(preferenceKey); } catch { /* Session preference still works. */ }
    const preferred = draft?.displayUnit ?? stored;
    return conversion.units.includes(preferred as DisplayUnit) ? preferred as DisplayUnit : conversion.preferred;
  });
  const canonicalDisplay = (value: unknown, unit = displayUnit): DisplayValue => {
    if (!conversion || unit === undefined || typeof value !== 'number') return initialDisplayValue(spec, value, t);
    return formatDisplayValue(fromCanonical(value, conversion.dimension, unit), spec.decimals ?? 2);
  };
  const [displayValue, setDisplayValue] = useState<DisplayValue>(
    () => draft?.rawValue ?? canonicalDisplay(initialValue),
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const validDraftRef = useRef(false);
  const tooltip = resolvedTooltip(stepName, spec, locale, t);
  const capability = spec.capabilityKey === undefined ? undefined : state.backendCapabilities[spec.capabilityKey];
  const capabilityLabel = capability !== undefined && Object.hasOwn(capabilityKeys, capability) ? capabilityKeys[capability] : undefined;
  const description = parameterDescription(spec, tooltip, t);
  const clientError = draft?.validation.status === 'invalid'
    ? validationMessage(draft.validation.message, spec, t)
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
    setDisplayValue(canonicalDisplay(initialValue));
    validDraftRef.current = false;
  }, [draft, initialValue, spec, t, displayUnit]);

  useEffect(() => {
    if (disabled) clearTimer();
  }, [disabled]);

  useEffect(() => () => clearTimer(), []);

  const update = (raw: unknown, display: DisplayValue) => {
    if (disabled) return;
    clearTimer();
    setDisplayValue(display);
    let validation = validateParameter(spec, raw);
    if (conversion && displayUnit !== undefined) {
      // Validate display syntax before converting; bounds belong to canonical units.
      const syntax = validateParameter({...spec, type: 'float', minimum: undefined, maximum: undefined, capabilityKey: undefined}, raw);
      if (syntax.ok && typeof syntax.value === 'number') {
        try {
          validation = validateParameter(spec, toCanonical(syntax.value, conversion.dimension, displayUnit));
        } catch { validation = {ok: false, messageKey: 'validation.finite'}; }
      } else { validation = syntax; }
    }
    validDraftRef.current = validation.ok;
    if (!validation.ok) {
      actions.updateDraft(
        stepIndex,
        spec.key,
        raw,
        {status: 'invalid', message: validation.messageKey},
        display,
        displayUnit,
      );
      return;
    }
    actions.updateDraft(
      stepIndex,
      spec.key,
      validation.value,
      {status: 'valid'},
      display,
      displayUnit,
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

  const changeUnit = (unit: DisplayUnit) => {
    clearTimer();
    const canonical = draft === undefined ? initialValue : draft.value;
    const display = draft?.validation.status === 'invalid' ? displayValue : canonicalDisplay(canonical, unit);
    setDisplayUnit(unit);
    setDisplayValue(display);
    if (draft !== undefined) actions.updateDraftDisplay(stepIndex, spec.key, display, unit);
    try { window.localStorage.setItem(preferenceKey, unit); } catch { /* Keep preference in memory. */ }
  };

  return (
    <div className={`parameter-field${hasError ? ' has-error' : ''}`}>
      <div className="parameter-label-row">
        <label htmlFor={inputId}>{spec.label || spec.key}</label>
        {capabilityLabel !== undefined && <span className={`parameter-capability capability-${capability}`}>{t(capabilityLabel)}</span>}
        {!conversion && spec.units && (
          <span id={unitsId} className="parameter-units">{spec.units}</span>
        )}
      </div>
      <div className={conversion ? 'parameter-value-row' : undefined}>
      <ParameterControl
        spec={spec}
        inputId={inputId}
        displayValue={displayValue}
        disabled={disabled}
        hasError={hasError}
        describedBy={uniqueDescriptions}
        tooltip={tooltip}
        onUpdate={update}
        onFlush={flush}
      />
      {conversion && <select
        aria-label={t('parameter.unit', {label: spec.label || spec.key})}
        className="parameter-unit-select"
        data-unit-control="true"
        value={displayUnit}
        disabled={disabled}
        onFocus={clearTimer}
        onChange={event => changeUnit(event.currentTarget.value as DisplayUnit)}
      >{conversion.units.map(unit => <option key={unit} value={unit}>{unit}</option>)}</select>}
      </div>
      {description && <p id={descriptionId} className="parameter-help">{description}</p>}
      {clientError && <p id={validationId} className="parameter-error">{clientError}</p>}
      {serverError !== undefined && (
        <div id={serverErrorId} className="parameter-server-error">
          <ErrorNotice
            title={t('parameter.saveErrorTitle')}
            error={serverError}
            parameterPath={serverError.parameterPath}
            suggestion={serverError.suggestion}
            rolledBack={serverError.rolledBack}
          />
        </div>
      )}
    </div>
  );
}

export function ParameterPanel({step, collapsed}: ParameterPanelProps) {
  const {state} = useAppState();
  const {t} = useI18n();
  const disabled = state.phase === 'running' || state.activeMutation !== null;
  const runError = step === null ? undefined : state.stepErrors[step.index];

  return (
    <section
      id="parameter-panel"
      className="workspace-pane parameter-pane"
      aria-label={t('parameter.region')}
      aria-busy={disabled}
      hidden={collapsed}
    >
      <header className="pane-header">
        <div>
          <span className="pane-kicker">{t('parameter.kicker')}</span>
          <h2>{t('parameter.title')}</h2>
        </div>
      </header>
      {step === null ? (
        <p className="pane-empty">{t('parameter.empty')}</p>
      ) : (
        <div className="parameter-summary">
          <div className="selected-step-heading">
            <div>
              <span className="selection-label">{t('parameter.currentStep')}</span>
              <h3>{step.instanceName}</h3>
              <p>{step.name}</p>
            </div>
            <StatusBadge status={step.runtimeStatus} />
          </div>
          {runError !== undefined && (
            <ErrorNotice
              title={t('parameter.runErrorTitle')}
              error={runError}
              parameterPath={runError.parameterPath}
              suggestion={runError.suggestion}
              rolledBack={runError.rolledBack}
            />
          )}
          {step.parameterSpecs.length === 0 ? (
            <p className="pane-empty">{t('parameter.noEditable')}</p>
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
                    stepName={step.name}
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
          {Object.hasOwn(step.params, 'mask_mode') && (
            <MaskControl
              stepIndex={step.index}
              maskName={typeof step.params.mask_name === 'string' ? step.params.mask_name : undefined}
              disabled={disabled}
            />
          )}
        </div>
      )}
    </section>
  );
}
