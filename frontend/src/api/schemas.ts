import type {
  BoundingBoxView,
  HistoryView,
  InitView,
  RecipeLoadView,
  MaterialView,
  MaterialVisualView,
  ModelSummaryView,
  ParameterChoice,
  ParameterChoiceValue,
  ParameterSpecView,
  PreviewManifestView,
  PreviewMeshView,
  RgbColor,
  RunView,
  RuntimeStatus,
  SetStepView,
  StepView,
  TimelineRestoreView,
  TimelineView,
  Vec3,
} from './types';

export class ApiContractError extends Error {
  constructor(
    readonly path: string,
    expected: string,
  ) {
    super(`API contract violation at ${path}: expected ${expected}`);
    this.name = 'ApiContractError';
  }
}

const runtimeStatuses = new Set<RuntimeStatus>(['ready', 'dirty', 'running', 'done', 'error']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new ApiContractError(path, 'object');
  }
  return value;
}

function requireArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new ApiContractError(path, 'array');
  }
  return value;
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== 'string') {
    throw new ApiContractError(path, 'string');
  }
  return value;
}

function optionalString(value: unknown, path: string): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  return requireString(value, path);
}

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') {
    throw new ApiContractError(path, 'boolean');
  }
  return value;
}

function requireFiniteNumber(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ApiContractError(path, 'finite number');
  }
  return value;
}

function optionalFiniteNumber(value: unknown, path: string): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  return requireFiniteNumber(value, path);
}

function requireInteger(value: unknown, path: string, minimum?: number): number {
  const number = requireFiniteNumber(value, path);
  if (!Number.isInteger(number) || (minimum !== undefined && number < minimum)) {
    throw new ApiContractError(path, minimum === undefined ? 'integer' : `integer >= ${minimum}`);
  }
  return number;
}

function optionalInteger(value: unknown, path: string, minimum?: number): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  return requireInteger(value, path, minimum);
}

function requireTuple3(value: unknown, path: string): Vec3 {
  const items = requireArray(value, path);
  if (items.length !== 3) {
    throw new ApiContractError(path, 'tuple with exactly 3 finite numbers');
  }
  return [
    requireFiniteNumber(items[0], `${path}[0]`),
    requireFiniteNumber(items[1], `${path}[1]`),
    requireFiniteNumber(items[2], `${path}[2]`),
  ];
}

function requirePositiveIntegerTuple3(value: unknown, path: string): Vec3 {
  const items = requireArray(value, path);
  if (items.length !== 3) {
    throw new ApiContractError(path, 'tuple with exactly 3 positive integers');
  }
  return [
    requireInteger(items[0], `${path}[0]`, 1),
    requireInteger(items[1], `${path}[1]`, 1),
    requireInteger(items[2], `${path}[2]`, 1),
  ];
}

function requireUnitInterval(value: unknown, path: string): number {
  const number = requireFiniteNumber(value, path);
  if (number < 0 || number > 1) {
    throw new ApiContractError(path, 'number in [0, 1]');
  }
  return number;
}

function requireColor(value: unknown, path: string): RgbColor {
  const items = requireArray(value, path);
  if (items.length !== 3) {
    throw new ApiContractError(path, 'RGB tuple with exactly 3 numbers');
  }
  return [
    requireUnitInterval(items[0], `${path}[0]`),
    requireUnitInterval(items[1], `${path}[1]`),
    requireUnitInterval(items[2], `${path}[2]`),
  ];
}

function parseRuntimeStatus(value: unknown): RuntimeStatus {
  // M2 compatibility 边界约定：未知的增量状态安全回退为 ready。
  return typeof value === 'string' && runtimeStatuses.has(value as RuntimeStatus)
    ? value as RuntimeStatus
    : 'ready';
}

function requireOkResult(payload: unknown): Record<string, unknown> {
  const envelope = requireRecord(payload, '$');
  if (envelope.ok !== true) {
    throw new ApiContractError('ok', 'true');
  }
  return requireRecord(envelope.result, 'result');
}

function parseChoiceValue(value: unknown, path: string): ParameterChoiceValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  throw new ApiContractError(path, 'JSON primitive choice value');
}

function parseChoices(value: unknown, path: string): ParameterChoice[] | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  return requireArray(value, path).map((choice, index) => {
    const choicePath = `${path}[${index}]`;
    const pair = requireArray(choice, choicePath);
    if (pair.length !== 2) {
      throw new ApiContractError(choicePath, '[value, label] tuple');
    }
    return [
      parseChoiceValue(pair[0], `${choicePath}[0]`),
      requireString(pair[1], `${choicePath}[1]`),
    ];
  });
}

function parseParameterSpec(value: unknown, path: string): ParameterSpecView {
  const source = requireRecord(value, path);
  const parsed: ParameterSpecView = {
    key: requireString(source.key, `${path}.key`),
    label: requireString(source.label, `${path}.label`),
    type: requireString(source.type, `${path}.type`),
  };
  if (Object.hasOwn(source, 'default')) {
    parsed.defaultValue = source.default;
  }
  const minimum = optionalFiniteNumber(source.minimum, `${path}.minimum`);
  const maximum = optionalFiniteNumber(source.maximum, `${path}.maximum`);
  const choices = parseChoices(source.choices, `${path}.choices`);
  const decimals = optionalInteger(source.decimals, `${path}.decimals`, 0);
  const step = optionalFiniteNumber(source.step, `${path}.step`);
  const units = optionalString(source.units, `${path}.units`);
  const tooltip = optionalString(source.tooltip, `${path}.tooltip`);
  if (minimum !== undefined) parsed.minimum = minimum;
  if (maximum !== undefined) parsed.maximum = maximum;
  if (choices !== undefined) parsed.choices = choices;
  if (decimals !== undefined) parsed.decimals = decimals;
  if (step !== undefined) parsed.step = step;
  if (units !== undefined) parsed.units = units;
  if (tooltip !== undefined) parsed.tooltip = tooltip;
  return parsed;
}

function parseStep(value: unknown, path: string, index: number): StepView {
  const source = requireRecord(value, path);
  return {
    index,
    name: requireString(source.name, `${path}.name`),
    instanceName: requireString(source.instance_name, `${path}.instance_name`),
    group: optionalString(source.group, `${path}.group`) ?? '',
    loop: optionalString(source.loop, `${path}.loop`) ?? '',
    enabled: requireBoolean(source.enabled, `${path}.enabled`),
    params: requireRecord(source.params, `${path}.params`),
    parameterSpecs: requireArray(source.parameter_specs, `${path}.parameter_specs`).map(
      (spec, specIndex) => parseParameterSpec(spec, `${path}.parameter_specs[${specIndex}]`),
    ),
    runtimeStatus: parseRuntimeStatus(source.runtime_status),
  };
}

function parseRecipe(value: unknown, path: string): StepView[] {
  return requireArray(value, path).map((step, index) => parseStep(step, `${path}[${index}]`, index));
}

function parseModel(value: unknown, path: string): ModelSummaryView {
  const source = requireRecord(value, path);
  const voxelSizeNm = requireFiniteNumber(source.voxel_size_nm, `${path}.voxel_size_nm`);
  if (voxelSizeNm <= 0) {
    throw new ApiContractError(`${path}.voxel_size_nm`, 'positive finite number');
  }
  const parsed: ModelSummaryView = {
    gridShape: requirePositiveIntegerTuple3(source.grid_shape, `${path}.grid_shape`),
    voxelSizeNm,
  };
  const threads = optionalInteger(source.threads, `${path}.threads`, 1);
  const substrateMaterial = optionalString(source.substrate_material, `${path}.substrate_material`);
  const substrateThicknessNm = optionalFiniteNumber(
    source.substrate_thickness_nm,
    `${path}.substrate_thickness_nm`,
  );
  if (threads !== undefined) parsed.threads = threads;
  if (substrateMaterial !== undefined) parsed.substrateMaterial = substrateMaterial;
  if (substrateThicknessNm !== undefined) parsed.substrateThicknessNm = substrateThicknessNm;
  return parsed;
}

function parseMaterial(value: unknown, path: string): MaterialView {
  const source = requireRecord(value, path);
  return {
    id: requireInteger(source.id, `${path}.id`, 0),
    name: requireString(source.name, `${path}.name`),
    color: requireColor(source.color, `${path}.color`),
    enabled: requireBoolean(source.enabled, `${path}.enabled`),
  };
}

function parseStringArray(value: unknown, path: string): string[] {
  return requireArray(value, path).map((item, index) => requireString(item, `${path}[${index}]`));
}

export function parseInitEnvelope(payload: unknown): InitView {
  const result = requireOkResult(payload);
  const view: InitView = {
    recipe: parseRecipe(result.recipe, 'result.recipe'),
    model: parseModel(result.model, 'result.model'),
    factories: parseStringArray(result.recipe_factories, 'result.recipe_factories'),
    materials: requireArray(result.materials, 'result.materials').map(
      (material, index) => parseMaterial(material, `result.materials[${index}]`),
    ),
    uiState: requireRecord(result.ui_state, 'result.ui_state'),
  };
  if (result.demo_recipes !== undefined) {
    const source = requireRecord(result.demo_recipes, 'result.demo_recipes');
    const demos: Record<string, import('./types').DemoRecipeView> = {};
    for (const [key, value] of Object.entries(source)) {
      demos[key] = requireRecord(value, `result.demo_recipes.${key}`) as never;
    }
    view.demoRecipes = demos;
  }
  if (result.current_recipe !== undefined) {
    view.currentRecipe = parseCurrentRecipe(result.current_recipe);
  }
  return view;
}

export function parseSetStepEnvelope(payload: unknown, index: number): SetStepView {
  const envelope = requireRecord(payload, '$');
  if (envelope.ok !== true) {
    throw new ApiContractError('ok', 'true');
  }
  return {
    step: parseStep(envelope.result, 'result', index),
    statuses: requireArray(envelope.statuses, 'statuses').map(item => parseRuntimeStatus(item)),
    warnings: envelope.warnings === undefined
      ? []
      : parseStringArray(envelope.warnings, 'warnings'),
  };
}

export function parseRecipeLoadEnvelope(
  payload: unknown,
  flagField: 'imported' | 'loaded' | null,
): RecipeLoadView {
  const result = requireOkResult(payload);
  if (flagField !== null && result[flagField] !== undefined) {
    requireBoolean(result[flagField], `result.${flagField}`);
  }
  return {
    model: parseModel(result.model, 'result.model'),
    recipe: parseRecipe(result.recipe, 'result.recipe'),
    currentRecipe: parseCurrentRecipe(result.current_recipe),
    log: result.log === undefined ? [] : parseStringArray(result.log, 'result.log'),
  };
}

function parseCurrentRecipe(value: unknown): {name: string; id: string} {
  const source = requireRecord(value, 'result.current_recipe');
  return {
    name: requireString(source.name, 'result.current_recipe.name'),
    id: requireString(source.id ?? '', 'result.current_recipe.id'),
  };
}

export function parseMaskUploadEnvelope(payload: unknown, index: number): SetStepView {
  // 外层 {ok, path, result:<set_step 封套>}；嵌套 result 才是步骤更新载荷
  const envelope = requireRecord(payload, '$');
  if (envelope.ok !== true) {
    throw new ApiContractError('ok', 'true');
  }
  return parseSetStepEnvelope(envelope.result, index);
}

export function parseStepListEnvelope(payload: unknown): StepView[] {
  // 结构编辑端点的 result 本身就是步骤数组（不是对象），不能走 requireOkResult
  const envelope = requireRecord(payload, '$');
  if (envelope.ok !== true) {
    throw new ApiContractError('ok', 'true');
  }
  return parseRecipe(envelope.result, 'result');
}

export function parseStepEnvelope(payload: unknown, index: number): StepView {
  const result = requireOkResult(payload);
  return parseStep(result, 'result', index);
}

export function parseSavedEnvelope(payload: unknown): {saved: boolean} {
  const result = requireOkResult(payload);
  return {
    saved: result.saved === undefined ? true : requireBoolean(result.saved, 'result.saved'),
  };
}

export function parseHistoryEnvelope(
  payload: unknown,
  appliedField: 'undone' | 'redone',
): HistoryView {
  const result = requireOkResult(payload);
  return {
    applied: requireBoolean(result[appliedField], `result.${appliedField}`),
    ...(result.model === undefined ? {} : {model: parseModel(result.model, 'result.model')}),
    log: result.log === undefined
      ? []
      : parseStringArray(result.log, 'result.log'),
  };
}

export function parseRunEnvelope(payload: unknown): RunView {
  const result = requireOkResult(payload);
  const parsed: RunView = {};
  const modelRevision = optionalInteger(result.model_revision, 'result.model_revision', 0);
  if (modelRevision !== undefined) parsed.modelRevision = modelRevision;
  if (result.model !== undefined) parsed.model = parseModel(result.model, 'result.model');
  if (result.runtime_status !== undefined) parsed.runtimeStatus = parseRuntimeStatus(result.runtime_status);
  if (result.log !== undefined) parsed.log = parseStringArray(result.log, 'result.log');
  if (result.skipped !== undefined) parsed.skipped = requireBoolean(result.skipped, 'result.skipped');
  const reason = optionalString(result.reason, 'result.reason');
  const description = optionalString(result.description, 'result.description');
  const index = optionalInteger(result.index, 'result.index', 0);
  if (reason !== undefined) parsed.reason = reason;
  if (description !== undefined) parsed.description = description;
  if (Object.hasOwn(result, 'result')) parsed.result = result.result;
  if (index !== undefined) parsed.index = index;
  return parsed;
}

function parseTimeline(value: unknown, path: string): TimelineView {
  const source = requireRecord(value, path);
  return {
    items: requireArray(source.items, `${path}.items`).map((item, index) => {
      const itemPath = `${path}.items[${index}]`;
      const itemSource = requireRecord(item, itemPath);
      return {
        index: requireInteger(itemSource.index, `${itemPath}.index`, 0),
        state: requireString(itemSource.state, `${itemPath}.state`),
        runtimeStatus: parseRuntimeStatus(itemSource.runtime_status),
        snapshotValid: requireBoolean(itemSource.snapshot_valid, `${itemPath}.snapshot_valid`),
      };
    }),
    current: requireInteger(source.current, `${path}.current`, -1),
  };
}

export function parseTimelineEnvelope(payload: unknown): TimelineView {
  return parseTimeline(requireOkResult(payload), 'result');
}

export function parseTimelineRestoreEnvelope(payload: unknown): TimelineRestoreView {
  const result = requireOkResult(payload);
  return {
    timeline: parseTimeline(result.timeline, 'result.timeline'),
    model: parseModel(result.model, 'result.model'),
    recipe: parseRecipe(result.recipe, 'result.recipe'),
    log: parseStringArray(result.log, 'result.log'),
  };
}

function parseMaterialVisual(value: unknown, path: string): MaterialVisualView {
  const source = requireRecord(value, path);
  return {
    materialId: requireInteger(source.material_id, `${path}.material_id`, 0),
    displayName: requireString(source.display_name, `${path}.display_name`),
    color: requireColor(source.color, `${path}.color`),
    opacity: requireUnitInterval(source.opacity, `${path}.opacity`),
    metallic: requireUnitInterval(source.metallic, `${path}.metallic`),
    roughness: requireUnitInterval(source.roughness, `${path}.roughness`),
    visible: requireBoolean(source.visible, `${path}.visible`),
  };
}

function parseBoundingBox(value: unknown, path: string): BoundingBoxView {
  const source = requireRecord(value, path);
  return {
    min: requireTuple3(source.min, `${path}.min`),
    max: requireTuple3(source.max, `${path}.max`),
  };
}

function parsePreviewMesh(value: unknown, path: string): PreviewMeshView {
  const source = requireRecord(value, path);
  const materialId = requireInteger(source.mat_id, `${path}.mat_id`, 1);
  const visual = parseMaterialVisual(source.visual, `${path}.visual`);
  if (visual.materialId !== materialId) {
    throw new ApiContractError(`${path}.visual.material_id`, `same value as ${path}.mat_id`);
  }
  return {
    materialId,
    name: requireString(source.name, `${path}.name`),
    triangleCount: requireInteger(source.tri_count, `${path}.tri_count`, 0),
    boundingBox: parseBoundingBox(source.bbox, `${path}.bbox`),
    visual,
  };
}

export function parsePreviewManifestEnvelope(payload: unknown): PreviewManifestView {
  const result = requireOkResult(payload);
  const parsed: PreviewManifestView = {
    revision: requireInteger(result.rev, 'result.rev', 0),
    meshes: requireArray(result.meshes, 'result.meshes').map(
      (mesh, index) => parsePreviewMesh(mesh, `result.meshes[${index}]`),
    ),
  };
  const mode = optionalString(result.mode, 'result.mode');
  if (mode !== undefined) parsed.mode = mode;
  return parsed;
}
