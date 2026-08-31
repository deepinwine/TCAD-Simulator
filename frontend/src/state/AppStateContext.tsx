import {
  createContext,
  type Dispatch,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from 'react';
import {TcadApiError} from '../api/client';
import type {RunView, TcadApi} from '../api/types';
import {
  type ActiveMutation,
  type AppAction,
  type AppState,
  appReducer,
  hasUnsavedDrafts,
  initialAppState,
  parameterDraftKey,
  type ParameterValidation,
} from './appReducer';

export interface AppStateActions {
  bootstrap(): Promise<void>;
  selectStep(index: number): void;
  updateDraft(
    index: number,
    key: string,
    value: unknown,
    validation?: ParameterValidation,
    rawValue?: string | boolean,
  ): number;
  saveParameter(index: number, key: string): Promise<void>;
  runStep(index?: number): Promise<void>;
  runTo(index?: number): Promise<void>;
  runAll(): Promise<void>;
  loadTimeline(): Promise<void>;
  restoreTimeline(index: number): Promise<void>;
  reconcile(): Promise<void>;
  undo(): Promise<void>;
  redo(): Promise<void>;
}

export interface AppStateContextValue {
  state: AppState;
  actions: AppStateActions;
}

interface AppStateProviderProps {
  api: TcadApi;
  children: ReactNode;
}

const AppStateContext = createContext<AppStateContextValue | null>(null);

function normalizeError(error: unknown): TcadApiError {
  if (error instanceof TcadApiError) return error;
  return new TcadApiError('发生未知客户端错误。', {
    status: 0,
    code: 'unexpected_client_error',
  });
}

function errorStepIndex(
  error: TcadApiError,
  recipe: AppState['recipe'],
  operation: 'step' | 'to' | 'all',
  fallback?: number,
): number | undefined {
  const details = error.details;
  if (typeof details === 'object' && details !== null && !Array.isArray(details)) {
    const candidate = (details as Record<string, unknown>).stepIndex;
    if (typeof candidate === 'number' && Number.isInteger(candidate) && candidate >= 0) {
      return recipe.some(item => item.index === candidate) ? candidate : undefined;
    }
  }
  return operation === 'step'
    && fallback !== undefined
    && recipe.some(item => item.index === fallback)
    ? fallback
    : undefined;
}

function isAbortError(error: unknown, signal: AbortSignal): boolean {
  if (signal.aborted) return true;
  return typeof error === 'object'
    && error !== null
    && 'name' in error
    && (error as {name?: unknown}).name === 'AbortError';
}

export function AppStateProvider({api, children}: AppStateProviderProps) {
  const [state, reactDispatch] = useReducer(appReducer, initialAppState);
  const stateRef = useRef(state);
  const mountedRef = useRef(false);
  const bootstrapPromiseRef = useRef<Promise<void> | null>(null);
  const bootstrapAttemptRef = useRef<object | null>(null);
  const bootstrapCompletedRef = useRef(false);
  const mutationGateRef = useRef<ActiveMutation>(null);
  const sequenceRef = useRef<Record<string, number>>({});
  const savingRef = useRef<Record<string, number>>({});
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const pendingSaveCountRef = useRef(0);
  const timelineGenerationRef = useRef(0);
  const standaloneTimelineControllerRef = useRef<AbortController | null>(null);
  const standaloneTimelinePromiseRef = useRef<Promise<void> | null>(null);
  const standaloneTimelineDedupeRef = useRef(false);
  const timelineErrorRef = useRef<TcadApiError | null>(null);
  const activeControllersRef = useRef(new Set<AbortController>());
  const lifecycleGenerationRef = useRef(0);

  const dispatch = useCallback<Dispatch<AppAction>>((action) => {
    if (!mountedRef.current) return;
    stateRef.current = appReducer(stateRef.current, action);
    reactDispatch(action);
  }, []);

  const createController = useCallback(() => {
    const controller = new AbortController();
    activeControllersRef.current.add(controller);
    return controller;
  }, []);

  const releaseController = useCallback((controller: AbortController) => {
    activeControllersRef.current.delete(controller);
  }, []);

  const cancelStandaloneTimeline = useCallback(() => {
    timelineGenerationRef.current += 1;
    const controller = standaloneTimelineControllerRef.current;
    standaloneTimelineControllerRef.current = null;
    standaloneTimelinePromiseRef.current = null;
    standaloneTimelineDedupeRef.current = false;
    controller?.abort();
    if (controller !== null && mountedRef.current) {
      dispatch({type: 'timeline/loadCancelled'});
    }
  }, [dispatch]);

  const bootstrap = useCallback((): Promise<void> => {
    if (bootstrapCompletedRef.current) return Promise.resolve();
    if (bootstrapPromiseRef.current !== null) return bootstrapPromiseRef.current;

    dispatch({type: 'bootstrap/started'});
    const controller = createController();
    const attempt = {};
    bootstrapAttemptRef.current = attempt;
    const operation = (async () => {
      try {
        await Promise.resolve();
        const payload = await api.init(controller.signal);
        if (!mountedRef.current) return;
        bootstrapCompletedRef.current = true;
        dispatch({type: 'bootstrap/succeeded', payload});
      } catch (error) {
        if (!mountedRef.current) return;
        if (isAbortError(error, controller.signal)) return;
        dispatch({type: 'bootstrap/failed', error: normalizeError(error)});
      } finally {
        releaseController(controller);
        if (bootstrapAttemptRef.current === attempt) {
          bootstrapPromiseRef.current = null;
          bootstrapAttemptRef.current = null;
        }
      }
    })();
    bootstrapPromiseRef.current = operation;
    return operation;
  }, [api, createController, dispatch, releaseController]);

  const selectStep = useCallback((index: number) => {
    if (!mountedRef.current) return;
    if (!stateRef.current.recipe.some(item => item.index === index)) return;
    dispatch({type: 'step/selected', index});
  }, [dispatch]);

  const updateDraft = useCallback((
    index: number,
    key: string,
    value: unknown,
    validation: ParameterValidation = {status: 'valid'},
    rawValue?: string | boolean,
  ): number => {
    if (!mountedRef.current) return 0;
    const draftKey = parameterDraftKey(index, key);
    const previous = Math.max(
      sequenceRef.current[draftKey] ?? 0,
      stateRef.current.drafts[draftKey]?.sequence ?? 0,
    );
    const sequence = previous + 1;
    sequenceRef.current[draftKey] = sequence;
    dispatch({
      type: 'parameter/draftChanged',
      index,
      key,
      value,
      rawValue,
      sequence,
      validation,
    });
    return sequence;
  }, [dispatch]);

  const saveParameter = useCallback((index: number, key: string): Promise<void> => {
    if (!mountedRef.current || mutationGateRef.current !== null) return Promise.resolve();
    const draftKey = parameterDraftKey(index, key);
    const draft = stateRef.current.drafts[draftKey];
    if (draft === undefined || draft.validation.status !== 'valid') return Promise.resolve();
    if (savingRef.current[draftKey] === draft.sequence) return Promise.resolve();

    savingRef.current[draftKey] = draft.sequence;
    pendingSaveCountRef.current += 1;
    const controller = createController();
    const operation = saveQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        if (!mountedRef.current || controller.signal.aborted) return;
        try {
          const payload = await api.setStep(
            {index, params: {[key]: draft.value}},
            controller.signal,
          );
          if (!mountedRef.current || controller.signal.aborted) return;
          dispatch({
            type: 'parameter/saveSucceeded',
            index,
            key,
            sequence: draft.sequence,
            payload,
          });
        } catch (error) {
          if (!mountedRef.current || isAbortError(error, controller.signal)) return;
          dispatch({
            type: 'parameter/saveFailed',
            index,
            key,
            sequence: draft.sequence,
            error: normalizeError(error),
          });
        }
      })
      .finally(() => {
        releaseController(controller);
        pendingSaveCountRef.current = Math.max(0, pendingSaveCountRef.current - 1);
        if (savingRef.current[draftKey] === draft.sequence) {
          delete savingRef.current[draftKey];
        }
      });
    saveQueueRef.current = operation.catch(() => undefined);
    return operation;
  }, [api, createController, dispatch, releaseController]);

  const beginMutation = useCallback((operation: Exclude<ActiveMutation, null>): boolean => {
    if (
      !mountedRef.current
      || mutationGateRef.current !== null
      || pendingSaveCountRef.current > 0
      || hasUnsavedDrafts(stateRef.current)
    ) {
      return false;
    }
    cancelStandaloneTimeline();
    mutationGateRef.current = operation;
    dispatch({type: 'run/started', operation});
    return true;
  }, [cancelStandaloneTimeline, dispatch]);

  const finishMutation = useCallback((operation: Exclude<ActiveMutation, null>) => {
    if (!mountedRef.current || mutationGateRef.current !== operation) return;
    mutationGateRef.current = null;
    dispatch({type: 'mutation/finished'});
  }, [dispatch]);

  const runMutation = useCallback(async (
    operation: 'step' | 'to' | 'all',
    request: (signal: AbortSignal) => Promise<RunView>,
    fallbackStepIndex?: number,
  ): Promise<void> => {
    if (!beginMutation(operation)) return;
    const controller = createController();
    try {
      const payload = await request(controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return;
      dispatch({type: 'run/succeeded', payload, index: fallbackStepIndex});
      if (!mountedRef.current) return;
      const timelineGeneration = ++timelineGenerationRef.current;
      try {
        const timeline = await api.getTimeline(controller.signal);
        if (
          !mountedRef.current
          || controller.signal.aborted
          || timelineGeneration !== timelineGenerationRef.current
        ) return;
        const errorToClear = timelineErrorRef.current ?? undefined;
        timelineErrorRef.current = null;
        dispatch({type: 'timeline/loaded', payload: timeline, errorToClear});
      } catch (error) {
        if (!mountedRef.current) return;
        if (isAbortError(error, controller.signal)) return;
        if (timelineGeneration !== timelineGenerationRef.current) return;
        const normalized = normalizeError(error);
        timelineErrorRef.current = normalized;
        dispatch({type: 'timeline/loadFailed', error: normalized});
      }
    } catch (error) {
      if (!mountedRef.current) return;
      if (isAbortError(error, controller.signal)) return;
      const normalized = normalizeError(error);
      dispatch({
        type: 'run/failed',
        index: errorStepIndex(
          normalized,
          stateRef.current.recipe,
          operation,
          fallbackStepIndex,
        ),
        error: normalized,
      });
    } finally {
      releaseController(controller);
      finishMutation(operation);
    }
  }, [api, beginMutation, createController, dispatch, finishMutation, releaseController]);

  const runStep = useCallback((index = stateRef.current.selectedStepIndex ?? undefined) => {
    if (index === undefined) return Promise.resolve();
    return runMutation('step', signal => api.runStep(index, signal), index);
  }, [api, runMutation]);

  const runTo = useCallback((index = stateRef.current.selectedStepIndex ?? undefined) => {
    if (index === undefined) return Promise.resolve();
    return runMutation('to', signal => api.runTo(index, signal), index);
  }, [api, runMutation]);

  const runAll = useCallback(
    () => runMutation('all', signal => api.runAll(signal)),
    [api, runMutation],
  );

  const loadTimeline = useCallback((): Promise<void> => {
    if (!mountedRef.current || mutationGateRef.current !== null) return Promise.resolve();
    if (
      standaloneTimelinePromiseRef.current !== null
      && standaloneTimelineDedupeRef.current
    ) {
      return standaloneTimelinePromiseRef.current;
    }
    const previous = standaloneTimelineControllerRef.current;
    if (previous !== null) {
      timelineGenerationRef.current += 1;
      previous.abort();
    }
    const generation = ++timelineGenerationRef.current;
    const controller = createController();
    standaloneTimelineControllerRef.current = controller;
    standaloneTimelineDedupeRef.current = true;
    queueMicrotask(() => {
      if (standaloneTimelineControllerRef.current === controller) {
        standaloneTimelineDedupeRef.current = false;
      }
    });
    dispatch({type: 'timeline/loadStarted'});
    const operation = (async () => {
      try {
        const payload = await api.getTimeline(controller.signal);
        if (
          !mountedRef.current
          || controller.signal.aborted
          || standaloneTimelineControllerRef.current !== controller
          || generation !== timelineGenerationRef.current
        ) return;
        const errorToClear = timelineErrorRef.current ?? undefined;
        timelineErrorRef.current = null;
        dispatch({type: 'timeline/loaded', payload, errorToClear});
      } catch (error) {
        if (!mountedRef.current) return;
        if (isAbortError(error, controller.signal)) return;
        if (
          standaloneTimelineControllerRef.current !== controller
          || generation !== timelineGenerationRef.current
        ) return;
        const normalized = normalizeError(error);
        timelineErrorRef.current = normalized;
        dispatch({type: 'timeline/loadFailed', error: normalized});
      } finally {
        releaseController(controller);
        if (standaloneTimelineControllerRef.current === controller) {
          standaloneTimelineControllerRef.current = null;
          standaloneTimelinePromiseRef.current = null;
        }
      }
    })();
    standaloneTimelinePromiseRef.current = operation;
    return operation;
  }, [api, createController, dispatch, releaseController]);

  const restoreTimeline = useCallback(async (index: number): Promise<void> => {
    const item = stateRef.current.timeline?.items.find(candidate => candidate.index === index);
    if (item?.snapshotValid !== true || !beginMutation('timeline')) return;

    const controller = createController();
    try {
      const payload = await api.restoreTimeline(index, controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return;
      dispatch({type: 'timeline/restoreSucceeded', payload});
    } catch (error) {
      if (!mountedRef.current) return;
      if (isAbortError(error, controller.signal)) return;
      dispatch({type: 'timeline/restoreFailed', error: normalizeError(error)});
    } finally {
      releaseController(controller);
      finishMutation('timeline');
    }
  }, [api, beginMutation, createController, dispatch, finishMutation, releaseController]);

  /**
   * run 网络失败后的状态对账：以服务端 timeline 为权威重建 UI 状态，
   * 并触发 Viewer 重拉几何（服务端可能已完成运行，本地却以为失败）。
   */
  /**
   * 撤销/重做：applied 时 bump previewGeneration（几何权威是 manifest.rev，
   * ADR-008 步骤缓存有意失效）并重拉 timeline 同步运行状态；无可撤销时静默 no-op。
   */
  const historyStep = useCallback(async (
    operation: 'undo' | 'redo',
  ): Promise<void> => {
    if (!beginMutation(operation)) return;
    const controller = createController();
    try {
      const view = operation === 'undo'
        ? await api.undo(controller.signal)
        : await api.redo(controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return;
      if (!view.applied) return;
      dispatch({
        type: 'history/applied',
        ...(view.model !== undefined ? {model: view.model} : {}),
      });
      const generation = ++timelineGenerationRef.current;
      try {
        const timeline = await api.getTimeline(controller.signal);
        if (
          !mountedRef.current
          || controller.signal.aborted
          || generation !== timelineGenerationRef.current
        ) return;
        timelineErrorRef.current = null;
        dispatch({type: 'timeline/loaded', payload: timeline});
      } catch (timelineError) {
        if (!mountedRef.current) return;
        if (isAbortError(timelineError, controller.signal)) return;
        if (generation !== timelineGenerationRef.current) return;
        const normalized = normalizeError(timelineError);
        timelineErrorRef.current = normalized;
        dispatch({type: 'timeline/loadFailed', error: normalized});
      }
    } catch (error) {
      if (!mountedRef.current) return;
      if (isAbortError(error, controller.signal)) return;
      dispatch({type: 'run/failed', error: normalizeError(error)});
    } finally {
      releaseController(controller);
      finishMutation(operation);
    }
  }, [api, beginMutation, createController, dispatch, finishMutation, releaseController]);

  const undo = useCallback(() => historyStep('undo'), [historyStep]);
  const redo = useCallback(() => historyStep('redo'), [historyStep]);

  const reconcile = useCallback(async (): Promise<void> => {
    if (!mountedRef.current || mutationGateRef.current !== null) return;
    const generation = ++timelineGenerationRef.current;
    const controller = createController();
    try {
      const timeline = await api.getTimeline(controller.signal);
      if (
        !mountedRef.current
        || controller.signal.aborted
        || generation !== timelineGenerationRef.current
      ) return;
      timelineErrorRef.current = null;
      dispatch({type: 'reconcile/succeeded', payload: timeline});
    } catch (error) {
      if (!mountedRef.current) return;
      if (isAbortError(error, controller.signal)) return;
      if (generation !== timelineGenerationRef.current) return;
      const normalized = normalizeError(error);
      timelineErrorRef.current = normalized;
      dispatch({type: 'timeline/loadFailed', error: normalized});
    } finally {
      releaseController(controller);
    }
  }, [api, createController, dispatch, releaseController]);

  useEffect(() => {
    const lifecycleGeneration = ++lifecycleGenerationRef.current;
    mountedRef.current = true;
    stateRef.current = state;
    void bootstrap();
    return () => {
      mountedRef.current = false;
      queueMicrotask(() => {
        if (
          mountedRef.current
          || lifecycleGenerationRef.current !== lifecycleGeneration
        ) return;
        timelineGenerationRef.current += 1;
        standaloneTimelineControllerRef.current = null;
        standaloneTimelinePromiseRef.current = null;
        standaloneTimelineDedupeRef.current = false;
        for (const controller of activeControllersRef.current) controller.abort();
      });
    };
  }, [bootstrap]);

  const actions = useMemo<AppStateActions>(() => ({
    bootstrap,
    selectStep,
    updateDraft,
    saveParameter,
    runStep,
    runTo,
    runAll,
    loadTimeline,
    restoreTimeline,
    reconcile,
    undo,
    redo,
  }), [
    bootstrap,
    loadTimeline,
    reconcile,
    redo,
    restoreTimeline,
    runAll,
    runStep,
    runTo,
    saveParameter,
    selectStep,
    undo,
    updateDraft,
  ]);

  const value = useMemo<AppStateContextValue>(() => ({state, actions}), [actions, state]);
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateContextValue {
  const context = useContext(AppStateContext);
  if (context === null) {
    throw new Error('useAppState 必须在 AppStateProvider 内使用。');
  }
  return context;
}
