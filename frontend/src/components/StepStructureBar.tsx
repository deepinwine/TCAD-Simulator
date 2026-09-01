import {useState} from 'react';
import {useAppState} from '../state/AppStateContext';

/**
 * 步骤结构编辑条：添加（工厂选择）、上移/下移/复制/删除、重命名（1–80 字符）。
 * 全部作用于当前选中步骤；操作经变更 gate 与运行互斥。
 */
export function StepStructureBar() {
  const {state, actions} = useAppState();
  const [addChoice, setAddChoice] = useState('');
  const [renameValue, setRenameValue] = useState('');
  const busy = state.phase === 'running' || state.activeMutation !== null;
  const selected = state.recipe.find(step => step.index === state.selectedStepIndex) ?? null;
  const selectedIndex = selected?.index ?? null;
  const position = selected === null
    ? -1
    : state.recipe.findIndex(step => step.index === selectedIndex);
  const canMoveUp = position > 0;
  const canMoveDown = position >= 0 && position < state.recipe.length - 1;
  const renameTrimmed = renameValue.trim();
  const renameValid = renameTrimmed.length >= 1 && renameTrimmed.length <= 80;

  return (
    <div className="step-structure-bar" role="group" aria-label="步骤结构编辑">
      <select
        aria-label="添加步骤类型"
        value={addChoice}
        disabled={busy || state.factories.length === 0}
        onChange={event => setAddChoice(event.target.value)}
      >
        <option value="">-- 步骤类型 --</option>
        {state.factories.map(factory => (
          <option key={factory} value={factory}>{factory}</option>
        ))}
      </select>
      <button
        type="button"
        disabled={busy || addChoice === ''}
        onClick={() => {
          void actions.addStep(addChoice);
          setAddChoice('');
        }}
      >
        添加步骤
      </button>
      <button
        type="button"
        disabled={busy || !canMoveUp}
        onClick={() => void actions.moveStep('up')}
      >
        上移
      </button>
      <button
        type="button"
        disabled={busy || !canMoveDown}
        onClick={() => void actions.moveStep('down')}
      >
        下移
      </button>
      <button
        type="button"
        disabled={busy || selectedIndex === null}
        onClick={() => void actions.duplicateStep()}
      >
        复制
      </button>
      <button
        type="button"
        disabled={busy || selectedIndex === null || state.recipe.length <= 1}
        onClick={() => void actions.removeStep()}
      >
        删除
      </button>
      <input
        type="text"
        aria-label="步骤重命名"
        placeholder={selected?.instanceName ?? '新步骤名'}
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
        应用重命名
      </button>
    </div>
  );
}
