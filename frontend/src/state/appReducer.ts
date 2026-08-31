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
export type ActiveMutation = 'step' | 'to' | 'all' | 'timeline' | null;

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
  | {type: 'timeline/loaded'; payload: TimelineView; errorToClear?: TcadApiError}
  | {type: 'timeline/loadFailed'; error: TcadApiError}
  | {type: 'timeline/restoreSucceeded'; payload: TimelineRestoreView}
  | {type: 'timeline/restoreFailed'; error: TcadApiError}
  | {type: 'mutation/finished'};

export const initialAppState: AppState = {
  phase: 'booting',
  recipe: [],
  selectedStepIndex: null,
  previewGeneration: 0,
  lastModelRevision: null,
  lastRunResult: undefined,
  timeline: null,
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
        globalError: null,
      };
    case 'run/succeeded':
      return {
        ...state,
        recipe: updateStepRuntimeStatus(
          state.recipe,
          action.payload.index ?? action.index,
          action.payload.runtimeStatus,
        ),
        model: action.payload.model ?? state.model,
        lastModelRevision: action.payload.modelRevision ?? state.lastModelRevision,
        lastRunResult: action.payload.result,
        previewGeneration: state.previewGeneration + 1,
        globalError: null,
      };
    case 'run/failed':
      return action.index === undefined
        ? {...state, globalError: action.error}
        : {
          ...state,
          stepErrors: {...state.stepErrors, [action.index]: action.error},
        };
    case 'timeline/loaded':
      return {
        ...state,
        recipe: applyTimelineStatuses(state.recipe, action.payload),
        timeline: action.payload,
        globalError: action.errorToClear !== undefined
          && state.globalError === action.errorToClear
          ? null
          : state.globalError,
      };
    case 'timeline/loadFailed':
      return {...state, globalError: action.error};
    case 'timeline/restoreSucceeded': {
      const selectedStepIndex = action.payload.timeline.current >= 0
        && action.payload.recipe.some(item => item.index === action.payload.timeline.current)
        ? action.payload.timeline.current
        : null;
      // lastModelRevision 仅保留最近一次 run 报告提示；几何权威始终是 manifest.rev。
      return {
        ...state,
        recipe: action.payload.recipe,
        model: action.payload.model,
        timeline: action.payload.timeline,
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
    case 'mutation/finished':
      return state.phase === 'fatal'
        ? {...state, activeMutation: null}
        : {...state, phase: 'ready', activeMutation: null};
  }
}
