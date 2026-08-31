interface ThreeViewerProps {
  refreshToken: number;
}

export function ThreeViewer({refreshToken}: ThreeViewerProps) {
  return (
    <section
      className="workspace-pane viewer-pane"
      aria-label="3D Viewer"
      data-refresh-token={refreshToken}
    >
      <header className="pane-header viewer-header">
        <div>
          <span className="pane-kicker">Geometry</span>
          <h2>3D Viewer</h2>
        </div>
        <span className="viewer-mode">Preview</span>
      </header>
      <div className="viewer-empty" role="status" aria-live="polite">
        <span className="viewer-empty-icon" aria-hidden="true">3D</span>
        <strong>当前模型为空</strong>
        <span>真实可交互几何将在 Viewer 加载后显示。</span>
      </div>
    </section>
  );
}
