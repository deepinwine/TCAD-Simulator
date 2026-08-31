import {hasUnsavedDrafts} from '../state/appReducer';
import {useAppState} from '../state/AppStateContext';

interface ToolbarProps {
  parametersCollapsed: boolean;
  onToggleParameters(): void;
}

const draftGuidanceId = 'mutation-draft-guidance';

export function Toolbar({parametersCollapsed, onToggleParameters}: ToolbarProps) {
  const {state, actions} = useAppState();
  const connected = state.phase === 'ready' || state.phase === 'running';
  const mutationActive = state.phase === 'running' || state.activeMutation !== null;
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
        {draftBlocked && (
          <span id={draftGuidanceId} className="toolbar-gate-copy" role="status">
            请先保存或修正参数
          </span>
        )}
      </div>
      <div className="toolbar-actions">
        <span
          className={`connection-state ${connected ? 'is-connected' : 'is-busy'}`}
          aria-label={`连接状态：${connected ? '已连接 Connected' : '处理中 Working'}`}
        >
          <span className="connection-dot" aria-hidden="true" />
          {connected ? '已连接 Connected' : '处理中 Working'}
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
