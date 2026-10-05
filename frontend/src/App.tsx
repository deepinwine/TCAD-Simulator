import {useEffect, useMemo, useRef, useState} from 'react';
import {createTcadApi} from './api/client';
import type {MaskAsset, TcadApi} from './api/types';
import {MaskWorkbench} from './mask/MaskWorkbench';
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
  const [workbench, setWorkbench] = useState<{
    asset: MaskAsset;
    stepIndex: number;
  } | null>(null);
  const [openingMask, setOpeningMask] = useState(false);
  const maskController = useRef<AbortController | null>(null);
  useEffect(() => () => maskController.current?.abort(), []);
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

  const openMask = async () => {
    if (selectedStep === null || openingMask || state.activeMutation !== null)
      return;
    const controller = new AbortController();
    maskController.current = controller;
    setOpeningMask(true);
    try {
      const id = selectedStep.params.mask_asset_id;
      const revision = selectedStep.params.mask_asset_revision;
      const sizeX =
        (state.model?.gridShape[0] ?? 200) * (state.model?.voxelSizeNm ?? 10);
      const sizeY =
        (state.model?.gridShape[1] ?? 200) * (state.model?.voxelSizeNm ?? 10);
      const asset: MaskAsset =
        selectedStep.params.mask_mode === "Asset" &&
        typeof id === "string" && id.trim() !== "" &&
        typeof revision === "number" && Number.isInteger(revision) && revision > 0
          ? await api.getMaskAsset(id, revision, controller.signal)
          : {
              version: 1,
              id: `mask_${crypto.randomUUID()}`,
              revision: 0,
              name: selectedStep.instanceName,
              coordinateUnit: "nm",
              boundsNm: [0, 0, sizeX, sizeY],
              layers: [
                { id: "1/0", layer: 1, datatype: 0, name: "M1", visible: true },
              ],
              shapes: [],
              source: { kind: "editor" },
            };
      if (!controller.signal.aborted)
        setWorkbench({ asset, stepIndex: selectedStep.index });
    } catch (error) {
      if (!controller.signal.aborted) actions.reportMaskError(error);
    } finally {
      if (!controller.signal.aborted) setOpeningMask(false);
    }
  };

  return (
    <><main className="studio-shell" inert={workbench !== null || openingMask ? true : undefined}>
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
        <ParameterPanel step={selectedStep} collapsed={parametersCollapsed} onEditMask={() => void openMask()} />
        <ThreeViewer api={api} refreshToken={state.previewGeneration} runtimeFactory={viewerRuntimeFactory} />
      </div>
      <TimelineBar />
    </main>
    {workbench !== null && <MaskWorkbench api={api} initialAsset={workbench.asset} stepIndex={workbench.stepIndex} onApply={actions.applyMaskAsset} onError={actions.reportMaskError} onClose={() => setWorkbench(null)} />}</>
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
