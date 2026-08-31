import {TcadApiError} from '../api/client';
import type {
  InitView,
  MaterialView,
  ModelSummaryView,
  RunView,
  RuntimeStatus,
  SetStepView,
  StepView,
  TimelineRestoreView,
  TimelineView,
} from '../api/types';

export type AppPhase = 'booting' | 'ready' | 'running' | 'fatal';
export type ActiveMutation = 'step' | 'to' | 'all' | 'timeline' | 'undo' | 'redo' | null;
export type TimelineStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface ParameterValidation {
  status: 'valid' | 'invalid';
  message?: string;
}

export interface ParameterDraft {
  value: unknown;
  rawValue?: string | boolean;
  sequence: number;
  validation: ParameterValidation;
}

export interface ParameterError {
  sequence: number;
  error: TcadApiError;
}

export interface AppState {
  phase: AppPhase;
  recipe: StepView[];
  selectedStepIndex: number | null;
  previewGeneration: number;
  lastModelRevision: number | null;
  lastRunResult: unknown;
  timeline: TimelineView | null;
  timelineStatus: TimelineStatus;
  timelineError: TcadApiError | null;
  historicalStepIndex: number | null;
  drafts: Record<string, ParameterDraft>;
  parameterErrors: Record<string, ParameterError>;
  stepErrors: Record<number, TcadApiError>;
  activeMutation: ActiveMutation;
  globalError: TcadApiError | null;
  model: ModelSummaryView | null;
  factories: string[];
  materials: MaterialView[];
  uiState: Record<string, unknown>;
}

export type AppAction =
  | {type: 'bootstrap/started'}
  | {type: 'bootstrap/succeeded'; payload: InitView}
  | {type: 'bootstrap/failed'; error: TcadApiError}
  | {type: 'step/selected'; index: number}
  | {
    type: 'parameter/draftChanged';
    index: number;
    key: string;
    value: unknown;
    rawValue?: string | boolean;
    sequence: number;
    validation: ParameterValidation;
  }
  | {
    type: 'parameter/saveSucceeded';
    index: number;
    key: string;
    sequence: number;
    payload: SetStepView;
  }
  | {
    type: 'parameter/saveFailed';
    index: number;
    key: string;
    sequence: number;
    error: TcadApiError;
  }
  | {type: 'run/started'; operation: Exclude<ActiveMutation, null>}
  | {type: 'run/succeeded'; payload: RunView; index?: number}
  | {type: 'run/failed'; index?: number; error: TcadApiError}
  | {type: 'timeline/loadStarted'}
  | {type: 'timeline/loadCancelled'}
  | {type: 'timeline/loaded'; payload: TimelineView; errorToClear?: TcadApiError}
  | {type: 'timeline/loadFailed'; error: TcadApiError}
  | {type: 'timeline/restoreSucceeded'; payload: TimelineRestoreView}
  | {type: 'timeline/restoreFailed'; error: TcadApiError}
  | {type: 'history/applied'; model?: ModelSummaryView}
  | {type: 'reconcile/succeeded'; payload: TimelineView}
  | {type: 'mutation/finished'};

export const initialAppState: AppState = {
  phase: 'booting',
  recipe: [],
  selectedStepIndex: null,
  previewGeneration: 0,
  lastModelRevision: null,
  lastRunResult: undefined,
  timeline: null,
  timelineStatus: 'idle',
  timelineError: null,
  historicalStepIndex: null,
  drafts: {},
  parameterErrors: {},
  stepErrors: {},
  activeMutation: null,
  globalError: null,
  model: null,
  factories: [],
  materials: [],
  uiState: {},
};

export function parameterDraftKey(index: number, key: string): string {
  return `${index}:${key}`;
}

export function hasUnsavedDrafts(state: Pick<AppState, 'drafts'>): boolean {
  return Object.keys(state.drafts).length > 0;
}

function withoutKey<T>(source: Record<string, T>, key: string): Record<string, T> {
  const result = {...source};
  delete result[key];
  return result;
}

function withoutMatchingParameterError(
  source: Record<string, ParameterError>,
  key: string,
  sequence: number,
): Record<string, ParameterError> {
  return source[key]?.sequence === sequence ? withoutKey(source, key) : source;
}

function withoutStepError(
  source: Record<number, TcadApiError>,
  index: number | undefined,
): Record<number, TcadApiError> {
  if (index === undefined || source[index] === undefined) return source;
  const result = {...source};
  delete result[index];
  return result;
}

function applyStatuses(
  recipe: StepView[],
  authoritativeStep: StepView,
  statuses: RuntimeStatus[],
): StepView[] {
  return recipe.map((existing, position) => {
    const authoritative = existing.index === authoritativeStep.index
      ? authoritativeStep
      : existing;
    const runtimeStatus = statuses[position];
    return runtimeStatus === undefined
      ? authoritative
      : {...authoritative, runtimeStatus};
  });
}

function updateStepRuntimeStatus(
  recipe: StepView[],
  index: number | undefined,
  runtimeStatus: RuntimeStatus | undefined,
): StepView[] {
  if (index === undefined || runtimeStatus === undefined) return recipe;
  return recipe.map(item => item.index === index ? {...item, runtimeStatus} : item);
}

function applyTimelineStatuses(recipe: StepView[], timeline: TimelineView): StepView[] {
  const statuses = new Map<number, RuntimeStatus>();
  for (const item of timeline.items) {
    if (!statuses.has(item.index)) statuses.set(item.index, item.runtimeStatus);
  }
  return recipe.map(item => {
    const runtimeStatus = statuses.get(item.index);
    return runtimeStatus === undefined ? item : {...item, runtimeStatus};
  });
}

function canonicalizeTimeline(timeline: TimelineView): TimelineView {
  const seen = new Set<number>();
  const items = timeline.items
    .filter(item => {
      if (seen.has(item.index)) return false;
      seen.add(item.index);
      return true;
    })
    .sort((left, right) => left.index - right.index);
  return {
    items,
    current: items.some(item => item.index === timeline.current) ? timeline.current : -1,
  };
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'bootstrap/started':
      return {...state, phase: 'booting', globalError: null};
    case 'bootstrap/succeeded':
      return {
        ...state,
        phase: 'ready',
        recipe: action.payload.recipe,
        selectedStepIndex: action.payload.recipe[0]?.index ?? null,
        previewGeneration: state.previewGeneration + 1,
        timeline: null,
        timelineStatus: 'idle',
        timelineError: null,
        historicalStepIndex: null,
        drafts: {},
        parameterErrors: {},
        stepErrors: {},
        activeMutation: null,
        globalError: null,
        model: action.payload.model,
        factories: action.payload.factories,
        materials: action.payload.materials,
        uiState: action.payload.uiState,
      };
    case 'bootstrap/failed':
      return {...state, phase: 'fatal', activeMutation: null, globalError: action.error};
    case 'step/selected':
      return {...state, selectedStepIndex: action.index};
    case 'parameter/draftChanged': {
      const draftKey = parameterDraftKey(action.index, action.key);
      return {
        ...state,
        drafts: {
          ...state.drafts,
          [draftKey]: {
            value: action.value,
            ...(action.rawValue === undefined ? {} : {rawValue: action.rawValue}),
            sequence: action.sequence,
            validation: action.validation,
          },
        },
        parameterErrors: withoutKey(state.parameterErrors, draftKey),
      };
    }
    case 'parameter/saveSucceeded': {
      const draftKey = parameterDraftKey(action.index, action.key);
      if (state.drafts[draftKey]?.sequence !== action.sequence) return state;
      return {
        ...state,
        recipe: applyStatuses(state.recipe, action.payload.step, action.payload.statuses),
        drafts: withoutKey(state.drafts, draftKey),
        parameterErrors: withoutMatchingParameterError(
          state.parameterErrors,
          draftKey,
          action.sequence,
        ),
      };
    }
    case 'parameter/saveFailed': {
      const draftKey = parameterDraftKey(action.index, action.key);
      if (state.drafts[draftKey]?.sequence !== action.sequence) return state;
      return {
        ...state,
        parameterErrors: {
          ...state.parameterErrors,
          [draftKey]: {sequence: action.sequence, error: action.error},
        },
      };
    }
    case 'run/started':
      return {
        ...state,
        phase: 'running',
        activeMutation: action.operation,
        historicalStepIndex: action.operation === 'timeline'
          ? state.historicalStepIndex
          : null,
        globalError: null,
      };
    case 'run/succeeded': {
      const index = action.payload.index ?? action.index;
      return {
        ...state,
        recipe: updateStepRuntimeStatus(
          state.recipe,
          index,
          action.payload.runtimeStatus,
        ),
        model: action.payload.model ?? state.model,
        lastModelRevision: action.payload.modelRevision ?? state.lastModelRevision,
        lastRunResult: action.payload.result,
        previewGeneration: state.previewGeneration + 1,
        stepErrors: state.activeMutation === 'all'
          ? {}
          : withoutStepError(state.stepErrors, index),
        historicalStepIndex: null,
        globalError: null,
      };
    }
    case 'run/failed': {
      const index = action.index !== undefined
        && state.recipe.some(item => item.index === action.index)
        ? action.index
        : undefined;
      const recipe = updateStepRuntimeStatus(state.recipe, index, 'error');
      return index === undefined
        ? {...state, globalError: action.error}
        : {
          ...state,
          recipe,
          stepErrors: {...state.stepErrors, [index]: action.error},
        };
    }
    case 'timeline/loadStarted':
      return {
        ...state,
        timelineStatus: 'loading',
        timelineError: null,
        globalError: state.timelineError !== null && state.globalError === state.timelineError
          ? null
          : state.globalError,
      };
    case 'timeline/loadCancelled':
      return {
        ...state,
        timelineStatus: state.timeline === null ? 'idle' : 'ready',
      };
    case 'timeline/loaded': {
      const timeline = canonicalizeTimeline(action.payload);
      return {
        ...state,
        recipe: applyTimelineStatuses(state.recipe, timeline),
        timeline,
        timelineStatus: 'ready',
        timelineError: null,
        globalError: action.errorToClear !== undefined
          && state.globalError === action.errorToClear
          ? null
          : state.globalError,
      };
    }
    case 'timeline/loadFailed':
      return {
        ...state,
        timelineStatus: 'error',
        timelineError: action.error,
        globalError: action.error,
      };
    case 'timeline/restoreSucceeded': {
      const timeline = canonicalizeTimeline(action.payload.timeline);
      const recipe = applyTimelineStatuses(action.payload.recipe, timeline);
      const selectedStepIndex = timeline.current >= 0
        && recipe.some(item => item.index === timeline.current)
        ? timeline.current
        : null;
      // lastModelRevision 仅保留最近一次 run 报告提示；几何权威始终是 manifest.rev。
      return {
        ...state,
        recipe,
        model: action.payload.model,
        timeline,
        timelineStatus: 'ready',
        timelineError: null,
        historicalStepIndex: timeline.current >= 0
          ? timeline.current
          : null,
        selectedStepIndex,
        previewGeneration: state.previewGeneration + 1,
        drafts: {},
        parameterErrors: {},
        stepErrors: {},
        globalError: null,
      };
    }
    case 'timeline/restoreFailed':
      return {...state, globalError: action.error};
    case 'history/applied':
      // undo/redo 有意使步骤缓存失效（ADR-008）：几何权威是 manifest.rev，
      // 这里只 bump previewGeneration 让 Viewer 重拉。
      return {
        ...state,
        model: action.model ?? state.model,
        historicalStepIndex: null,
        globalError: null,
        previewGeneration: state.previewGeneration + 1,
      };
    case 'reconcile/succeeded': {
      const timeline = canonicalizeTimeline(action.payload);
      return {
        ...state,
        recipe: applyTimelineStatuses(state.recipe, timeline),
        timeline,
        timelineStatus: 'ready',
        timelineError: null,
        globalError: null,
        // 服务端可能已完成运行（M2 验收实测）：强制 Viewer 重拉 manifest/STL
        previewGeneration: state.previewGeneration + 1,
      };
    }
    case 'mutation/finished':
      return state.phase === 'fatal'
        ? {...state, activeMutation: null}
        : {...state, phase: 'ready', activeMutation: null};
  }
}
