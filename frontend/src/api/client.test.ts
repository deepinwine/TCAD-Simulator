import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  TcadApiError,
  apiBinary,
  apiGetJson,
  apiPostJson,
  createTcadApi,
} from './client';

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
      causeValue: payload,
    });
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
  it('为冻结端点生成明确的方法、payload 和 STL query', async () => {
    const manifest = {
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(manifest))
      .mockResolvedValueOnce(new Response(new Uint8Array([9]), {status: 200}));
    vi.stubGlobal('fetch', fetchMock);
    const api = createTcadApi();

    const parsed = await api.getPreviewManifest({mode: 'solid', faceLimit: 2000});
    const binary = await api.getPreviewStl({materialId: 2, revision: parsed.revision, mode: 'solid'});

    expect(fetchMock.mock.calls[0][0]).toBe('/api/preview/manifest?mode=solid&face_limit=2000');
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty('body');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/preview/stl?mat_id=2&rev=4&mode=solid');
    expect([...new Uint8Array(binary)]).toEqual([9]);
  });
});
