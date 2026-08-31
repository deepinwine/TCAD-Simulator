export interface MaterialDisplayState {
  visible: boolean;
  opacity: number;
}

interface MaterialPanelProps {
  materials: ReadonlyArray<{
    matId: number;
    name: string;
    visible: boolean;
    opacity: number;
  }>;
  display: Record<number, MaterialDisplayState>;
  onChange(matId: number, next: MaterialDisplayState): void;
  disabled?: boolean;
}

/**
 * 材料显示控制面板：可见性开关与透明度滑杆。
 *
 * 纯浏览器本地显示状态，不回写后端。
 */
export function MaterialPanel({materials, display, onChange, disabled = false}: MaterialPanelProps) {
  if (materials.length === 0) return null;
  return (
    <div className="viewer-material-panel" role="group" aria-label="材料显示控制">
      {materials.map(({matId, name}) => {
        const state = display[matId];
        if (state === undefined) return null;
        return (
          <div key={matId} className="viewer-material-row">
            <label className="viewer-material-name">
              <input
                type="checkbox"
                checked={state.visible}
                disabled={disabled}
                aria-label={`${name} 可见`}
                onChange={() => onChange(matId, {...state, visible: !state.visible})}
              />
              {name}
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={state.opacity}
              disabled={disabled}
              aria-label={`${name} 透明度`}
              onChange={event => onChange(matId, {
                ...state,
                opacity: Number(event.target.value),
              })}
            />
          </div>
        );
      })}
    </div>
  );
}
