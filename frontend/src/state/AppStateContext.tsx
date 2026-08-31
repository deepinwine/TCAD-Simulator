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
  ): number;
  saveParameter(index: number, key: string): Promise<void>;
  runStep(index?: number): Promise<void>;
  runTo(index?: number): Promise<void>;
  runAll(): Promise<void>;
  loadTimeline(): Promise<void>;
  restoreTimeline(index: number): Promise<void>;
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

function errorStepIndex(error: TcadApiError, fallback?: number): number | undefined {
  const details = error.details;
  if (typeof details === 'object' && details !== null && !Array.isArray(details)) {
    const candidate = (details as Record<string, unknown>).stepIndex;
    if (typeof candidate === 'number' && Number.isInteger(candidate) && candidate >= 0) {
      return candidate;
    }
  }
  return fallback;
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

  const dispatch = useCallback<Dispatch<AppAction>>((action) => {
    if (!mountedRef.current) return;
    stateRef.current = appReducer(stateRef.current, action);
    reactDispatch(action);
  }, []);

  const bootstrap = useCallback((): Promise<void> => {
    if (bootstrapCompletedRef.current) return Promise.resolve();
    if (bootstrapPromiseRef.current !== null) return bootstrapPromiseRef.current;

    dispatch({type: 'bootstrap/started'});
    const controller = new AbortController();
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
        dispatch({type: 'bootstrap/failed', error: normalizeError(error)});
      } finally {
        if (mountedRef.current && bootstrapAttemptRef.current === attempt) {
          bootstrapPromiseRef.current = null;
          bootstrapAttemptRef.current = null;
        }
      }
    })();
    bootstrapPromiseRef.current = operation;
    return operation;
  }, [api, dispatch]);

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
      sequence,
      validation,
    });
    return sequence;
  }, [dispatch]);

  const saveParameter = useCallback(async (index: number, key: string): Promise<void> => {
    if (!mountedRef.current || mutationGateRef.current !== null) return;
    const draftKey = parameterDraftKey(index, key);
    const draft = stateRef.current.drafts[draftKey];
    if (draft === undefined || draft.validation.status !== 'valid') return;
    if (savingRef.current[draftKey] === draft.sequence) return;

    savingRef.current[draftKey] = draft.sequence;
    const controller = new AbortController();
    try {
      const payload = await api.setStep(
        {index, params: {[key]: draft.value}},
        controller.signal,
      );
      if (!mountedRef.current) return;
      dispatch({
        type: 'parameter/saveSucceeded',
        index,
        key,
        sequence: draft.sequence,
        payload,
      });
    } catch (error) {
      if (!mountedRef.current) return;
      dispatch({
        type: 'parameter/saveFailed',
        index,
        key,
        sequence: draft.sequence,
        error: normalizeError(error),
      });
    } finally {
      if (
        mountedRef.current
        && savingRef.current[draftKey] === draft.sequence
      ) {
        delete savingRef.current[draftKey];
      }
    }
  }, [api, dispatch]);

  const beginMutation = useCallback((operation: Exclude<ActiveMutation, null>): boolean => {
    if (!mountedRef.current || mutationGateRef.current !== null) return false;
    mutationGateRef.current = operation;
    dispatch({type: 'run/started', operation});
    return true;
  }, [dispatch]);

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
    const controller = new AbortController();
    try {
      const payload = await request(controller.signal);
      if (!mountedRef.current) return;
      dispatch({type: 'run/succeeded', payload, index: fallbackStepIndex});
      if (!mountedRef.current) return;
      try {
        const timeline = await api.getTimeline(controller.signal);
        if (!mountedRef.current) return;
        dispatch({type: 'timeline/loaded', payload: timeline});
      } catch (error) {
        if (!mountedRef.current) return;
        dispatch({type: 'timeline/loadFailed', error: normalizeError(error)});
      }
    } catch (error) {
      if (!mountedRef.current) return;
      const normalized = normalizeError(error);
      dispatch({
        type: 'run/failed',
        index: errorStepIndex(normalized, fallbackStepIndex),
        error: normalized,
      });
    } finally {
      finishMutation(operation);
    }
  }, [api, beginMutation, dispatch, finishMutation]);

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

  const loadTimeline = useCallback(async (): Promise<void> => {
    if (!mountedRef.current) return;
    const controller = new AbortController();
    try {
      const payload = await api.getTimeline(controller.signal);
      if (!mountedRef.current) return;
      dispatch({type: 'timeline/loaded', payload});
    } catch (error) {
      if (!mountedRef.current) return;
      dispatch({type: 'timeline/loadFailed', error: normalizeError(error)});
    }
  }, [api, dispatch]);

  const restoreTimeline = useCallback(async (index: number): Promise<void> => {
    const item = stateRef.current.timeline?.items.find(candidate => candidate.index === index);
    if (item?.snapshotValid !== true || !beginMutation('timeline')) return;

    const controller = new AbortController();
    try {
      const payload = await api.restoreTimeline(index, controller.signal);
      if (!mountedRef.current) return;
      dispatch({type: 'timeline/restoreSucceeded', payload});
    } catch (error) {
      if (!mountedRef.current) return;
      dispatch({type: 'timeline/restoreFailed', error: normalizeError(error)});
    } finally {
      finishMutation('timeline');
    }
  }, [api, beginMutation, dispatch, finishMutation]);

  useEffect(() => {
    mountedRef.current = true;
    stateRef.current = state;
    void bootstrap();
    return () => {
      mountedRef.current = false;
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
  }), [
    bootstrap,
    loadTimeline,
    restoreTimeline,
    runAll,
    runStep,
    runTo,
    saveParameter,
    selectStep,
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
