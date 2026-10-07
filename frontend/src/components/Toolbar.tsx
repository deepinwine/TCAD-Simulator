import {useRef, useState} from 'react';
import {type ActiveMutation, hasUnsavedDrafts} from '../state/appReducer';
import {useAppState} from '../state/AppStateContext';
import {useI18n} from '../i18n/I18nContext';
import {LanguageSwitcher} from './LanguageSwitcher';
import type {TranslationKey} from '../i18n/catalogs';

interface ToolbarProps {
  parametersCollapsed: boolean;
  onToggleParameters(): void;
}

const draftGuidanceId = 'mutation-draft-guidance';

const operationKeys: Record<Exclude<ActiveMutation, null>, TranslationKey> = {
  step: 'operation.step',
  to: 'operation.to',
  all: 'operation.all',
  timeline: 'operation.timeline',
  undo: 'operation.undo',
  redo: 'operation.redo',
  recipe: 'operation.recipe',
  mask: 'operation.mask',
};

export function Toolbar({parametersCollapsed, onToggleParameters}: ToolbarProps) {
  const {state, actions} = useAppState();
  const {t} = useI18n();
  const [demoChoice, setDemoChoice] = useState('');
  const [recipeName, setRecipeName] = useState('');
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const demoRecipes = state.demoRecipes;
  const structureMode = state.recipe.length > 0 && state.recipe.every(step => step.name.startsWith('Structure '));
  const mutationActive = state.phase === 'running' || state.activeMutation !== null;
  const activeOperation = state.activeMutation;
  const online = state.phase === 'ready' || state.phase === 'running';
  const connectionLabel = mutationActive
    ? t('toolbar.connectionRunning')
    : online
      ? t('toolbar.connectionConnected')
      : t('toolbar.connectionWorking');
  const connectionTone = mutationActive || !online ? 'is-busy' : 'is-connected';
  const runAnnouncement = mutationActive && activeOperation !== null
    ? t('toolbar.runningAnnouncement', {operation: t(operationKeys[activeOperation])})
    : '';
  const draftBlocked = hasUnsavedDrafts(state);
  const selectedMissing = state.selectedStepIndex === null;
  const allRunsDisabled = mutationActive || draftBlocked;
  const describedBy = draftBlocked ? draftGuidanceId : undefined;
  return (
    <header className="studio-toolbar">
      <div className="product-lockup">
        <span className="product-mark" aria-hidden="true">TS</span>
        <div>
          <h1>TCAD Studio</h1>
          <span className="product-context">{structureMode ? t('cad.mode', {grid: state.model?.voxelSizeNm ?? '—'}) : 'Process CAD'}</span>
        </div>
      </div>
      <div className="toolbar-run-group" aria-label={t('toolbar.processActions')}>
        <button type="button" className="toolbar-button is-primary" disabled={allRunsDisabled || demoRecipes?.['Structure CAD — Trench'] === undefined} aria-describedby={describedBy} onClick={() => {
          const recipe = demoRecipes?.['Structure CAD — Trench'];
          if (recipe !== undefined) void actions.importRecipe({recipe, name: 'Structure CAD — Trench'});
        }}>{t('cad.example')}</button>
        <button
          type="button"
          className="toolbar-button run-button"
          disabled={allRunsDisabled || selectedMissing}
          aria-describedby={describedBy}
          onClick={() => void actions.runStep()}
        >
          {t(structureMode ? 'cad.step' : 'toolbar.runStep')}
        </button>
        <button
          type="button"
          className="toolbar-button run-button"
          disabled={allRunsDisabled || selectedMissing}
          aria-describedby={describedBy}
          onClick={() => void actions.runTo()}
        >
          {t(structureMode ? 'cad.to' : 'toolbar.runTo')}
        </button>
        <button
          type="button"
          className="toolbar-button run-button is-primary"
          disabled={allRunsDisabled}
          aria-describedby={describedBy}
          onClick={() => void actions.runAll()}
        >
          {t(structureMode ? 'cad.all' : 'toolbar.runAll')}
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => void actions.undo()}
        >
          {t('toolbar.undo')}
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => void actions.redo()}
        >
          {t('toolbar.redo')}
        </button>
        <select
          className="toolbar-button"
          aria-label={t('toolbar.demoRecipe')}
          value={demoChoice}
          disabled={allRunsDisabled || demoRecipes === undefined}
          onChange={event => setDemoChoice(event.target.value)}
        >
          <option value="">{t('toolbar.selectDemo')}</option>
          {demoRecipes !== undefined && Object.entries(demoRecipes).map(([key, demo]) => (
            <option key={key} value={key}>
              {demo.description ? `${key} — ${demo.description}` : key}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled || demoChoice === ''}
          onClick={() => {
            const blob = demoRecipes?.[demoChoice];
            if (blob !== undefined) {
              void actions.importRecipe({recipe: blob, name: demoChoice});
              setDemoChoice('');
            }
          }}
        >
          {t('toolbar.loadDemo')}
        </button>
        <input
          type="text"
          className="toolbar-button"
          aria-label={t('toolbar.recipeName')}
          placeholder={t('toolbar.recipeName')}
          value={recipeName}
          disabled={allRunsDisabled}
          onChange={event => setRecipeName(event.target.value)}
        />
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled || recipeName.trim() === ''}
          onClick={() => {
            void actions.newRecipe(recipeName.trim());
            setRecipeName('');
          }}
        >
          {t('toolbar.newRecipe')}
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled || recipeName.trim() === ''}
          onClick={() => {
            void actions.saveRecipe(recipeName.trim());
          }}
          title={t('toolbar.saveRecipeTitle')}
        >
          {t('toolbar.saveRecipe')}
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => void actions.exportRecipe()}
        >
          {t('toolbar.exportRecipe')}
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => importInputRef.current?.click()}
        >
          {t('toolbar.importRecipe')}
        </button>
        <input
          ref={importInputRef}
          type="file"
          accept="application/json,.json"
          aria-label={t('toolbar.importRecipeFile')}
          className="visually-hidden"
          onChange={event => {
            const file = event.target.files?.[0];
            if (file !== undefined) {
              void file.text().then(content => {
                actions.importRecipe({recipe: JSON.parse(content)});
              });
            }
            event.target.value = '';
          }}
        />
        {draftBlocked && (
          <span id={draftGuidanceId} className="toolbar-gate-copy" role="status">
            {t('toolbar.draftGuidance')}
          </span>
        )}
      </div>
      <div className="toolbar-actions">
        <LanguageSwitcher />
        <span
          className="toolbar-run-status"
          role="status"
          aria-live="polite"
          aria-label={runAnnouncement || undefined}
        >
          {runAnnouncement}
        </span>
        <span
          className={`connection-state ${connectionTone}`}
          aria-label={t('toolbar.connectionStatus', {status: connectionLabel})}
        >
          <span className="connection-dot" aria-hidden="true" />
          {connectionLabel}
        </span>
        <button
          type="button"
          className="toolbar-button"
          aria-controls="parameter-panel"
          aria-expanded={!parametersCollapsed}
          aria-label={parametersCollapsed
            ? t('toolbar.expandParameters')
            : t('toolbar.collapseParameters')}
          onClick={onToggleParameters}
        >
          {parametersCollapsed ? t('toolbar.showParameters') : t('toolbar.hideParameters')}
        </button>
      </div>
    </header>
  );
}
