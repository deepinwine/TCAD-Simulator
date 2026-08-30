import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  TcadApiError,
  apiBinary,
  apiGetJson,
  apiPostJson,
  createTcadApi,
} from './client';
import {ApiContractError} from './schemas';

const wireStep = {
  name: 'Initialize Wafer',
  instance_name: 'Substrate',
  enabled: true,
  params: {material: 'Silicon'},
  parameter_specs: [],
  runtime_status: 'ready',
};

const wireModel = {
  grid_shape: [64, 64, 96],
  voxel_size_nm: 10,
  threads: 4,
  metrics: [['Max height (nm)', '200.0']],
};

const initEnvelope = {
  ok: true,
  result: {
    recipe: [wireStep],
    model: wireModel,
    recipe_factories: ['Initialize Wafer'],
    materials: [{id: 1, name: 'Silicon', color: [0.6, 0.6, 0.65], enabled: true}],
    ui_state: {},
  },
};

const timelineResult = {
  items: [{index: 0, state: 'current', runtime_status: 'done', snapshot_valid: true}],
  current: 0,
};

const manifestEnvelope = {
  ok: true,
  result: {
    rev: 4,
    mode: 'solid',
    meshes: [{
      mat_id: 2,
      name: 'Silicon',
      tri_count: 1,
      bbox: {min: [0, 0, 0], max: [1, 1, 1]},
      visual: {
        material_id: 2,
        display_name: 'Silicon',
        color: [0.6, 0.6, 0.65],
        opacity: 1,
        metallic: 0,
        roughness: 0.72,
        visible: true,
      },
    }],
  },
};

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    statusText: init.statusText,
    headers: {'content-type': 'application/json', ...init.headers},
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('JSON client boundary', () => {
  it('HTTP 200 + ok:false 仍映射为完整 TcadApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      ok: false,
      code: 'no_valid_snapshot',
      error: '没有有效快照',
      error_type: 'SnapshotError',
      parameter_path: 'timeline.index',
      suggestion: '先执行步骤',
      rolled_back: false,
      details: {index: 4},
    })));

    await expect(apiPostJson('/api/timeline/restore', {index: 4}, value => value)).rejects
      .toMatchObject({
        name: 'TcadApiError',
        status: 200,
        code: 'no_valid_snapshot',
        message: '没有有效快照',
        errorType: 'SnapshotError',
        parameterPath: 'timeline.index',
        suggestion: '先执行步骤',
        rolledBack: false,
        details: {index: 4},
      });
  });

  it('run/step 平面失败载荷完整映射', async () => {
    const payload = {
      ok: false,
      step_index: 2,
      instance_name: 'Metal Etch',
      step_type: 'Etch',
      error: 'time must be positive',
      error_type: 'ValueError',
      parameter_path: 'params.time',
      suggestion: 'Review the step parameters and retry.',
      rolled_back: true,
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(payload)));

    await expect(createTcadApi().runStep(2)).rejects.toMatchObject({
      status: 200,
      message: 'time must be positive',
      errorType: 'ValueError',
      parameterPath: 'params.time',
      suggestion: 'Review the step parameters and retry.',
      rolledBack: true,
      details: {
        stepIndex: 2,
        instanceName: 'Metal Etch',
        stepType: 'Etch',
      },
      causeValue: {kind: 'server_error', status: 200},
    });
  });

  it('未知服务端字段和敏感 details 不会通过 error 对象泄露', async () => {
    const payload = {
      ok: false,
      code: 'failed',
      error: '请求失败',
      internal_path: '/Users/private/recipe.json',
      api_key: 'sk-secret-value',
      step_index: {api_key: 'flat-secret'},
      details: {index: 4, api_key: 'nested-secret', internal_path: '/private/file'},
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(payload, {status: 500})));

    let error: unknown;
    try {
      await apiPostJson('/api/run/step', {index: 4}, value => value);
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(TcadApiError);
    expect(error).toMatchObject({
      details: {index: 4},
      causeValue: {kind: 'server_error', status: 500, code: 'failed'},
    });
    expect(JSON.stringify(error)).not.toMatch(
      /sk-secret|private\/recipe|nested-secret|private\/file|flat-secret/,
    );
    expect((error as TcadApiError).causeValue).not.toBe(payload);
  });

  it('GET 固定 same-origin 且不发送 body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ok: true, result: {value: 1}}));
    vi.stubGlobal('fetch', fetchMock);

    await apiGetJson('/api/example', payload => payload);

    expect(fetchMock).toHaveBeenCalledWith('/api/example', {
      method: 'GET',
      credentials: 'same-origin',
      signal: undefined,
    });
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty('body');
  });

  it('POST 固定 same-origin、JSON.stringify 和 Content-Type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ok: true, result: {value: 1}}));
    vi.stubGlobal('fetch', fetchMock);

    await apiPostJson('/api/example', {index: 3}, payload => payload);

    expect(fetchMock).toHaveBeenCalledWith('/api/example', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({index: 3}),
      signal: undefined,
    });
  });

  it('AbortError 原样抛出', async () => {
    const aborted = new DOMException('The operation was aborted.', 'AbortError');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(aborted));

    let received: unknown;
    try {
      await apiGetJson('/api/init', payload => payload);
    } catch (error) {
      received = error;
    }
    expect(received).toBe(aborted);
  });

  it('读取 JSON body 期间的 AbortError 也原样抛出', async () => {
    const aborted = new DOMException('The operation was aborted.', 'AbortError');
    const response = {
      ok: true,
      status: 200,
      json: vi.fn().mockRejectedValue(aborted),
    } as unknown as Response;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    let received: unknown;
    try {
      await apiGetJson('/api/init', payload => payload);
    } catch (error) {
      received = error;
    }
    expect(received).toBe(aborted);
  });

  it('网络和 JSON 解析失败使用稳定消息且不泄露底层内容', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('secret-token=/private/path')));
    await expect(apiGetJson('/api/init', payload => payload)).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
      message: '无法连接 TCAD 服务。',
      causeValue: undefined,
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('secret-token=/private/path', {
      status: 200,
      headers: {'content-type': 'application/json'},
    })));
    let error: unknown;
    try {
      await apiGetJson('/api/init', payload => payload);
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(TcadApiError);
    expect((error as Error).message).toBe('TCAD 服务返回了无效 JSON。');
    expect(JSON.stringify(error)).not.toContain('secret-token');
  });
});

describe('binary client boundary', () => {
  it('成功返回 ArrayBuffer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2, 3]), {
      status: 200,
      headers: {'content-type': 'application/sla'},
    })));

    const result = await apiBinary('/api/preview/stl?mat_id=1&rev=2&mode=solid');
    expect([...new Uint8Array(result)]).toEqual([1, 2, 3]);
  });

  it('JSON 错误不会被当成 STL', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(
      {ok: false, code: 'missing_mesh', error: 'Preview geometry not found'},
      {status: 404},
    )));

    await expect(apiBinary('/api/preview/stl')).rejects.toMatchObject({
      status: 404,
      code: 'missing_mesh',
      message: 'Preview geometry not found',
    });
  });

  it('HTTP 200 JSON ok:false 仍按结构化错误处理', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(
      {ok: false, code: 'stale_revision', error: 'Preview revision is stale'},
      {headers: {'Content-Type': 'Application/JSON; Charset=UTF-8'}},
    )));

    await expect(apiBinary('/api/preview/stl')).rejects.toMatchObject({
      status: 200,
      code: 'stale_revision',
      message: 'Preview revision is stale',
    });
  });

  it('HTTP 200 JSON ok:true 作为错误的响应类别拒绝', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ok: true, result: {}})));

    await expect(apiBinary('/api/preview/stl')).rejects.toMatchObject({
      status: 200,
      code: 'unexpected_json_response',
      message: '期望二进制资源，但 TCAD 服务返回了 JSON。',
    });
  });

  it('binary body 读取保留 AbortError，其他失败使用安全错误', async () => {
    const aborted = new DOMException('The operation was aborted.', 'AbortError');
    const abortResponse = {
      ok: true,
      status: 200,
      headers: new Headers({'content-type': 'application/sla'}),
      arrayBuffer: vi.fn().mockRejectedValue(aborted),
    } as unknown as Response;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(abortResponse));
    let received: unknown;
    try {
      await apiBinary('/api/preview/stl');
    } catch (error) {
      received = error;
    }
    expect(received).toBe(aborted);

    const failedResponse = {
      ok: true,
      status: 200,
      headers: new Headers({'content-type': 'application/sla'}),
      arrayBuffer: vi.fn().mockRejectedValue(new Error('secret=/private/mesh.stl')),
    } as unknown as Response;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failedResponse));
    await expect(apiBinary('/api/preview/stl')).rejects.toMatchObject({
      status: 200,
      code: 'binary_read_failed',
      message: '无法读取 TCAD 二进制资源。',
      causeValue: undefined,
    });
  });

  it('非 JSON 错误使用安全稳定消息', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('server-path=/private/export', {
      status: 502,
      statusText: 'secret upstream',
      headers: {'content-type': 'text/plain'},
    })));

    await expect(apiBinary('/api/preview/stl')).rejects.toMatchObject({
      status: 502,
      code: 'binary_request_failed',
      message: '二进制资源请求失败（HTTP 502）。',
      causeValue: undefined,
    });
  });
});

describe('TcadApi endpoint methods', () => {
  const cases = [
    {
      name: 'init',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.init(),
      response: () => jsonResponse(initEnvelope),
      path: '/api/init',
      method: 'GET',
    },
    {
      name: 'setStep',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.setStep({
        index: 0, params: {material: 'Silicon'}, noAutosave: true,
      }),
      response: () => jsonResponse({ok: true, result: wireStep, statuses: ['dirty']}),
      path: '/api/step/set',
      method: 'POST',
      body: {index: 0, params: {material: 'Silicon'}, no_autosave: true},
    },
    {
      name: 'runStep',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.runStep(2),
      response: () => jsonResponse({ok: true, result: {model: wireModel}}),
      path: '/api/run/step',
      method: 'POST',
      body: {index: 2},
    },
    {
      name: 'runTo',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.runTo(3),
      response: () => jsonResponse({ok: true, result: {model: wireModel, index: 3}}),
      path: '/api/run/to',
      method: 'POST',
      body: {index: 3},
    },
    {
      name: 'runAll',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.runAll(),
      response: () => jsonResponse({ok: true, result: {model: wireModel}}),
      path: '/api/run/all',
      method: 'POST',
      body: {},
    },
    {
      name: 'getTimeline',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.getTimeline(),
      response: () => jsonResponse({ok: true, result: timelineResult}),
      path: '/api/timeline/get',
      method: 'POST',
      body: {},
    },
    {
      name: 'restoreTimeline',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.restoreTimeline(0),
      response: () => jsonResponse({
        ok: true,
        result: {timeline: timelineResult, model: wireModel, recipe: [wireStep], log: []},
      }),
      path: '/api/timeline/restore',
      method: 'POST',
      body: {index: 0},
    },
    {
      name: 'getPreviewManifest',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.getPreviewManifest({
        mode: 'solid', faceLimit: 2000,
      }),
      response: () => jsonResponse(manifestEnvelope),
      path: '/api/preview/manifest?mode=solid&face_limit=2000',
      method: 'GET',
    },
    {
      name: 'getMaterialStl',
      invoke: (api: ReturnType<typeof createTcadApi>) => api.getMaterialStl({
        materialId: 2, revision: 4, mode: 'solid',
      }),
      response: () => new Response(new Uint8Array([9]), {
        status: 200, headers: {'content-type': 'application/sla'},
      }),
      path: '/api/preview/stl?mat_id=2&rev=4&mode=solid',
      method: 'GET',
    },
  ];

  it.each(cases)('$name 固化 method/path/payload', async testCase => {
    const fetchMock = vi.fn().mockResolvedValue(testCase.response());
    vi.stubGlobal('fetch', fetchMock);

    await testCase.invoke(createTcadApi());

    const [path, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(testCase.path);
    expect(request).toMatchObject({method: testCase.method, credentials: 'same-origin'});
    if (testCase.method === 'GET') {
      expect(request).not.toHaveProperty('body');
    } else {
      expect(request.headers).toEqual({'Content-Type': 'application/json'});
      expect(request.body).toBe(JSON.stringify(testCase.body));
    }
  });

  const invalidIntegerCases: Array<[
    string,
    (api: ReturnType<typeof createTcadApi>) => Promise<unknown>,
  ]> = [
    ['setStep.index', (api: ReturnType<typeof createTcadApi>) => api.setStep({index: NaN})],
    ['runStep.index', (api: ReturnType<typeof createTcadApi>) => api.runStep(Infinity)],
    ['runTo.index', (api: ReturnType<typeof createTcadApi>) => api.runTo(-1)],
    ['restoreTimeline.index', (api: ReturnType<typeof createTcadApi>) => api.restoreTimeline(1.5)],
    ['manifest.faceLimit', (api: ReturnType<typeof createTcadApi>) => api.getPreviewManifest({faceLimit: NaN})],
    ['stl.materialId', (api: ReturnType<typeof createTcadApi>) => api.getMaterialStl({materialId: 0, revision: 1})],
    ['stl.revision', (api: ReturnType<typeof createTcadApi>) => api.getMaterialStl({materialId: 1, revision: -1})],
  ];

  it.each(invalidIntegerCases)('%s 在 fetch 前拒绝非法整数', async (_label, invoke) => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ok: true, result: {}}));
    vi.stubGlobal('fetch', fetchMock);

    await expect(Promise.resolve().then(() => invoke(createTcadApi())))
      .rejects.toBeInstanceOf(ApiContractError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
