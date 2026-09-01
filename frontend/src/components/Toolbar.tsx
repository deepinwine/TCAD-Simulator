import {useRef, useState} from 'react';
import {type ActiveMutation, hasUnsavedDrafts} from '../state/appReducer';
import {useAppState} from '../state/AppStateContext';

interface ToolbarProps {
  parametersCollapsed: boolean;
  onToggleParameters(): void;
}

const draftGuidanceId = 'mutation-draft-guidance';

const operationLabels: Record<Exclude<ActiveMutation, null>, string> = {
  step: '运行选中步骤',
  to: '运行至选中步骤',
  all: '运行全部',
  timeline: '回看历史快照',
  undo: '撤销',
  redo: '重做',
  recipe: '切换配方',
};

export function Toolbar({parametersCollapsed, onToggleParameters}: ToolbarProps) {
  const {state, actions} = useAppState();
  const [demoChoice, setDemoChoice] = useState('');
  const [recipeName, setRecipeName] = useState('');
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const demoRecipes = state.demoRecipes;
  const mutationActive = state.phase === 'running' || state.activeMutation !== null;
  const activeOperation = state.activeMutation;
  const online = state.phase === 'ready' || state.phase === 'running';
  const connectionLabel = mutationActive
    ? '运行中 Running'
    : online
      ? '已连接 Connected'
      : '处理中 Working';
  const connectionTone = mutationActive || !online ? 'is-busy' : 'is-connected';
  const runAnnouncement = mutationActive && activeOperation !== null
    ? `正在运行：${operationLabels[activeOperation]}…`
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
          <span className="product-context">Process CAD</span>
        </div>
      </div>
      <div className="toolbar-run-group" aria-label="工艺执行">
        <button
          type="button"
          className="toolbar-button run-button"
          disabled={allRunsDisabled || selectedMissing}
          aria-describedby={describedBy}
          onClick={() => void actions.runStep()}
        >
          运行选中步骤
        </button>
        <button
          type="button"
          className="toolbar-button run-button"
          disabled={allRunsDisabled || selectedMissing}
          aria-describedby={describedBy}
          onClick={() => void actions.runTo()}
        >
          运行至选中步骤
        </button>
        <button
          type="button"
          className="toolbar-button run-button is-primary"
          disabled={allRunsDisabled}
          aria-describedby={describedBy}
          onClick={() => void actions.runAll()}
        >
          运行全部
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => void actions.undo()}
        >
          撤销
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => void actions.redo()}
        >
          重做
        </button>
        <select
          className="toolbar-button"
          aria-label="Demo 配方"
          value={demoChoice}
          disabled={allRunsDisabled || demoRecipes === undefined}
          onChange={event => setDemoChoice(event.target.value)}
        >
          <option value="">-- 选择 Demo 配方 --</option>
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
          加载 Demo
        </button>
        <input
          type="text"
          className="toolbar-button"
          aria-label="配方名称"
          placeholder="配方名称"
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
          新建配方
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled || recipeName.trim() === ''}
          onClick={() => {
            void actions.saveRecipe(recipeName.trim());
          }}
          title="以输入名称保存当前配方"
        >
          保存配方
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => void actions.exportRecipe()}
        >
          导出配方
        </button>
        <button
          type="button"
          className="toolbar-button"
          disabled={allRunsDisabled}
          onClick={() => importInputRef.current?.click()}
        >
          导入配方
        </button>
        <input
          ref={importInputRef}
          type="file"
          accept="application/json,.json"
          aria-label="导入配方文件"
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
            请先保存或修正参数
          </span>
        )}
      </div>
      <div className="toolbar-actions">
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
          aria-label={`连接状态：${connectionLabel}`}
        >
          <span className="connection-dot" aria-hidden="true" />
          {connectionLabel}
        </span>
        <button
          type="button"
          className="toolbar-button"
          aria-controls="parameter-panel"
          aria-expanded={!parametersCollapsed}
          aria-label={parametersCollapsed ? '展开 Parameters' : '折叠 Parameters'}
          onClick={onToggleParameters}
        >
          {parametersCollapsed ? '显示参数' : '隐藏参数'}
        </button>
      </div>
    </header>
  );
}
