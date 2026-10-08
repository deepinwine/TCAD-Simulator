import {useEffect, useRef, useState} from 'react';
import type {StepView, TcadApi} from '../api/types';
import {useAppState} from '../state/AppStateContext';
import {useI18n} from '../i18n/I18nContext';
import {AddStepDialog} from './AddStepDialog';
import {updateProjectRecipe, validDomain} from './projectSettingsModel';
export function ProjectSettings({api, onClose}: {api: TcadApi; onClose(): void}) {
  const {state, actions} = useAppState(); const {t} = useI18n();
  const [exported, setExported] = useState<Record<string, unknown> | null>(null);
  const [template, setTemplate] = useState<StepView | null>(null);
  const [grid, setGrid] = useState(['', '', '']); const [voxel, setVoxel] = useState('');
  const [error, setError] = useState(false); const [failed, setFailed] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const sourceRecipe = useRef(state.recipe);
  useEffect(() => {
    const element = dialog.current; const previous = document.activeElement as HTMLElement | null;
    if (typeof element?.showModal === 'function') element.showModal(); else element?.setAttribute('open', '');
    return () => previous?.focus();
  }, []);
  useEffect(() => {
    if (state.phase === 'booting') return;
    const controller = new AbortController(); sourceRecipe.current = state.recipe;
    void api.exportRecipe('current', controller.signal).then(blob => blob.text()).then(text => {
      if (controller.signal.aborted) return;
      const blob = JSON.parse(text) as Record<string, unknown>;
      const steps = blob.steps_full as Record<string, unknown>[] | undefined;
      const initial = state.recipe[0]; const raw = steps?.[0];
      if (!initial || !raw || !['Structure Wafer', 'Initialize Wafer'].includes(String(raw.name))) throw new Error('missing initializer');
      const domain = blob.domain as Record<string, unknown>;
      const shape = domain.grid_shape as number[];
      setGrid(shape.map(String)); setVoxel(String(domain.voxel_size_nm));
      setTemplate({...initial, params: {...((raw.params_raw ?? raw.params) as Record<string, unknown>)}});
      setExported(blob);
    }).catch(() => {if (!controller.signal.aborted) setError(true);});
    return () => controller.abort();
  }, [api, state.phase === 'booting']);
  const numbers = grid.map(Number); const size = Number(voxel);
  const valid = grid.every(value => value.trim() !== '') && voxel.trim() !== '' && validDomain(numbers, size);
  const busy = state.phase === 'running' || state.activeMutation !== null;
  const stale = state.recipe !== sourceRecipe.current;
  return <dialog ref={dialog} aria-modal="true" aria-labelledby="project-settings-title" className="add-step-dialog" onCancel={event => {event.preventDefault(); if (!busy) onClose();}}>
    <h2 id="project-settings-title">{t('project.title')}</h2>
    <p>{t('project.warning')}</p><p>{t('project.budget')}</p>
    {error ? <><p role="alert">{t('project.unavailable')}</p><button onClick={onClose}>{t('addStep.cancel')}</button></> : template && exported ? <>
      {['X', 'Y', 'Z'].map((axis, index) => <div key={axis}><label htmlFor={`project-grid-${axis}`}>{t('project.grid', {axis})}</label><input id={`project-grid-${axis}`} type="number" min="1" step="1" value={grid[index]} disabled={busy} onChange={event => setGrid(old => old.map((value, position) => position === index ? event.target.value : value))} /></div>)}
      <label htmlFor="project-voxel">{t('project.voxel')}</label><input id="project-voxel" type="number" min="0" step="any" value={voxel} disabled={busy} onChange={event => setVoxel(event.target.value)} />
      <p>{t('project.span', {x: Number.isFinite(numbers[0] * size) ? numbers[0] * size : '—', y: Number.isFinite(numbers[1] * size) ? numbers[1] * size : '—'})}</p>
      {(!valid || failed || stale) && <p role="alert">{t(stale ? 'project.stale' : failed ? 'project.failed' : 'addStep.invalid')}</p>}
      {template.name === 'Initialize Wafer' && <p>{t('project.legacy')}</p>}
      <AddStepDialog inline project template={template} busy={busy} canConfirm={valid && !stale} onCancel={onClose} onConfirm={async configuration => {
        const recipe = updateProjectRecipe(exported, numbers, size, configuration.params);
        const applied = await actions.importRecipe({recipe});
        if (applied) onClose(); else setFailed(true);
        return applied;
      }} />
    </> : <p role="status">{t('app.connecting')}</p>}
  </dialog>;
}
