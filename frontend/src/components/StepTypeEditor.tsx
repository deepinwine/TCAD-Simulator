import {useState} from 'react';
import type {StepView} from '../api/types';
import {useAppState} from '../state/AppStateContext';
import {useI18n} from '../i18n/I18nContext';
import {AddStepDialog} from './AddStepDialog';
import {candidateStep, processCatalog} from './processCatalog';
export function StepTypeEditor({step, onCandidateChange}: {step: StepView; onCandidateChange(index: number, pending: boolean): void}) {
  const {state, actions} = useAppState();
  const {t} = useI18n();
  const [candidates, setCandidates] = useState<Record<number, StepView>>({});
  const [choices, setChoices] = useState<Record<number, string>>({});
  const [modes, setModes] = useState<Record<number, string>>({});
  const current = step.name === 'Structure Fill' ? 'Deposit' : step.name.replace(/^Structure /, '');
  const choice = choices[step.index] ?? (processCatalog.some(item => item.id === current) ? current : '');
  const mode = modes[step.index] ?? (step.name === 'Structure Fill' ? 'Fill' : 'Deposit');
  const busy = state.phase === 'running' || state.activeMutation !== null;
  const factory = `Structure ${choice === 'Deposit' ? mode : choice}`;
  const available = state.factoryTemplates?.some(item => item.name === factory);
  function cancel(index: number) {
    setCandidates(old => {const next = {...old}; delete next[index]; return next;});
    setChoices(old => {const next = {...old}; delete next[index]; return next;});
    setModes(old => {const next = {...old}; delete next[index]; return next;});
    onCandidateChange(index, false);
  }
  function configure(type: string, nextMode: string) {
    setChoices(old => ({...old, [step.index]: type})); setModes(old => ({...old, [step.index]: nextMode}));
    const template = state.factoryTemplates?.find(item => item.name === `Structure ${type === 'Deposit' ? nextMode : type}`);
    if (template) {setCandidates(old => ({...old, [step.index]: candidateStep(step, template)})); onCandidateChange(step.index, true);}
    else {setCandidates(old => {const next = {...old}; delete next[step.index]; return next;}); onCandidateChange(step.index, false);}
  }
  return <div className="step-type-editor">
    {!processCatalog.some(item => item.id === current) && <p>{t('typeEdit.legacy', {name: step.name})}</p>}
    <label htmlFor="step-process-type">{t('typeEdit.type')}</label>
    <select id="step-process-type" disabled={busy} value={choice} onChange={event => configure(event.target.value, 'Deposit')}>
      <option value="" disabled>{t('structure.selectType')}</option>{processCatalog.map(item => <option key={item.id} value={item.id}>{t(item.key)}</option>)}
    </select>
    {choice === 'Deposit' && <><label htmlFor="step-deposition-mode">{t('typeEdit.mode')}</label><select id="step-deposition-mode" disabled={busy} value={mode} onChange={event => configure(choice, event.target.value)}><option value="Deposit">{t('typeEdit.film')}</option><option value="Fill">{t('typeEdit.fill')}</option></select></>}
    <button type="button" disabled={busy || !available} onClick={() => configure(choice, mode)}>{t('typeEdit.configure')}</button>
    {!available && <p>{t('structure.legacyServer')}</p>}
    {Object.entries(candidates).map(([indexText, candidate]) => {
      const index = Number(indexText);
      return <div key={`${index}:${candidate.name}`} hidden={index !== step.index}>
        <p role="status">{t('typeEdit.notice')}</p>
        <AddStepDialog inline template={candidate} busy={busy} onCancel={() => cancel(index)} onConfirm={async configuration => {const applied = await actions.replaceStep(index, candidate.name, configuration); if (applied) cancel(index); return applied;}} />
      </div>;
    })}
  </div>;
}
