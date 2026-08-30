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
  sequence: number;
  validation: ParameterValidation;
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
  | {type: 'run/succeeded'; payload: RunView}
  | {type: 'run/failed'; index?: number; error: TcadApiError}
  | {type: 'timeline/loaded'; payload: TimelineView}
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

function withoutKey<T>(source: Record<string, T>, key: string): Record<string, T> {
  const result = {...source};
  delete result[key];
  return result;
}

function withoutStepError(
  source: Record<number, TcadApiError>,
  index: number,
): Record<number, TcadApiError> {
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

function optionalModelRevision(value: TimelineRestoreView): number | undefined {
  const candidate = (value as TimelineRestoreView & {modelRevision?: unknown}).modelRevision;
  return typeof candidate === 'number' && Number.isInteger(candidate) && candidate >= 0
    ? candidate
    : undefined;
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
            sequence: action.sequence,
            validation: action.validation,
          },
        },
      };
    }
    case 'parameter/saveSucceeded': {
      const draftKey = parameterDraftKey(action.index, action.key);
      if (state.drafts[draftKey]?.sequence !== action.sequence) return state;
      return {
        ...state,
        recipe: applyStatuses(state.recipe, action.payload.step, action.payload.statuses),
        drafts: withoutKey(state.drafts, draftKey),
        stepErrors: withoutStepError(state.stepErrors, action.index),
      };
    }
    case 'parameter/saveFailed': {
      const draftKey = parameterDraftKey(action.index, action.key);
      if (state.drafts[draftKey]?.sequence !== action.sequence) return state;
      return {
        ...state,
        stepErrors: {...state.stepErrors, [action.index]: action.error},
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
        recipe: action.payload.recipe ?? state.recipe,
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
      return {...state, timeline: action.payload};
    case 'timeline/loadFailed':
      return {...state, globalError: action.error};
    case 'timeline/restoreSucceeded': {
      const modelRevision = optionalModelRevision(action.payload);
      return {
        ...state,
        recipe: action.payload.recipe,
        model: action.payload.model,
        timeline: action.payload.timeline,
        selectedStepIndex: action.payload.timeline.current,
        lastModelRevision: modelRevision ?? state.lastModelRevision,
        previewGeneration: state.previewGeneration + 1,
        drafts: {},
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
