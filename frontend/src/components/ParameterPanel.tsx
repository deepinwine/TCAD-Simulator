import type {StepView} from '../api/types';
import {summarizeParams} from './ProcessFlowPane';
import {StatusBadge} from './StatusBadge';

interface ParameterPanelProps {
  step: StepView | null;
  collapsed: boolean;
}

export function ParameterPanel({step, collapsed}: ParameterPanelProps) {
  return (
    <section
      id="parameter-panel"
      className="workspace-pane parameter-pane"
      aria-label="Parameters"
      hidden={collapsed}
    >
      <header className="pane-header">
        <div>
          <span className="pane-kicker">Inspector</span>
          <h2>Parameters</h2>
        </div>
      </header>
      {step === null ? (
        <p className="pane-empty">选择一个工艺步骤以查看参数</p>
      ) : (
        <div className="parameter-summary">
          <div className="selected-step-heading">
            <div>
              <span className="selection-label">当前步骤</span>
              <h3>{step.instanceName}</h3>
              <p>{step.name}</p>
            </div>
            <StatusBadge status={step.runtimeStatus} />
          </div>
          <dl className="summary-grid">
            <div>
              <dt>参数规格</dt>
              <dd>{step.parameterSpecs.length}</dd>
            </div>
            <div>
              <dt>已配置参数</dt>
              <dd>{Object.keys(step.params).length}</dd>
            </div>
          </dl>
          <div className="summary-block">
            <span>参数摘要</span>
            <p>{summarizeParams(step.params)}</p>
          </div>
          <p className="placeholder-note">参数编辑将在下一阶段启用。</p>
        </div>
      )}
    </section>
  );
}
