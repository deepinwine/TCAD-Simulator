import {useState} from 'react';
import {useAppState} from '../state/AppStateContext';
import {useI18n} from '../i18n/I18nContext';
import {AddStepDialog} from './AddStepDialog';
import type {StepView} from '../api/types';
import {processCatalog, isInitializer} from './processCatalog';

/**
 * 步骤结构编辑条：添加（工厂选择）、上移/下移/复制/删除、重命名（1–80 字符）。
 * 全部作用于当前选中步骤；操作经变更 gate 与运行互斥。
 */
export function StepStructureBar() {
  const {state, actions} = useAppState();
  const {t} = useI18n();
  const [template, setTemplate] = useState<StepView | null>(null);
  const [addChoice, setAddChoice] = useState('');
  const [mode, setMode] = useState('Deposit');
  const [renameValue, setRenameValue] = useState('');
  const busy = state.phase === 'running' || state.activeMutation !== null || state.pendingSaves > 0 || state.pendingTypeEdits.length > 0;
  const selected = state.recipe.find(step => step.index === state.selectedStepIndex) ?? null;
  const selectedIndex = selected?.index ?? null;
  const position = selected === null
    ? -1
    : state.recipe.findIndex(step => step.index === selectedIndex);
  const canMoveUp = position > 0 && !isInitializer(state.recipe[position - 1]);
  const canMoveDown = position >= 0 && position < state.recipe.length - 1;
  const renameTrimmed = renameValue.trim();
  const renameValid = renameTrimmed.length >= 1 && renameTrimmed.length <= 80;
  const factories = processCatalog.map(item => `Structure ${item.id}`);
  const factory = addChoice === 'Structure Deposit' ? `Structure ${mode}` : addChoice;
  const available = state.factoryTemplates?.some(item => item.name === factory);

  return (
    <div className="step-structure-bar" role="group" aria-label={t('structure.group')}>
      <select
        aria-label={t('structure.addType')}
        value={factories.includes(addChoice) ? addChoice : ''}
        disabled={busy}
        onChange={event => {setAddChoice(event.target.value); setMode('Deposit');}}
      >
        <option value="">{t('structure.selectType')}</option>
        {processCatalog.map(item => (
          <option key={item.id} value={`Structure ${item.id}`}>{t(item.key)}</option>
        ))}
      </select>
      {addChoice === 'Structure Deposit' && <select aria-label={t('typeEdit.mode')} value={mode} disabled={busy} onChange={event => setMode(event.target.value)}><option value="Deposit">{t('typeEdit.film')}</option><option value="Fill">{t('typeEdit.fill')}</option></select>}
      <button
        type="button"
        disabled={busy || !available}
        onClick={() => {
          const configurationTemplate = state.factoryTemplates?.find(item => item.name === factory);
          if (configurationTemplate) setTemplate(configurationTemplate);
        }}
      >
        {t('structure.add')}
      </button>
      {!available && <small>{t('structure.legacyServer')}</small>}
      {template !== null && <AddStepDialog template={template} busy={busy} onCancel={() => setTemplate(null)} onConfirm={async configuration => {const applied = await actions.addStep(template.name, configuration); if (applied) {setTemplate(null); setAddChoice('');} return applied;}} />}
      <button
        type="button"
        disabled={busy || !canMoveUp}
        onClick={() => void actions.moveStep('up')}
      >
        {t('structure.moveUp')}
      </button>
      <button
        type="button"
        disabled={busy || !canMoveDown}
        onClick={() => void actions.moveStep('down')}
      >
        {t('structure.moveDown')}
      </button>
      <button
        type="button"
        disabled={busy || selectedIndex === null}
        onClick={() => void actions.duplicateStep()}
      >
        {t('structure.duplicate')}
      </button>
      <button
        type="button"
        disabled={busy || selectedIndex === null || state.recipe.length <= 1}
        onClick={() => void actions.removeStep()}
      >
        {t('structure.remove')}
      </button>
      <input
        type="text"
        aria-label={t('structure.rename')}
        placeholder={selected?.instanceName ?? t('structure.newName')}
        value={renameValue}
        disabled={busy || selectedIndex === null}
        onChange={event => setRenameValue(event.target.value)}
      />
      <button
        type="button"
        disabled={busy || selectedIndex === null || !renameValid}
        onClick={() => {
          void actions.renameStep(renameTrimmed);
          setRenameValue('');
        }}
      >
        {t('structure.applyRename')}
      </button>
    </div>
  );
}
