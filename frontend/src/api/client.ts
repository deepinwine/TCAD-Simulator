import {
  ApiContractError,
  parseHistoryEnvelope,
  parseInitEnvelope,
  parseRecipeLoadEnvelope,
  parseSavedEnvelope,
  parseStepEnvelope,
  parseStepListEnvelope,
  parsePreviewManifestEnvelope,
  parseRunEnvelope,
  parseSetStepEnvelope,
  parseTimelineEnvelope,
  parseTimelineRestoreEnvelope,
} from './schemas';
import type {
  HistoryView,
  InitView,
  RecipeLoadView,
  PreviewManifestRequest,
  PreviewManifestView,
  PreviewStlRequest,
  RunView,
  SetStepRequest,
  StepView,
  SetStepView,
  TcadApi,
  TimelineRestoreView,
  TimelineView,
} from './types';

interface TcadApiErrorOptions {
  status: number;
  code?: string;
  errorType?: string;
  parameterPath?: string;
  suggestion?: string;
  rolledBack?: boolean;
  details?: unknown;
  causeValue?: unknown;
}

export class TcadApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly errorType?: string;
  readonly parameterPath?: string;
  readonly suggestion?: string;
  readonly rolledBack?: boolean;
  readonly details?: unknown;
  readonly causeValue?: unknown;

  constructor(message: string, options: TcadApiErrorOptions) {
    super(message);
    this.name = 'TcadApiError';
    this.status = options.status;
    this.code = options.code;
    this.errorType = options.errorType;
    this.parameterPath = options.parameterPath;
    this.suggestion = options.suggestion;
    this.rolledBack = options.rolledBack;
    this.details = options.details;
    this.causeValue = options.causeValue;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringField(source: Record<string, unknown>, key: string): string | undefined {
  return typeof source[key] === 'string' ? source[key] : undefined;
}

function booleanField(source: Record<string, unknown>, key: string): boolean | undefined {
  return typeof source[key] === 'boolean' ? source[key] : undefined;
}

function flatStepDetails(source: Record<string, unknown>): Record<string, unknown> | undefined {
  const details: Record<string, unknown> = {};
  if (
    typeof source.step_index === 'number'
    && Number.isFinite(source.step_index)
    && Number.isInteger(source.step_index)
  ) {
    details.stepIndex = source.step_index;
  }
  if (typeof source.instance_name === 'string') details.instanceName = source.instance_name;
  if (typeof source.step_type === 'string') details.stepType = source.step_type;
  return Object.keys(details).length > 0 ? details : undefined;
}

function safeExplicitDetails(value: unknown): Record<string, unknown> | undefined {
  if (!isRecord(value)) return undefined;
  const details: Record<string, unknown> = {};
  if (typeof value.index === 'number' && Number.isFinite(value.index) && Number.isInteger(value.index)) {
    details.index = value.index;
  }
  return Object.keys(details).length > 0 ? details : undefined;
}

function toApiError(status: number, payload: unknown): TcadApiError {
  const source = isRecord(payload) ? payload : {};
  const explicitDetails = safeExplicitDetails(source.details);
  const stepDetails = flatStepDetails(source);
  let details = explicitDetails;
  if (stepDetails !== undefined) {
    details = explicitDetails !== undefined ? {...explicitDetails, ...stepDetails} : stepDetails;
  }
  const message = stringField(source, 'error')
    ?? stringField(source, 'message')
    ?? `TCAD 请求失败（HTTP ${status}）。`;
  const code = stringField(source, 'code');
  return new TcadApiError(message, {
    status,
    code,
    errorType: stringField(source, 'error_type'),
    parameterPath: stringField(source, 'parameter_path'),
    suggestion: stringField(source, 'suggestion'),
    rolledBack: booleanField(source, 'rolled_back'),
    details,
    causeValue: {
      kind: 'server_error',
      status,
      ...(code !== undefined ? {code} : {}),
    },
  });
}

function isAbortError(error: unknown): boolean {
  return (error instanceof DOMException && error.name === 'AbortError')
    || (isRecord(error) && error.name === 'AbortError');
}

async function fetchSafely(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new TcadApiError('无法连接 TCAD 服务。', {
      status: 0,
      code: 'network_error',
    });
  }
}

async function readJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json() as unknown;
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new TcadApiError('TCAD 服务返回了无效 JSON。', {
      status: response.status,
      code: 'invalid_json',
    });
  }
}

function isSuccessfulEnvelope(payload: unknown): boolean {
  return isRecord(payload) && payload.ok === true;
}

export async function apiJson<T>(
  path: string,
  init: RequestInit,
  parse: (payload: unknown) => T,
): Promise<T> {
  const requestInit: RequestInit = {...init, credentials: 'same-origin'};
  if ((requestInit.method ?? 'GET').toUpperCase() === 'GET') {
    delete requestInit.body;
  }
  const response = await fetchSafely(path, requestInit);
  const payload = await readJsonSafely(response);
  if (!response.ok || !isSuccessfulEnvelope(payload)) {
    throw toApiError(response.status, payload);
  }
  return parse(payload);
}

export function apiGetJson<T>(
  path: string,
  parse: (payload: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  return apiJson(path, {method: 'GET', credentials: 'same-origin', signal}, parse);
}

export function apiPostJson<T>(
  path: string,
  body: unknown,
  parse: (payload: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  return apiJson(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
    signal,
  }, parse);
}

export async function apiBinary(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetchSafely(path, {
    method: 'GET',
    credentials: 'same-origin',
    signal,
  });
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
  if (contentType.includes('json')) {
    const payload = await readJsonSafely(response);
    if (!response.ok || !isSuccessfulEnvelope(payload)) {
      throw toApiError(response.status, payload);
    }
    throw new TcadApiError('期望二进制资源，但 TCAD 服务返回了 JSON。', {
      status: response.status,
      code: 'unexpected_json_response',
    });
  }
  if (!response.ok) {
    throw new TcadApiError(`二进制资源请求失败（HTTP ${response.status}）。`, {
      status: response.status,
      code: 'binary_request_failed',
    });
  }
  try {
    return await response.arrayBuffer();
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new TcadApiError('无法读取 TCAD 二进制资源。', {
      status: response.status,
      code: 'binary_read_failed',
    });
  }
}

function requireRequestInteger(value: number, path: string, minimum: number): number {
  if (!Number.isFinite(value) || !Number.isInteger(value) || value < minimum) {
    throw new ApiContractError(path, `integer >= ${minimum}`);
  }
  return value;
}

function previewManifestPath(request: PreviewManifestRequest): string {
  const query = new URLSearchParams();
  if (request.mode !== undefined) query.set('mode', request.mode);
  if (request.faceLimit !== undefined) {
    query.set('face_limit', String(requireRequestInteger(request.faceLimit, 'request.faceLimit', 1)));
  }
  const suffix = query.toString();
  return suffix ? `/api/preview/manifest?${suffix}` : '/api/preview/manifest';
}

function previewStlPath(request: PreviewStlRequest): string {
  const query = new URLSearchParams({
    mat_id: String(requireRequestInteger(request.materialId, 'request.materialId', 1)),
    rev: String(requireRequestInteger(request.revision, 'request.revision', 0)),
    mode: request.mode ?? 'solid',
  });
  return `/api/preview/stl?${query.toString()}`;
}

export function createTcadApi(): TcadApi {
  return {
    init(signal?: AbortSignal): Promise<InitView> {
      return apiGetJson('/api/init', parseInitEnvelope, signal);
    },
    setStep(request: SetStepRequest, signal?: AbortSignal): Promise<SetStepView> {
      const index = requireRequestInteger(request.index, 'request.index', 0);
      return apiPostJson(
        '/api/step/set',
        {
          index,
          ...(request.enabled !== undefined ? {enabled: request.enabled} : {}),
          ...(request.params !== undefined ? {params: request.params} : {}),
          ...(request.loop !== undefined ? {loop: request.loop} : {}),
          ...(request.group !== undefined ? {group: request.group} : {}),
          ...(request.noAutosave !== undefined ? {no_autosave: request.noAutosave} : {}),
        },
        payload => parseSetStepEnvelope(payload, index),
        signal,
      );
    },
    runStep(index: number, signal?: AbortSignal): Promise<RunView> {
      const validatedIndex = requireRequestInteger(index, 'request.index', 0);
      return apiPostJson('/api/run/step', {index: validatedIndex}, parseRunEnvelope, signal);
    },
    runTo(index: number, signal?: AbortSignal): Promise<RunView> {
      const validatedIndex = requireRequestInteger(index, 'request.index', 0);
      return apiPostJson('/api/run/to', {index: validatedIndex}, parseRunEnvelope, signal);
    },
    runAll(signal?: AbortSignal): Promise<RunView> {
      return apiPostJson('/api/run/all', {}, parseRunEnvelope, signal);
    },
    undo(signal?: AbortSignal): Promise<HistoryView> {
      return apiPostJson(
        '/api/undo',
        {},
        (payload: unknown) => parseHistoryEnvelope(payload, 'undone'),
        signal,
      );
    },
    redo(signal?: AbortSignal): Promise<HistoryView> {
      return apiPostJson(
        '/api/redo',
        {},
        (payload: unknown) => parseHistoryEnvelope(payload, 'redone'),
        signal,
      );
    },
    importRecipe(
      request: {recipe: unknown; autosaveCurrent?: boolean; currentName?: string},
      signal?: AbortSignal,
    ): Promise<RecipeLoadView> {
      return apiPostJson(
        '/api/recipe/import',
        {
          recipe: request.recipe,
          ...(request.autosaveCurrent === undefined ? {} : {autosave_current: request.autosaveCurrent}),
          ...(request.currentName === undefined ? {} : {current_name: request.currentName}),
        },
        (payload: unknown) => parseRecipeLoadEnvelope(payload, 'imported'),
        signal,
      );
    },
    newRecipe(name: string, signal?: AbortSignal): Promise<RecipeLoadView> {
      return apiPostJson(
        '/api/recipe/new',
        {name},
        (payload: unknown) => parseRecipeLoadEnvelope(payload, null),
        signal,
      );
    },
    saveRecipe(name: string, signal?: AbortSignal): Promise<{saved: boolean}> {
      return apiPostJson(
        '/api/recipe/save',
        {name},
        parseSavedEnvelope,
        signal,
      );
    },
    exportRecipe(scope: string = 'current', signal?: AbortSignal): Promise<Blob> {
      return apiBinary(`/api/recipe/export?scope=${encodeURIComponent(scope)}`, signal)
        .then(buffer => new Blob([buffer], {type: 'application/json'}));
    },
    loadRecipe(id: string, signal?: AbortSignal): Promise<RecipeLoadView> {
      return apiPostJson(
        '/api/recipe/load',
        {id},
        (payload: unknown) => parseRecipeLoadEnvelope(payload, 'loaded'),
        signal,
      );
    },
    addStep(name: string, signal?: AbortSignal): Promise<StepView[]> {
      return apiPostJson(
        '/api/recipe/add',
        {name},
        parseStepListEnvelope,
        signal,
      );
    },
    removeStep(index: number, signal?: AbortSignal): Promise<StepView[]> {
      const validated = requireRequestInteger(index, 'request.index', 0);
      return apiPostJson(
        '/api/recipe/remove',
        {index: validated},
        parseStepListEnvelope,
        signal,
      );
    },
    duplicateStep(index: number, signal?: AbortSignal): Promise<StepView[]> {
      const validated = requireRequestInteger(index, 'request.index', 0);
      return apiPostJson(
        '/api/recipe/duplicate',
        {index: validated},
        parseStepListEnvelope,
        signal,
      );
    },
    moveStep(index: number, direction: 'up' | 'down', signal?: AbortSignal): Promise<StepView[]> {
      const validated = requireRequestInteger(index, 'request.index', 0);
      return apiPostJson(
        '/api/recipe/move',
        {index: validated, direction},
        parseStepListEnvelope,
        signal,
      );
    },
    renameStep(index: number, instanceName: string, signal?: AbortSignal): Promise<StepView> {
      const validated = requireRequestInteger(index, 'request.index', 0);
      return apiPostJson(
        '/api/recipe/rename-step',
        {index: validated, instance_name: instanceName},
        (payload: unknown) => parseStepEnvelope(payload, validated),
        signal,
      );
    },
    getTimeline(signal?: AbortSignal): Promise<TimelineView> {
      return apiPostJson('/api/timeline/get', {}, parseTimelineEnvelope, signal);
    },
    restoreTimeline(index: number, signal?: AbortSignal): Promise<TimelineRestoreView> {
      const validatedIndex = requireRequestInteger(index, 'request.index', 0);
      return apiPostJson(
        '/api/timeline/restore',
        {index: validatedIndex},
        parseTimelineRestoreEnvelope,
        signal,
      );
    },
    getPreviewManifest(
      request: PreviewManifestRequest = {},
      signal?: AbortSignal,
    ): Promise<PreviewManifestView> {
      return apiGetJson(previewManifestPath(request), parsePreviewManifestEnvelope, signal);
    },
    getMaterialStl(request: PreviewStlRequest, signal?: AbortSignal): Promise<ArrayBuffer> {
      return apiBinary(previewStlPath(request), signal);
    },
  };
}

export const tcadApi: TcadApi = createTcadApi();
export type {TcadApi} from './types';
