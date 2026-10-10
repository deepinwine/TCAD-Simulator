import {useCallback, useEffect, useRef, useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {TcadApiError} from '../api/client';
import type {TcadApi, ModelSummaryView, DisplayManifestView} from '../api/types';
import {ErrorNotice} from '../components/ErrorNotice';
import {useI18n} from '../i18n/I18nContext';
import type {TranslationKey} from '../i18n/catalogs';
import {clipStateAllOff, type ClipAxis, type ClipState} from './clipping';
import {MaterialPanel, type MaterialDisplayState} from './MaterialPanel';
import {measureDistance, type PickHit} from './picking';
import {createThreeViewerRuntime} from './viewerRuntime';
import type {MaterialSummary, StandardView, ViewerRuntime} from './viewerRuntime';

export type ProjectionMode = 'perspective' | 'orthographic';
export type {StandardView, ViewerRuntime} from './viewerRuntime';

interface ThreeViewerProps {
  hiddenStepIds?: readonly string[];
  onDisplayReady?(manifest: DisplayManifestView | null, ready: boolean, failed?: boolean): void;
  model?: ModelSummaryView | null;
  api: TcadApi;
  refreshToken: number;
  runtimeFactory?: (api: TcadApi) => ViewerRuntime;
}

const STANDARD_VIEWS: ReadonlyArray<{view: StandardView; key: TranslationKey}> = [
  {view: 'iso', key: 'viewer.view.iso'},
  {view: 'top', key: 'viewer.view.top'},
  {view: 'bottom', key: 'viewer.view.bottom'},
  {view: 'front', key: 'viewer.view.front'},
  {view: 'back', key: 'viewer.view.back'},
  {view: 'left', key: 'viewer.view.left'},
  {view: 'right', key: 'viewer.view.right'},
];

const CLIP_AXES: ReadonlyArray<{axis: ClipAxis; label: string}> = [
  {axis: 'x', label: 'X'},
  {axis: 'y', label: 'Y'},
  {axis: 'z', label: 'Z'},
];
const EMPTY_HIDDEN: readonly string[] = [];

function asViewerApiError(error: unknown): TcadApiError {
  if (error instanceof TcadApiError) return error;
  return new TcadApiError(
    error instanceof Error ? error.message : String(error),
    {status: 0},
  );
}

export function ThreeViewer({api, model = null, refreshToken, runtimeFactory, hiddenStepIds = EMPTY_HIDDEN, onDisplayReady}: ThreeViewerProps) {
  const {t} = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<ViewerRuntime | null>(null);
  const [backend, setBackend] = useState<string | null>(null);
  const [initError, setInitError] = useState<TcadApiError | null>(null);
  const [loadError, setLoadError] = useState<TcadApiError | null>(null);
  const [sectionError, setSectionError] = useState<TcadApiError | null>(null);
  const [loadWarnings, setLoadWarnings] = useState<string[]>([]);
  const [displayError,setDisplayError] = useState<string | null>(null);
  const displayCallbackRef=useRef(onDisplayReady); displayCallbackRef.current=onDisplayReady;
  const hiddenRef=useRef(hiddenStepIds); hiddenRef.current=hiddenStepIds;
  const [retryAttempt, setRetryAttempt] = useState(0);
  const [orthoActive, setOrthoActive] = useState(false);
  const [clip, setClip] = useState<ClipState>(clipStateAllOff);
  const [materials, setMaterials] = useState<MaterialSummary[]>([]);
  const [display, setDisplay] = useState<Record<number, MaterialDisplayState>>({});
  const [selection, setSelection] = useState<PickHit | null>(null);
  const [measureMode, setMeasureMode] = useState(false);
  const [measurePoints, setMeasurePoints] = useState<PickHit['point'][]>([]);
  const [distance, setDistance] = useState<number | null>(null);
  const pointerDownRef = useRef<{id: number; x: number; y: number} | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return;
    let runtime: ViewerRuntime;
    try {
      runtime = (runtimeFactory ?? createThreeViewerRuntime)(api);
      runtime.mount(container);
    } catch (error) {
      setInitError(asViewerApiError(error));
      return;
    }
    runtimeRef.current = runtime;
    setBackend(runtime.backend);
    setInitError(null);
    return () => {
      runtimeRef.current = null;
      setBackend(null);
      runtime.dispose();
    };
  }, [api, runtimeFactory]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    let cancelled = false;
    runtime?.setSectionContext?.(model, error => {
      if (!cancelled) setSectionError(error === null ? null : asViewerApiError(error));
    });
    return () => {cancelled = true;};
  }, [model, retryAttempt, api, runtimeFactory]);

  useEffect(() => {
    containerRef.current?.querySelector('canvas')?.setAttribute('aria-label', t('viewer.canvas'));
  }, [backend, t]);

  useEffect(() => {
    runtimeRef.current?.setHiddenStepIds?.(hiddenStepIds);
    setSelection(null);
    setMeasurePoints([]);setDistance(null);runtimeRef.current?.setMeasureMarkers(null);
  }, [hiddenStepIds,api,runtimeFactory]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (runtime === null) return;
    let cancelled = false;
    setLoadError(null);
    displayCallbackRef.current?.(null,false);
    runtime.loadMeshes(refreshToken, retryAttempt > 0).then(result => {
      if (cancelled) return;
      if (result.stale) return;
      setLoadWarnings(result.warnings);
      setDisplayError(result.displayError ?? null);
      displayCallbackRef.current?.(result.display ?? null,!!result.display?.available);
      runtime.setHiddenStepIds?.(hiddenRef.current);
      setMaterials(result.materials);
      setDisplay(Object.fromEntries(result.materials.map(material => [
        material.matId,
        {visible: material.visible, opacity: material.opacity},
      ])));
    }).catch(error => {
      if (cancelled) return;
      setLoadError(asViewerApiError(error));
      displayCallbackRef.current?.(null,false,true);
    });
    return () => {
      cancelled = true;
    };
  }, [refreshToken, retryAttempt, api, runtimeFactory]);

  const retry = useCallback(() => {
    setRetryAttempt(attempt => attempt + 1);
  }, []);

  const toggleProjection = useCallback(() => {
    const runtime = runtimeRef.current;
    if (runtime === null) return;
    const next = orthoActive ? 'perspective' : 'orthographic';
    runtime.setProjection(next);
    setOrthoActive(!orthoActive);
  }, [orthoActive]);

  const updateClip = useCallback((next: ClipState) => {
    setClip(next);
    runtimeRef.current?.setClipping(next);
  }, []);

  const toggleClipAxis = (axis: ClipAxis) => {
    updateClip({
      ...clip,
      [axis]: {...clip[axis], enabled: !clip[axis].enabled},
    });
  };

  const moveClipAxis = (axis: ClipAxis, position: number) => {
    updateClip({
      ...clip,
      [axis]: {...clip[axis], position},
    });
  };

  const changeMaterialDisplay = (matId: number, next: MaterialDisplayState) => {
    setDisplay(current => ({...current, [matId]: next}));
    runtimeRef.current?.setMaterialDisplay(matId, next);
  };

  const toggleMeasureMode = () => {
    const next = !measureMode;
    setMeasureMode(next);
    setMeasurePoints([]);
    setDistance(null);
    runtimeRef.current?.setMeasureMarkers(null);
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    pointerDownRef.current = {id: event.pointerId, x: event.clientX, y: event.clientY};
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    const down = pointerDownRef.current;
    pointerDownRef.current = null;
    if (event.button !== 0 || down === null || down.id !== event.pointerId) return;
    const moved = Math.hypot(event.clientX - down.x, event.clientY - down.y);
    if (moved > 4) return;
    const runtime = runtimeRef.current;
    if (runtime === null) return;
    const stage = event.currentTarget;
    const rect = stage.getBoundingClientRect();
    const ndcX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1;
    const ndcY = -(((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 - 1);
    const hit = runtime.pickAt(ndcX, ndcY);
    if (hit === null) {
      if (!measureMode) setSelection(null);
      return;
    }
    setSelection(hit);
    if (measureMode) {
      const nextPoints = measurePoints.length >= 2 ? [hit.point] : [...measurePoints, hit.point];
      setMeasurePoints(nextPoints);
      runtime.setMeasureMarkers(nextPoints.map(point => {
        const [x, y, z] = point.toArray();
        return [x, y, z] as const;
      }));
      setDistance(nextPoints.length === 2 ? measureDistance(nextPoints[0], nextPoints[1]) : null);
    }
  };

  return (
    <section className="workspace-pane viewer-pane" aria-label={t('viewer.region')}>
      <header className="pane-header viewer-header">
        <div>
          <span className="pane-kicker">{t('viewer.kicker')}</span>
          <h2>{t('viewer.title')}</h2>
        </div>
        {backend !== null && <span className="viewer-backend-badge">{backend}</span>}
      </header>
      <div className="viewer-toolbar" role="group" aria-label={t('viewer.standardViews')}>
        {STANDARD_VIEWS.map(({view, key}) => (
          <button
            key={view}
            type="button"
            className="viewer-view-button"
            disabled={initError !== null}
            onClick={() => runtimeRef.current?.setStandardView(view)}
          >
            {t(key)}
          </button>
        ))}
        <button
          type="button"
          className="viewer-view-button"
          disabled={initError !== null}
          onClick={() => runtimeRef.current?.fit()}
        >
          {t('viewer.fit')}
        </button>
        <button
          type="button"
          className="viewer-view-button"
          aria-pressed={orthoActive}
          disabled={initError !== null}
          onClick={toggleProjection}
        >
          {t('viewer.orthographic')}
        </button>
        <button
          type="button"
          className="viewer-view-button"
          aria-pressed={measureMode}
          disabled={initError !== null}
          onClick={toggleMeasureMode}
        >
          {t('viewer.measureMode')}
        </button>
      </div>
      <div className="viewer-clip-group" role="group" aria-label={t('viewer.clipPlanes')}>
        {CLIP_AXES.map(({axis, label}) => (
          <div key={axis} className="viewer-clip-row">
            <label className="viewer-clip-axis">
              <input
                type="checkbox"
                checked={clip[axis].enabled}
                disabled={initError !== null}
                aria-label={t('viewer.enableClip', {axis: label})}
                onChange={() => toggleClipAxis(axis)}
              />
              {label}
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={clip[axis].position}
              disabled={initError !== null || !clip[axis].enabled}
              aria-label={t('viewer.clipPosition', {axis: label})}
              onChange={event => moveClipAxis(axis, Number(event.target.value))}
            />
          </div>
        ))}
      </div>
      <div
        className="viewer-stage"
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
      >
        <MaterialPanel
          materials={materials}
          display={display}
          onChange={changeMaterialDisplay}
          disabled={initError !== null}
        />
        {selection !== null && (
          <div className="viewer-selection-bar" role="status">
            {t('viewer.hitPoint', {
              name: selection.name,
              point: selection.point.toArray().map(v => v.toFixed(3)).join(', '),
            })}
          </div>
        )}
        {distance !== null && (
          <div className="viewer-measure-readout" role="status" aria-live="polite">
            {t('viewer.distance', {distance: distance.toFixed(4)})}
          </div>
        )}
        {initError !== null && (
          <ErrorNotice
            title={t('viewer.initError')}
            error={initError}
            suggestion={t('viewer.initSuggestion')}
            trustedSuggestion
          />
        )}
        {initError === null && loadError !== null && (
          <ErrorNotice
            title={t('viewer.loadError')}
            error={loadError}
            suggestion={materials.length > 0 ? t('viewer.staleSuggestion') : undefined}
            trustedSuggestion
            actionLabel={t('viewer.retry')}
            onAction={retry}
          />
        )}
        {initError === null && sectionError !== null && (
          <ErrorNotice title={t('viewer.sectionError')} error={sectionError} actionLabel={t('viewer.retry')} onAction={retry} />
        )}
        {initError === null && displayError !== null && <ErrorNotice title={t('display.error')} message={t(displayError.includes('display_budget_exceeded') ? 'display.budget' : displayError.includes('unknown_provenance') ? 'display.unknown' : 'display.failed')} suggestion={t('display.fallback')} trustedSuggestion actionLabel={t('viewer.retry')} onAction={retry} />}
        {initError === null && loadError === null && loadWarnings.length > 0 && (
          <ErrorNotice
            title={t('viewer.partialError')}
            suggestion={t('viewer.partialSuggestion')}
            trustedSuggestion
            actionLabel={t('viewer.retry')}
            onAction={retry}
          />
        )}
      </div>
    </section>
  );
}
