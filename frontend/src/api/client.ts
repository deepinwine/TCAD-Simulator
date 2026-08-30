import {
  parseInitEnvelope,
  parsePreviewManifestEnvelope,
  parseRunEnvelope,
  parseSetStepEnvelope,
  parseTimelineEnvelope,
  parseTimelineRestoreEnvelope,
} from './schemas';
import type {
  InitView,
  PreviewManifestRequest,
  PreviewManifestView,
  PreviewStlRequest,
  RunView,
  SetStepRequest,
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
  const fields: Array<[string, string]> = [
    ['step_index', 'stepIndex'],
    ['instance_name', 'instanceName'],
    ['step_type', 'stepType'],
    ['rollback_error', 'rollbackError'],
  ];
  const details: Record<string, unknown> = {};
  for (const [wireName, clientName] of fields) {
    if (source[wireName] !== undefined) details[clientName] = source[wireName];
  }
  return Object.keys(details).length > 0 ? details : undefined;
}

function toApiError(status: number, payload: unknown): TcadApiError {
  const source = isRecord(payload) ? payload : {};
  const explicitDetails = source.details;
  const stepDetails = flatStepDetails(source);
  let details = explicitDetails;
  if (stepDetails !== undefined) {
    details = isRecord(explicitDetails) ? {...explicitDetails, ...stepDetails} : stepDetails;
  }
  const message = stringField(source, 'error')
    ?? stringField(source, 'message')
    ?? `TCAD 请求失败（HTTP ${status}）。`;
  return new TcadApiError(message, {
    status,
    code: stringField(source, 'code'),
    errorType: stringField(source, 'error_type'),
    parameterPath: stringField(source, 'parameter_path'),
    suggestion: stringField(source, 'suggestion'),
    rolledBack: booleanField(source, 'rolled_back'),
    details,
    causeValue: payload,
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
  if (response.ok) {
    return response.arrayBuffer();
  }
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
  if (contentType.includes('json')) {
    const payload = await readJsonSafely(response);
    throw toApiError(response.status, payload);
  }
  throw new TcadApiError(`二进制资源请求失败（HTTP ${response.status}）。`, {
    status: response.status,
    code: 'binary_request_failed',
  });
}

function previewManifestPath(request: PreviewManifestRequest): string {
  const query = new URLSearchParams();
  if (request.mode !== undefined) query.set('mode', request.mode);
  if (request.faceLimit !== undefined) query.set('face_limit', String(request.faceLimit));
  const suffix = query.toString();
  return suffix ? `/api/preview/manifest?${suffix}` : '/api/preview/manifest';
}

function previewStlPath(request: PreviewStlRequest): string {
  const query = new URLSearchParams({
    mat_id: String(request.materialId),
    rev: String(request.revision),
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
      return apiPostJson(
        '/api/step/set',
        {
          index: request.index,
          ...(request.enabled !== undefined ? {enabled: request.enabled} : {}),
          ...(request.params !== undefined ? {params: request.params} : {}),
          ...(request.loop !== undefined ? {loop: request.loop} : {}),
          ...(request.group !== undefined ? {group: request.group} : {}),
          ...(request.noAutosave !== undefined ? {no_autosave: request.noAutosave} : {}),
        },
        payload => parseSetStepEnvelope(payload, request.index),
        signal,
      );
    },
    runStep(index: number, signal?: AbortSignal): Promise<RunView> {
      return apiPostJson('/api/run/step', {index}, parseRunEnvelope, signal);
    },
    runTo(index: number, signal?: AbortSignal): Promise<RunView> {
      return apiPostJson('/api/run/to', {index}, parseRunEnvelope, signal);
    },
    runAll(signal?: AbortSignal): Promise<RunView> {
      return apiPostJson('/api/run/all', {}, parseRunEnvelope, signal);
    },
    getTimeline(signal?: AbortSignal): Promise<TimelineView> {
      return apiPostJson('/api/timeline/get', {}, parseTimelineEnvelope, signal);
    },
    restoreTimeline(index: number, signal?: AbortSignal): Promise<TimelineRestoreView> {
      return apiPostJson('/api/timeline/restore', {index}, parseTimelineRestoreEnvelope, signal);
    },
    getPreviewManifest(
      request: PreviewManifestRequest = {},
      signal?: AbortSignal,
    ): Promise<PreviewManifestView> {
      return apiGetJson(previewManifestPath(request), parsePreviewManifestEnvelope, signal);
    },
    getPreviewStl(request: PreviewStlRequest, signal?: AbortSignal): Promise<ArrayBuffer> {
      return apiBinary(previewStlPath(request), signal);
    },
  };
}

export const tcadApi: TcadApi = createTcadApi();
export type {TcadApi} from './types';
