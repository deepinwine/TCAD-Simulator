import {useEffect, useRef, useState} from 'react';
import type {StepView} from '../api/types';
import {useI18n} from '../i18n/I18nContext';
import {zhCN, type TranslationKey} from '../i18n/catalogs';
import {validateParameter, type ParameterValidationResult} from './parameterValidation';
import {presentStep} from './stepPresentation';
import {conversionSpec} from '../units/parameterUnits';
import {fromCanonical, toCanonical, UnitConversionError, type DisplayUnit} from '../units/units';

function displayBound(value: number | undefined, conversion: ReturnType<typeof conversionSpec>, unit: DisplayUnit): number | undefined {
  if (value === undefined || !conversion) return value;
  try {return fromCanonical(value, conversion.dimension, unit);}
  catch (error) {if (error instanceof UnitConversionError) return undefined; throw error;}
}

export function AddStepDialog({template, busy, onCancel, onConfirm}: {template: StepView; busy: boolean; onCancel(): void; onConfirm(configuration: {params: Record<string, unknown>; instanceName?: string}): Promise<boolean | void>}) {
  const {locale, t} = useI18n();
  const english = locale === 'en';
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(template.parameterSpecs.map(spec => [spec.key, template.params[spec.key] ?? spec.defaultValue])));
  const [name, setName] = useState('');
  const [units, setUnits] = useState<Record<string, DisplayUnit>>(() => Object.fromEntries(template.parameterSpecs.flatMap(spec => {const conversion = conversionSpec(spec); return conversion ? [[spec.key, conversion.preferred]] : [];})));
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);
  const [conversionErrors, setConversionErrors] = useState<Record<string, boolean>>({});
  const dialog = useRef<HTMLDialogElement>(null);
  const gate = useRef(false);
  function updateValue(key: string, value: unknown) {
    setValues(current => ({...current, [key]: value}));
    setConversionErrors(current => ({...current, [key]: false}));
  }
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    if (typeof element?.showModal === 'function') element.showModal();
    else element?.setAttribute('open', '');
    element?.querySelector<HTMLElement>('select, input, button')?.focus();
    return () => previous?.focus();
  }, []);
  const validated = template.parameterSpecs.map(spec => {
    const conversion = conversionSpec(spec);
    const editable = ['float', 'int', 'integer', 'bool', 'boolean', 'choice', 'enum', 'string', 'str', 'text'].includes(spec.type);
    const raw = values[spec.key];
    let baseResult: ParameterValidationResult;
    try {
      const canonical = conversion && raw !== '' && Number.isFinite(Number(raw)) ? toCanonical(Number(raw), conversion.dimension, units[spec.key]) : raw;
      baseResult = editable ? validateParameter(spec, canonical) : {ok: true, value: raw};
    } catch (error) {
      if (!(error instanceof UnitConversionError)) throw error;
      baseResult = {ok: false, messageKey: 'validation.finite'};
    }
    const result: ParameterValidationResult = conversionErrors[spec.key] ? {ok: false, messageKey: 'validation.finite'} : baseResult;
    return {spec, conversion, editable, result, baseResult};
  });
  const valid = validated.every(item => item.result.ok) && name.trim().length <= 80;
  const disabled = busy || submitting;
  return <dialog ref={dialog} aria-modal="true" aria-labelledby="add-step-title" className="add-step-dialog" onCancel={event => {event.preventDefault(); if (!disabled) onCancel();}}>
    <form onSubmit={async event => {
      event.preventDefault();
      if (!valid || disabled || gate.current) return;
      gate.current = true; setSubmitting(true); setFailed(false);
      try {if (await onConfirm({params: Object.fromEntries(validated.map(({spec, result}) => [spec.key, result.ok ? result.value : undefined])), ...(name.trim() ? {instanceName: name.trim()} : {})}) === false) setFailed(true);}
      finally {gate.current = false; setSubmitting(false);}
    }}>
      <h2 id="add-step-title">{english ? 'Configure step' : '配置步骤'} · {presentStep(template, [], locale).type}</h2>
      <p>{presentStep(template, [], locale).description}</p>
      {failed && <p role="alert">{english ? 'Could not add the step. Check the parameters and retry.' : '添加失败，请检查参数后重试。'}</p>}
      {validated.map(({spec, result, baseResult, conversion, editable}) => {
        const id = `add-step-${spec.key}`;
        const label = Object.hasOwn(zhCN, `cad.${spec.key}`) ? t(`cad.${spec.key}` as TranslationKey) : spec.label;
        return <div className="parameter-field" key={spec.key}>
          <label htmlFor={id}>{label}{spec.units ? `（${units[spec.key] ?? spec.units}）` : ''}</label>
          {!editable ? <pre>{JSON.stringify(values[spec.key])}</pre> : spec.choices ? <select id={id} disabled={disabled} value={spec.choices.findIndex(([value]) => Object.is(value, values[spec.key]))} onChange={event => updateValue(spec.key, spec.choices![Number(event.target.value)][0])}>
            {spec.choices.map(([, text], index) => <option key={index} value={index}>{text}</option>)}
          </select> : spec.type === 'bool' || spec.type === 'boolean' ? <input id={id} type="checkbox" disabled={disabled} checked={Boolean(values[spec.key])} onChange={event => updateValue(spec.key, event.target.checked)} /> : <input id={id} type={['float', 'int', 'integer'].includes(spec.type) ? 'number' : 'text'} step="any" min={displayBound(spec.minimum, conversion, units[spec.key])} max={displayBound(spec.maximum, conversion, units[spec.key])} disabled={disabled} aria-invalid={!result.ok} value={String(values[spec.key] ?? '')} onChange={event => updateValue(spec.key, event.target.value)} />}
          {conversion && <select aria-label={`${label}${english ? ' unit' : '单位'}`} disabled={disabled} value={units[spec.key]} onChange={event => {
            const nextUnit = event.target.value as DisplayUnit;
            try {
              if (baseResult.ok && typeof baseResult.value === 'number') {
                const converted = fromCanonical(baseResult.value, conversion.dimension, nextUnit);
                updateValue(spec.key, String(converted));
              } else setConversionErrors(current => ({...current, [spec.key]: false}));
              setUnits(current => ({...current, [spec.key]: nextUnit}));
            } catch (error) {
              if (!(error instanceof UnitConversionError)) throw error;
              setConversionErrors(current => ({...current, [spec.key]: true}));
            }
          }}>{conversion.units.map(unit => <option key={unit} value={unit}>{unit}</option>)}</select>}
          {spec.tooltip && <small>{spec.tooltip}</small>}
          {!result.ok && <small role="alert">{english ? 'Enter a valid value within the allowed range.' : '请输入符合范围的有效值。'}</small>}
        </div>;
      })}
      <label htmlFor="add-step-name">{english ? 'Custom name (optional)' : '自定义名称（可选）'}</label>
      <input id="add-step-name" maxLength={80} value={name} disabled={disabled} onChange={event => setName(event.target.value)} />
      <div className="dialog-actions"><button type="button" disabled={disabled} onClick={onCancel}>{english ? 'Cancel' : '取消'}</button><button type="submit" disabled={disabled || !valid}>{english ? 'Add step' : '确认添加'}</button></div>
    </form>
  </dialog>;
}
