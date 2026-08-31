import {useMemo, useState} from 'react';
import {createTcadApi} from './api/client';
import type {TcadApi} from './api/types';
import {ErrorNotice} from './components/ErrorNotice';
import {ParameterPanel} from './components/ParameterPanel';
import {ProcessFlowPane} from './components/ProcessFlowPane';
import {TimelineBar} from './components/TimelineBar';
import {Toolbar} from './components/Toolbar';
import {AppStateProvider, useAppState} from './state/AppStateContext';
import {ThreeViewer} from './viewer/ThreeViewer';

interface AppProps {
  api?: TcadApi;
}

function StudioShell() {
  const {state, actions} = useAppState();
  const [parametersCollapsed, setParametersCollapsed] = useState(false);
  const selectedStep = useMemo(
    () => state.recipe.find(step => step.index === state.selectedStepIndex) ?? null,
    [state.recipe, state.selectedStepIndex],
  );

  if (state.phase === 'booting') {
    return (
      <main className="launch-screen">
        <h1>TCAD Studio</h1>
        <p role="status" aria-live="polite" aria-busy="true">
          正在连接现有 Process CAD Session…
        </p>
      </main>
    );
  }

  if (state.phase === 'fatal') {
    return (
      <main className="launch-screen">
        <h1>TCAD Studio</h1>
        <ErrorNotice
          title="无法加载 TCAD Session"
          message="请确认 TCAD 服务已启动，然后重试连接。"
          actionLabel="重试连接"
          onAction={() => void actions.bootstrap()}
        />
      </main>
    );
  }

  const workspaceClass = parametersCollapsed
    ? 'studio-workspace parameters-collapsed'
    : 'studio-workspace';

  return (
    <main className="studio-shell">
      <Toolbar
        phase={state.phase}
        parametersCollapsed={parametersCollapsed}
        onToggleParameters={() => setParametersCollapsed(value => !value)}
      />
      <div className={workspaceClass}>
        <ProcessFlowPane
          recipe={state.recipe}
          selectedStepIndex={state.selectedStepIndex}
          onSelect={actions.selectStep}
        />
        <ParameterPanel step={selectedStep} collapsed={parametersCollapsed} />
        <ThreeViewer refreshToken={state.previewGeneration} />
      </div>
      <TimelineBar timeline={state.timeline} />
    </main>
  );
}

export function App({api}: AppProps) {
  const resolvedApi = useMemo(() => api ?? createTcadApi(), [api]);
  return (
    <AppStateProvider api={resolvedApi}>
      <StudioShell />
    </AppStateProvider>
  );
}
