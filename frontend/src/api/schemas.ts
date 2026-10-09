import type {
  MaterialSliceView,
  BoundingBoxView,
  HistoryView,
  InitView,
  MaskAsset,
  MaskAssetApplyView,
  MaskAssetLayer,
  MaskAssetShape,
  MaskAssetSummary,
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

export function parseMaterialSliceEnvelope(payload: unknown): MaterialSliceView {
  const source = requireOkResult(payload);
  const axis = requireString(source.axis, 'result.axis');
  if (!['X', 'Y', 'Z'].includes(axis)) throw new ApiContractError('result.axis', 'X, Y, Z');
  if (source.dtype !== 'u16') throw new ApiContractError('result.dtype', 'u16');
  const indexMax = requireInteger(source.index_max, 'result.index_max', 0);
  const index = requireInteger(source.index, 'result.index', 0);
  if (!Number.isSafeInteger(indexMax) || !Number.isSafeInteger(index)) throw new ApiContractError('result.index', 'safe integers');
  if (index > indexMax) throw new ApiContractError('result.index', 'within index_max');
  const shape = requireArray(source.shape, 'result.shape');
  if (shape.length !== 2) throw new ApiContractError('result.shape', 'two dimensions');
  const rows = requireInteger(shape[0], 'result.shape[0]', 1);
  const cols = requireInteger(shape[1], 'result.shape[1]', 1);
  const count = rows * cols;
  if (!Number.isSafeInteger(count) || count > 16_777_216 || rows > 4096 || cols > 4096) throw new ApiContractError('result.shape', 'at most 4096 per dimension and 16777216 pixels');
  const encoded = requireString(source.data_b64, 'result.data_b64');
  const padding = (3 - (count * 2) % 3) % 3;
  if (encoded.length !== Math.ceil(count * 2 / 3) * 4) {
    throw new ApiContractError('result.data_b64', 'exact-length base64 uint16 data');
  }
  // Scan once: repeated regex groups can exhaust V8's stack on valid large slices.
  const contentLength = encoded.length - padding;
  for (let i = 0; i < encoded.length; i++) {
    const code = encoded.charCodeAt(i);
    const valid = i >= contentLength ? code === 61
      : (code >= 65 && code <= 90) || (code >= 97 && code <= 122)
        || (code >= 48 && code <= 57) || code === 43 || code === 47;
    if (!valid) throw new ApiContractError('result.data_b64', 'exact-length base64 uint16 data');
  }
  const bytes = atob(encoded);
  if (btoa(bytes) !== encoded) throw new ApiContractError('result.data_b64', 'canonical base64');
  if (bytes.length !== count * 2) throw new ApiContractError('result.data_b64', 'shape-sized uint16 data');
  const data = new Uint16Array(count);
  for (let i = 0; i < count; i++) data[i] = bytes.charCodeAt(i * 2) | (bytes.charCodeAt(i * 2 + 1) << 8);
  return {axis: axis.toLowerCase() as MaterialSliceView['axis'], index, indexMax, shape: [rows, cols], data};
}
import {canonicalUnits, toCanonical, type Dimension, type DisplayUnit} from '../units/units';

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

function requirePoint(value: unknown, path: string): readonly [number, number] {
  const items = requireArray(value, path);
  if (items.length !== 2) {
    throw new ApiContractError(path, 'tuple with exactly 2 finite numbers');
  }
  return [
    requireFiniteNumber(items[0], `${path}[0]`),
    requireFiniteNumber(items[1], `${path}[1]`),
  ];
}

function requireTuple4(value: unknown, path: string): readonly [number, number, number, number] {
  const items = requireArray(value, path);
  if (items.length !== 4) {
    throw new ApiContractError(path, 'tuple with exactly 4 finite numbers');
  }
  return [
    requireFiniteNumber(items[0], `${path}[0]`),
    requireFiniteNumber(items[1], `${path}[1]`),
    requireFiniteNumber(items[2], `${path}[2]`),
    requireFiniteNumber(items[3], `${path}[3]`),
  ];
}

function requirePositiveNumber(value: unknown, path: string): number {
  const number = requireFiniteNumber(value, path);
  if (number <= 0) {
    throw new ApiContractError(path, 'positive finite number');
  }
  return number;
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
  const dimension = optionalString(source.dimension, `${path}.dimension`);
  const canonicalUnit = optionalString(source.canonical_unit, `${path}.canonical_unit`);
  const capabilityKey = optionalString(source.capability_key, `${path}.capability_key`);
  if (dimension !== undefined) parsed.dimension = dimension;
  if (canonicalUnit !== undefined) parsed.canonicalUnit = canonicalUnit;
  if (capabilityKey !== undefined) parsed.capabilityKey = capabilityKey;
  if (source.display_units !== undefined && source.display_units !== null) {
    parsed.displayUnits = parseStringArray(source.display_units, `${path}.display_units`);
  }
  // Null metadata and an empty unit list are emitted for unannotated legacy
  // specs. A declared unit contract, however, must be internally consistent.
  if (dimension !== undefined || canonicalUnit !== undefined || parsed.displayUnits?.length) {
    if (dimension === undefined || !Object.hasOwn(canonicalUnits, dimension)) {
      throw new ApiContractError(`${path}.dimension`, 'length, time, angle, rate, or concentration');
    }
    const validatedDimension = dimension as Dimension;
    if (canonicalUnit !== canonicalUnits[validatedDimension]) {
      throw new ApiContractError(`${path}.canonical_unit`, canonicalUnits[validatedDimension]);
    }
    parsed.displayUnits?.forEach((unit, index) => {
      try { toCanonical(0, validatedDimension, unit as DisplayUnit); }
      catch { throw new ApiContractError(`${path}.display_units[${index}]`, `display unit for ${dimension}`); }
    });
  }
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
  if (result.factory_templates !== undefined) view.factoryTemplates = parseRecipe(result.factory_templates, 'result.factory_templates');
  if (result.current_recipe !== undefined) {
    view.currentRecipe = parseCurrentRecipe(result.current_recipe);
  }
  if (result.backend_capabilities !== undefined) {
    const capabilities = requireRecord(result.backend_capabilities, 'result.backend_capabilities');
    view.backendCapabilities = Object.fromEntries(Object.entries(capabilities).map(([key, value]) => [
      key, requireString(value, `result.backend_capabilities.${key}`),
    ]));
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

function parseMaskAssetLayer(value: unknown, path: string): MaskAssetLayer {
  const source = requireRecord(value, path);
  return {
    id: requireString(source.id, `${path}.id`),
    layer: requireInteger(source.layer, `${path}.layer`, 0),
    datatype: requireInteger(source.datatype, `${path}.datatype`, 0),
    name: requireString(source.name, `${path}.name`),
    visible: requireBoolean(source.visible, `${path}.visible`),
  };
}

function parseMaskPoints(value: unknown, path: string): readonly (readonly [number, number])[] {
  return requireArray(value, path).map((point, index) => requirePoint(point, `${path}[${index}]`));
}

function parseMaskAssetShape(value: unknown, path: string): MaskAssetShape {
  const source = requireRecord(value, path);
  const id = requireString(source.id, `${path}.id`);
  const layerId = requireString(source.layer_id, `${path}.layer_id`);
  const type = requireString(source.type, `${path}.type`);
  if (type === 'rectangle') {
    return {
      id, layerId, type,
      xNm: requireFiniteNumber(source.x_nm, `${path}.x_nm`),
      yNm: requireFiniteNumber(source.y_nm, `${path}.y_nm`),
      widthNm: requirePositiveNumber(source.width_nm, `${path}.width_nm`),
      heightNm: requirePositiveNumber(source.height_nm, `${path}.height_nm`),
      rotationDeg: requireFiniteNumber(source.rotation_deg ?? 0, `${path}.rotation_deg`),
    };
  }
  if (type === 'circle' || type === 'hole') {
    return {
      id, layerId, type,
      cxNm: requireFiniteNumber(source.cx_nm, `${path}.cx_nm`),
      cyNm: requireFiniteNumber(source.cy_nm, `${path}.cy_nm`),
      radiusNm: requirePositiveNumber(source.radius_nm, `${path}.radius_nm`),
    };
  }
  if (type === 'line') {
    const pointsNm = parseMaskPoints(source.points_nm, `${path}.points_nm`);
    if (pointsNm.length < 2) {
      throw new ApiContractError(`${path}.points_nm`, 'at least 2 finite points');
    }
    return {
      id, layerId, type, pointsNm,
      widthNm: requirePositiveNumber(source.width_nm, `${path}.width_nm`),
    };
  }
  if (type === 'polygon') {
    const pointsNm = parseMaskPoints(source.points_nm, `${path}.points_nm`);
    if (pointsNm.length < 4) {
      throw new ApiContractError(`${path}.points_nm`, 'at least 4 finite points');
    }
    const first = pointsNm[0];
    const last = pointsNm[pointsNm.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) {
      throw new ApiContractError(`${path}.points_nm`, 'explicitly closed polygon');
    }
    return {id, layerId, type, pointsNm};
  }
  throw new ApiContractError(`${path}.type`, 'rectangle, circle, hole, line, or polygon');
}

function parseMaskAsset(value: unknown, path: string): MaskAsset {
  const source = requireRecord(value, path);
  if (source.version !== 1) {
    throw new ApiContractError(`${path}.version`, '1');
  }
  if (source.coordinate_unit !== 'nm') {
    throw new ApiContractError(`${path}.coordinate_unit`, 'nm');
  }
  const parsed: MaskAsset = {
    version: 1,
    id: requireString(source.id, `${path}.id`),
    revision: requireInteger(source.revision, `${path}.revision`, 1),
    name: requireString(source.name, `${path}.name`),
    coordinateUnit: 'nm',
    boundsNm: requireTuple4(source.bounds_nm, `${path}.bounds_nm`),
    layers: requireArray(source.layers, `${path}.layers`).map(
      (layer, index) => parseMaskAssetLayer(layer, `${path}.layers[${index}]`),
    ),
    shapes: requireArray(source.shapes, `${path}.shapes`).map(
      (shape, index) => parseMaskAssetShape(shape, `${path}.shapes[${index}]`),
    ),
    source: requireRecord(source.source, `${path}.source`),
  };
  const sha256 = optionalString(source.sha256, `${path}.sha256`);
  if (parsed.boundsNm[2] <= parsed.boundsNm[0] || parsed.boundsNm[3] <= parsed.boundsNm[1]) {
    throw new ApiContractError(`${path}.bounds_nm`, 'positive-area bounds');
  }
  const layerIds = new Set<string>();
  parsed.layers.forEach((layer, index) => {
    if (layerIds.has(layer.id)) {
      throw new ApiContractError(`${path}.layers[${index}].id`, 'unique layer id');
    }
    layerIds.add(layer.id);
  });
  const shapeIds = new Set<string>();
  parsed.shapes.forEach((shape, index) => {
    if (shapeIds.has(shape.id)) {
      throw new ApiContractError(`${path}.shapes[${index}].id`, 'unique shape id');
    }
    shapeIds.add(shape.id);
    if (!layerIds.has(shape.layerId)) {
      throw new ApiContractError(`${path}.shapes[${index}].layer_id`, 'existing layer id');
    }
  });
  if (sha256 !== undefined) parsed.sha256 = sha256;
  return parsed;
}

function parseMaskAssetSummary(value: unknown, path: string): MaskAssetSummary {
  const source = requireRecord(value, path);
  return {
    id: requireString(source.id, `${path}.id`),
    name: requireString(source.name, `${path}.name`),
    revision: requireInteger(source.revision, `${path}.revision`, 1),
    sha256: requireString(source.sha256, `${path}.sha256`),
  };
}

export function parseMaskAssetListEnvelope(payload: unknown): MaskAssetSummary[] {
  const envelope = requireRecord(payload, '$');
  if (envelope.ok !== true) throw new ApiContractError('ok', 'true');
  return requireArray(envelope.result, 'result').map(
    (summary, index) => parseMaskAssetSummary(summary, `result[${index}]`),
  );
}

export function parseMaskAssetEnvelope(payload: unknown): MaskAsset {
  return parseMaskAsset(requireOkResult(payload), 'result');
}

export function parseMaskAssetDeleteEnvelope(payload: unknown): void {
  const result = requireOkResult(payload);
  if (result.deleted !== true) {
    throw new ApiContractError('result.deleted', 'true');
  }
}

export function parseMaskAssetApplyEnvelope(payload: unknown, index: number): MaskAssetApplyView {
  const result = requireOkResult(payload);
  return {
    asset: parseMaskAsset(result.asset, 'result.asset'),
    step: parseStep(result.step, 'result.step', index),
    statuses: requireArray(result.statuses, 'result.statuses').map(item => parseRuntimeStatus(item)),
    warnings: result.warnings === undefined ? [] : parseStringArray(result.warnings, 'result.warnings'),
  };
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
