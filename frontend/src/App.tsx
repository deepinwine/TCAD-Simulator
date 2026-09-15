import {useMemo, useState} from 'react';
import {createTcadApi} from './api/client';
import type {TcadApi} from './api/types';
import {ErrorNotice} from './components/ErrorNotice';
import {ParameterPanel} from './components/ParameterPanel';
import {ProcessFlowPane} from './components/ProcessFlowPane';
import {RecipeAssistant} from './components/RecipeAssistant';
import {StepStructureBar} from './components/StepStructureBar';
import {TimelineBar} from './components/TimelineBar';
import {Toolbar} from './components/Toolbar';
import {I18nProvider, useI18n} from './i18n/I18nContext';
import {AppStateProvider, useAppState} from './state/AppStateContext';
import {ThreeViewer} from './viewer/ThreeViewer';
import type {ViewerRuntime} from './viewer/viewerRuntime';

interface AppProps {
  api?: TcadApi;
  viewerRuntimeFactory?: (api: TcadApi) => ViewerRuntime;
}

function StudioShell({api, viewerRuntimeFactory}: {api: TcadApi; viewerRuntimeFactory?: (api: TcadApi) => ViewerRuntime}) {
  const {state, actions} = useAppState();
  const {t} = useI18n();
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
          {t('app.connecting')}
        </p>
      </main>
    );
  }

  if (state.phase === 'fatal') {
    return (
      <main className="launch-screen">
        <h1>TCAD Studio</h1>
        <ErrorNotice
          title={t('app.loadErrorTitle')}
          error={state.globalError ?? undefined}
          message={t('app.loadErrorMessage')}
          actionLabel={t('app.retryConnection')}
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
            title={t('error.operationTitle')}
            error={state.globalError}
            parameterPath={state.globalError.parameterPath}
            suggestion={state.globalError.code === 'network_error'
              ? t('error.networkSuggestion')
              : state.globalError.suggestion}
            trustedSuggestion={state.globalError.code === 'network_error'}
            rolledBack={state.globalError.rolledBack}
            actionLabel={state.globalError.code === 'network_error' ? t('error.reconcile') : undefined}
            onAction={state.globalError.code === 'network_error'
              ? () => void actions.reconcile()
              : undefined}
          />
        </div>
      )}
      <div className={workspaceClass}>
        <div className="workspace-left">
          <RecipeAssistant />
          <ProcessFlowPane
            recipe={state.recipe}
            selectedStepIndex={state.selectedStepIndex}
            onSelect={actions.selectStep}
          >
            <StepStructureBar />
          </ProcessFlowPane>
        </div>
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
    <I18nProvider>
      <AppStateProvider api={resolvedApi}>
        <StudioShell api={resolvedApi} viewerRuntimeFactory={viewerRuntimeFactory} />
      </AppStateProvider>
    </I18nProvider>
  );
}
