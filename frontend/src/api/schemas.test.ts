import {describe, expect, it} from 'vitest';

import {
  ApiContractError,
  parseInitEnvelope,
  parsePreviewManifestEnvelope,
  parseRunEnvelope,
  parseSetStepEnvelope,
  parseTimelineEnvelope,
  parseTimelineRestoreEnvelope,
} from './schemas';

const validStep = {
  name: 'Initialize Wafer',
  instance_name: 'Substrate',
  enabled: true,
  params: {material: 'Silicon'},
  parameter_specs: [
    {
      key: 'material',
      label: 'Material',
      type: 'enum',
      default: 'Silicon',
      choices: [['Silicon', 'Silicon']],
    },
  ],
  runtime_status: 'ready',
};

const validInit = {
  ok: true,
  result: {
    recipe: [validStep],
    model: {
      grid_shape: [64, 64, 96],
      voxel_size_nm: 10,
      threads: 4,
      metrics: [['Max height (nm)', '200.0'], ['Silicon volume (µm³)', '1.25']],
    },
    recipe_factories: ['Initialize Wafer'],
    materials: [{id: 1, name: 'Silicon', color: [0.6, 0.6, 0.65], enabled: true}],
    ui_state: {selected: 0},
  },
};

describe('parseInitEnvelope', () => {
  it('接受 additive 字段并明确映射 snake_case', () => {
    const parsed = parseInitEnvelope({
      ...validInit,
      server_added: 1,
      result: {...validInit.result, server_added: {future: true}},
    });

    expect(parsed.recipe[0]).toMatchObject({
      index: 0,
      instanceName: 'Substrate',
      runtimeStatus: 'ready',
    });
    expect(parsed.recipe[0].parameterSpecs[0]).toMatchObject({
      defaultValue: 'Silicon',
      choices: [['Silicon', 'Silicon']],
    });
    expect(parsed.model).toMatchObject({gridShape: [64, 64, 96], voxelSizeNm: 10, threads: 4});
    expect(parsed.uiState).toEqual({selected: 0});
    expect(parsed.model).not.toHaveProperty('revision');
  });

  it('缺少必要容器时报告精确 JSON path', () => {
    expect(() => parseInitEnvelope({ok: true, result: {model: {}}})).toThrow(
      'result.recipe',
    );
  });

  it('未知 runtime_status 回退 ready', () => {
    const parsed = parseInitEnvelope({
      ...validInit,
      result: {...validInit.result, recipe: [{...validStep, runtime_status: 'future-state'}]},
    });

    expect(parsed.recipe[0].runtimeStatus).toBe('ready');
  });

  it('拒绝非有限数值和错误 tuple', () => {
    const invalidGrid = {
      ...validInit,
      result: {...validInit.result, model: {...validInit.result.model, grid_shape: [64, Infinity, 96]}},
    };
    expect(() => parseInitEnvelope(invalidGrid)).toThrow('result.model.grid_shape[1]');

    const invalidChoice = {
      ...validInit,
      result: {
        ...validInit.result,
        recipe: [{
          ...validStep,
          parameter_specs: [{...validStep.parameter_specs[0], choices: [['Silicon']]}],
        }],
      },
    };
    expect(() => parseInitEnvelope(invalidChoice)).toThrow(
      'result.recipe[0].parameter_specs[0].choices[0]',
    );
  });
});

describe('mutation and timeline schemas', () => {
  it('解析 set_step 的权威 step 与 statuses', () => {
    const parsed = parseSetStepEnvelope(
      {ok: true, result: {...validStep, runtime_status: 'dirty'}, statuses: ['done', 'dirty']},
      1,
    );

    expect(parsed.step.index).toBe(1);
    expect(parsed.step.runtimeStatus).toBe('dirty');
    expect(parsed.statuses).toEqual(['done', 'dirty']);
  });

  it('解析 run 响应但不要求 disabled step 返回模型', () => {
    expect(parseRunEnvelope({ok: true, result: {skipped: true, reason: 'disabled'}})).toEqual({
      skipped: true,
      reason: 'disabled',
    });
    expect(parseRunEnvelope({ok: true, result: {model_revision: 7}}).modelRevision).toBe(7);
  });

  it('run 和 timeline restore 容忍客户端未读取的真实 metrics 二维数组', () => {
    const model = validInit.result.model;
    expect(parseRunEnvelope({ok: true, result: {model}}).model).toMatchObject({
      gridShape: [64, 64, 96],
      voxelSizeNm: 10,
    });

    const restored = parseTimelineRestoreEnvelope({
      ok: true,
      result: {
        timeline: {
          items: [{index: 0, state: 'current', runtime_status: 'done', snapshot_valid: true}],
          current: 0,
        },
        model,
        recipe: [validStep],
        log: ['restored'],
      },
    });
    expect(restored.model).not.toHaveProperty('metrics');
    expect(restored.recipe[0].index).toBe(0);
  });

  it('解析 Timeline 并校验 snapshot_valid', () => {
    const parsed = parseTimelineEnvelope({
      ok: true,
      result: {
        items: [{index: 0, state: 'current', runtime_status: 'done', snapshot_valid: true}],
        current: 0,
      },
    });
    expect(parsed).toEqual({
      items: [{index: 0, state: 'current', runtimeStatus: 'done', snapshotValid: true}],
      current: 0,
    });

    expect(() => parseTimelineEnvelope({
      ok: true,
      result: {items: [{index: 0, state: 'done', runtime_status: 'done'}], current: 0},
    })).toThrow('result.items[0].snapshot_valid');
  });
});

describe('parsePreviewManifestEnvelope', () => {
  const validManifest = {
    ok: true,
    result: {
      rev: 12,
      mode: 'solid',
      meshes: [{
        mat_id: 7,
        name: 'Copper',
        tri_count: 24,
        bbox: {min: [0, 0, 0], max: [1, 2, 3]},
        visual: {
          material_id: 7,
          display_name: 'Copper',
          color: [0.72, 0.45, 0.2],
          opacity: 1,
          metallic: 0.7,
          roughness: 0.25,
          visible: true,
        },
      }],
    },
  };

  it('只从 manifest rev 建立 revision 并校验 mesh/visual', () => {
    const parsed = parsePreviewManifestEnvelope(validManifest);

    expect(parsed.revision).toBe(12);
    expect(parsed.meshes[0]).toMatchObject({
      materialId: 7,
      triangleCount: 24,
      boundingBox: {min: [0, 0, 0], max: [1, 2, 3]},
      visual: {materialId: 7, displayName: 'Copper', visible: true},
    });
  });

  it('拒绝越界颜色和非有限 bbox', () => {
    const invalidColor = structuredClone(validManifest);
    invalidColor.result.meshes[0].visual.color[1] = 1.2;
    expect(() => parsePreviewManifestEnvelope(invalidColor)).toThrow(
      'result.meshes[0].visual.color[1]',
    );

    const invalidBox = structuredClone(validManifest);
    invalidBox.result.meshes[0].bbox.max[2] = Infinity;
    expect(() => parsePreviewManifestEnvelope(invalidBox)).toThrow(
      'result.meshes[0].bbox.max[2]',
    );
  });

  it('抛出的契约错误保留 path', () => {
    try {
      parsePreviewManifestEnvelope({ok: true, result: {rev: 1}});
      throw new Error('expected parser to throw');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiContractError);
      expect((error as ApiContractError).path).toBe('result.meshes');
    }
  });
});
