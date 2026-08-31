import {useCallback, useEffect, useRef, useState} from 'react';
import type {TcadApi} from '../api/types';
import {ErrorNotice} from '../components/ErrorNotice';
import {clipStateAllOff, type ClipAxis, type ClipState} from './clipping';
import {createThreeViewerRuntime} from './viewerRuntime';
import type {StandardView, ViewerRuntime} from './viewerRuntime';

export type ProjectionMode = 'perspective' | 'orthographic';
export type {StandardView, ViewerRuntime} from './viewerRuntime';

interface ThreeViewerProps {
  api: TcadApi;
  refreshToken: number;
  runtimeFactory?: (api: TcadApi) => ViewerRuntime;
}

const STANDARD_VIEWS: ReadonlyArray<{view: StandardView; label: string}> = [
  {view: 'iso', label: 'ISO 视图'},
  {view: 'top', label: '顶视图'},
  {view: 'bottom', label: '底视图'},
  {view: 'front', label: '前视图'},
  {view: 'back', label: '后视图'},
  {view: 'left', label: '左视图'},
  {view: 'right', label: '右视图'},
];

const CLIP_AXES: ReadonlyArray<{axis: ClipAxis; label: string}> = [
  {axis: 'x', label: 'X'},
  {axis: 'y', label: 'Y'},
  {axis: 'z', label: 'Z'},
];

export function ThreeViewer({api, refreshToken, runtimeFactory}: ThreeViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<ViewerRuntime | null>(null);
  const [backend, setBackend] = useState<string | null>(null);
  const [initError, setInitError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [orthoActive, setOrthoActive] = useState(false);
  const [clip, setClip] = useState<ClipState>(clipStateAllOff);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return;
    let runtime: ViewerRuntime;
    try {
      runtime = (runtimeFactory ?? createThreeViewerRuntime)(api);
      runtime.mount(container);
    } catch (error) {
      setInitError(error instanceof Error ? error.message : String(error));
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
    if (runtime === null) return;
    let cancelled = false;
    setLoadError(null);
    runtime.loadMeshes(refreshToken).catch(error => {
      if (cancelled) return;
      setLoadError(error instanceof Error ? error.message : String(error));
    });
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  const retry = useCallback(() => {
    const runtime = runtimeRef.current;
    if (runtime === null) return;
    setLoadError(null);
    runtime.loadMeshes(refreshToken).catch(error => {
      setLoadError(error instanceof Error ? error.message : String(error));
    });
  }, [refreshToken]);

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

  return (
    <section className="workspace-pane viewer-pane" aria-label="3D Viewer">
      <header className="pane-header viewer-header">
        <div>
          <span className="pane-kicker">Geometry</span>
          <h2>3D Viewer</h2>
        </div>
        {backend !== null && <span className="viewer-backend-badge">{backend}</span>}
      </header>
      <div className="viewer-toolbar" role="group" aria-label="标准视图">
        {STANDARD_VIEWS.map(({view, label}) => (
          <button
            key={view}
            type="button"
            className="viewer-view-button"
            disabled={initError !== null}
            onClick={() => runtimeRef.current?.setStandardView(view)}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          className="viewer-view-button"
          disabled={initError !== null}
          onClick={() => runtimeRef.current?.fit()}
        >
          适应窗口
        </button>
        <button
          type="button"
          className="viewer-view-button"
          aria-pressed={orthoActive}
          disabled={initError !== null}
          onClick={toggleProjection}
        >
          正交视图
        </button>
      </div>
      <div className="viewer-clip-group" role="group" aria-label="裁剪平面">
        {CLIP_AXES.map(({axis, label}) => (
          <div key={axis} className="viewer-clip-row">
            <label className="viewer-clip-axis">
              <input
                type="checkbox"
                checked={clip[axis].enabled}
                disabled={initError !== null}
                aria-label={`启用 ${label} 裁剪`}
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
              aria-label={`${label} 裁剪位置`}
              onChange={event => moveClipAxis(axis, Number(event.target.value))}
            />
          </div>
        ))}
      </div>
      <div className="viewer-stage" ref={containerRef}>
        {initError !== null && (
          <ErrorNotice
            title="无法初始化 3D Viewer"
            message={initError}
            suggestion="请检查浏览器 WebGL2 支持后重试。"
          />
        )}
        {initError === null && loadError !== null && (
          <ErrorNotice
            title="几何加载失败"
            message={loadError}
            actionLabel="重试加载几何"
            onAction={retry}
          />
        )}
      </div>
    </section>
  );
}
