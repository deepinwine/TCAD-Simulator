import type {AppPhase} from '../state/appReducer';

interface ToolbarProps {
  phase: AppPhase;
  parametersCollapsed: boolean;
  onToggleParameters(): void;
}

export function Toolbar({phase, parametersCollapsed, onToggleParameters}: ToolbarProps) {
  const connected = phase === 'ready' || phase === 'running';
  return (
    <header className="studio-toolbar">
      <div className="product-lockup">
        <span className="product-mark" aria-hidden="true">TS</span>
        <div>
          <h1>TCAD Studio</h1>
          <span className="product-context">Process CAD</span>
        </div>
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
