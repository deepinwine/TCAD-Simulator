export type RuntimeStatus = 'ready' | 'dirty' | 'running' | 'done' | 'error';

export type Vec3 = readonly [number, number, number];
export type RgbColor = readonly [number, number, number];
export type ParameterChoiceValue = string | number | boolean | null;
export type ParameterChoice = readonly [ParameterChoiceValue, string];

export interface ParameterSpecView {
  key: string;
  label: string;
  type: string;
  defaultValue?: unknown;
  minimum?: number;
  maximum?: number;
  choices?: readonly ParameterChoice[];
  decimals?: number;
  step?: number;
  units?: string;
  tooltip?: string;
}

export interface StepView {
  index: number;
  name: string;
  instanceName: string;
  group: string;
  loop: string;
  enabled: boolean;
  params: Record<string, unknown>;
  parameterSpecs: ParameterSpecView[];
  runtimeStatus: RuntimeStatus;
}

export interface ModelSummaryView {
  gridShape: Vec3;
  voxelSizeNm: number;
  threads?: number;
  substrateMaterial?: string;
  substrateThicknessNm?: number;
}

export interface MaterialView {
  id: number;
  name: string;
  color: RgbColor;
  enabled: boolean;
}

export interface InitView {
  recipe: StepView[];
  model: ModelSummaryView;
  factories: string[];
  materials: MaterialView[];
  uiState: Record<string, unknown>;
}

export interface SetStepRequest {
  index: number;
  enabled?: boolean;
  params?: Record<string, unknown>;
  loop?: string;
  group?: string;
  noAutosave?: boolean;
}

export interface SetStepView {
  step: StepView;
  statuses: RuntimeStatus[];
  warnings: string[];
}

export interface RunView {
  modelRevision?: number;
  model?: ModelSummaryView;
  runtimeStatus?: RuntimeStatus;
  recipe?: StepView[];
  log?: string[];
  skipped?: boolean;
  reason?: string;
  description?: string;
  result?: unknown;
  index?: number;
}

export interface TimelineItemView {
  index: number;
  state: string;
  runtimeStatus: RuntimeStatus;
  snapshotValid: boolean;
}

export interface TimelineView {
  items: TimelineItemView[];
  current: number;
}

export interface TimelineRestoreView {
  timeline: TimelineView;
  model: ModelSummaryView;
  recipe: StepView[];
  log: string[];
}

export interface MaterialVisualView {
  materialId: number;
  displayName: string;
  color: RgbColor;
  opacity: number;
  metallic: number;
  roughness: number;
  visible: boolean;
}

export interface BoundingBoxView {
  min: Vec3;
  max: Vec3;
}

export interface PreviewMeshView {
  materialId: number;
  name: string;
  triangleCount: number;
  boundingBox: BoundingBoxView;
  visual: MaterialVisualView;
}

export interface PreviewManifestView {
  revision: number;
  mode?: string;
  meshes: PreviewMeshView[];
}

export interface PreviewManifestRequest {
  mode?: 'solid' | 'fast';
  faceLimit?: number;
}

export interface PreviewStlRequest {
  materialId: number;
  revision: number;
  mode?: 'solid' | 'fast';
}

export interface TcadApi {
  init(signal?: AbortSignal): Promise<InitView>;
  setStep(request: SetStepRequest, signal?: AbortSignal): Promise<SetStepView>;
  runStep(index: number, signal?: AbortSignal): Promise<RunView>;
  runTo(index: number, signal?: AbortSignal): Promise<RunView>;
  runAll(signal?: AbortSignal): Promise<RunView>;
  getTimeline(signal?: AbortSignal): Promise<TimelineView>;
  restoreTimeline(index: number, signal?: AbortSignal): Promise<TimelineRestoreView>;
  getPreviewManifest(
    request?: PreviewManifestRequest,
    signal?: AbortSignal,
  ): Promise<PreviewManifestView>;
  getMaterialStl(request: PreviewStlRequest, signal?: AbortSignal): Promise<ArrayBuffer>;
}
