import {useMemo, useState} from 'react';
import {createTcadApi} from './api/client';
import type {TcadApi} from './api/types';
import {ErrorNotice} from './components/ErrorNotice';
import {ParameterPanel} from './components/ParameterPanel';
import {ProcessFlowPane} from './components/ProcessFlowPane';
import {StepStructureBar} from './components/StepStructureBar';
import {TimelineBar} from './components/TimelineBar';
import {Toolbar} from './components/Toolbar';
import {AppStateProvider, useAppState} from './state/AppStateContext';
import {ThreeViewer} from './viewer/ThreeViewer';
import type {ViewerRuntime} from './viewer/viewerRuntime';

interface AppProps {
  api?: TcadApi;
  viewerRuntimeFactory?: (api: TcadApi) => ViewerRuntime;
}

function StudioShell({api, viewerRuntimeFactory}: {api: TcadApi; viewerRuntimeFactory?: (api: TcadApi) => ViewerRuntime}) {
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
        parametersCollapsed={parametersCollapsed}
        onToggleParameters={() => setParametersCollapsed(value => !value)}
      />
      {state.globalError !== null && state.globalError !== state.timelineError && (
        <div className="global-error-strip">
          <ErrorNotice
            title="操作失败"
            message={state.globalError.message}
            parameterPath={state.globalError.parameterPath}
            suggestion={state.globalError.code === 'network_error'
              ? '服务端可能仍在执行（长工艺无响应期间连接可能被断开）。点击重新同步以服务端状态为准。'
              : state.globalError.suggestion}
            rolledBack={state.globalError.rolledBack}
            actionLabel={state.globalError.code === 'network_error' ? '重新同步' : undefined}
            onAction={state.globalError.code === 'network_error'
              ? () => void actions.reconcile()
              : undefined}
          />
        </div>
      )}
      <div className={workspaceClass}>
        <ProcessFlowPane
          recipe={state.recipe}
          selectedStepIndex={state.selectedStepIndex}
          onSelect={actions.selectStep}
        >
          <StepStructureBar />
        </ProcessFlowPane>
        <ParameterPanel step={selectedStep} collapsed={parametersCollapsed} />
        <ThreeViewer api={api} refreshToken={state.previewGeneration} runtimeFactory={viewerRuntimeFactory} />
      </div>
      <TimelineBar />
    </main>
  );
}

export function App({api, viewerRuntimeFactory}: AppProps) {
  const resolvedApi = useMemo(() => api ?? createTcadApi(), [api]);
  return (
    <AppStateProvider api={resolvedApi}>
      <StudioShell api={resolvedApi} viewerRuntimeFactory={viewerRuntimeFactory} />
    </AppStateProvider>
  );
}
