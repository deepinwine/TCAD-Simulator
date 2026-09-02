import {useCallback, useRef, useState} from 'react';
import {useAppState} from '../state/AppStateContext';

interface PlannedStepView {
  type: string;
  params: Record<string, unknown>;
  confidence: number;
  sourceSpan: string;
  warnings: string[];
  isDefault: boolean;
}

interface DraftView {
  version: number;
  sourceText: string;
  steps: PlannedStepView[];
  warnings: string[];
  ambiguities: string[];
}

interface ValidationView {
  ok: boolean;
  errors: string[];
  warnings: string[];
  mode_recommendations: Array<{
    step: string;
    recommended_mode: string;
    reason: string;
  }>;
}

/**
 * M16/M17：自然语言工艺描述 → 可审核 Recipe。
 * 解析在后端 /api/v2/recipe/parse（规则式，无需 LLM）。
 * 应用走既有 /api/recipe/import（冻结契约）。
 */
export function RecipeAssistant() {
  const {actions} = useAppState();
  const [input, setInput] = useState('');
  const [draft, setDraft] = useState<DraftView | null>(null);
  const [validation, setValidation] = useState<ValidationView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const generate = useCallback(async () => {
    const text = input.trim();
    if (text === '' || busy) return;
    setBusy(true);
    setError(null);
    setDraft(null);
    setValidation(null);
    try {
      const response = await fetch('/api/v2/recipe/parse', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({text}),
      });
      const payload: unknown = await response.json();
      if (typeof payload === 'object' && payload !== null && 'ok' in payload) {
        const data = payload as {ok: boolean; draft?: DraftView; validation?: ValidationView; error?: string};
        if (data.ok && data.draft && data.validation) {
          setDraft(data.draft);
          setValidation(data.validation);
        } else {
          setError(data.error ?? '解析失败');
        }
      } else {
        setError('服务返回了无效响应');
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  }, [input, busy]);

  const apply = useCallback(() => {
    if (draft === null || !validation?.ok) return;
    // 把 draft 转换为 recipe blob（与 /api/recipe/import 兼容的格式）
    const recipeBlob = {
      name: 'NL Generated Recipe',
      steps: draft.steps.map(step => ({
        name: step.type,
        enabled: true,
        params: step.params,
      })),
    };
    void actions.importRecipe({recipe: recipeBlob, name: 'NL Recipe'});
    setDraft(null);
    setValidation(null);
    setInput('');
  }, [draft, validation, actions]);

  return (
    <section className="recipe-assistant" aria-label="Recipe Assistant">
      <header className="pane-header">
        <div>
          <span className="pane-kicker">AI</span>
          <h2>Recipe Assistant</h2>
        </div>
      </header>
      <textarea
        ref={inputRef}
        className="recipe-input"
        aria-label="工艺描述"
        placeholder={'描述你的半导体工艺…\n例：在Si上沉积100 nm SiO2，然后光刻100 nm孔，刻蚀500 nm，沉积20 nm SiN，填W并CMP'}
        value={input}
        disabled={busy}
        onChange={event => setInput(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            void generate();
          }
        }}
      />
      <div className="recipe-actions">
        <button
          type="button"
          className="toolbar-button is-primary"
          disabled={busy || input.trim() === ''}
          onClick={() => void generate()}
        >
          {busy ? '解析中…' : '生成 Recipe'}
        </button>
        {draft !== null && validation?.ok && (
          <button
            type="button"
            className="toolbar-button"
            onClick={apply}
          >
            应用到 Process Flow
          </button>
        )}
      </div>
      {error !== null && (
        <p className="recipe-error" role="alert">{error}</p>
      )}
      {draft !== null && (
        <div className="recipe-draft" role="region" aria-label="Proposed Recipe">
          <h3>Proposed Recipe</h3>
          <ol className="recipe-steps">
            {draft.steps.map((step, index) => (
              <li key={index} className={`recipe-step ${step.isDefault ? 'is-default' : ''}`}>
                <span className="step-number">{String(index + 1).padStart(2, '0')}</span>
                <span className="step-info">
                  <strong>{step.type}</strong>
                  <span className="step-params">
                    {Object.entries(step.params)
                      .slice(0, 3)
                      .map(([key, value]) => `${key}=${String(value)}`)
                      .join(' · ')}
                  </span>
                  {step.isDefault && (
                    <span className="default-badge">自动填充默认值</span>
                  )}
                  {step.confidence < 0.7 && (
                    <span className="low-confidence">置信度 {(step.confidence * 100).toFixed(0)}%</span>
                  )}
                  {step.warnings.map((warning, warningIndex) => (
                    <span key={warningIndex} className="step-warning">⚠ {warning}</span>
                  ))}
                </span>
              </li>
            ))}
          </ol>
          {draft.ambiguities.length > 0 && (
            <div className="recipe-ambiguities" role="alert">
              <h4>歧义</h4>
              <ul>
                {draft.ambiguities.map((ambiguity, index) => (
                  <li key={index}>{ambiguity}</li>
                ))}
              </ul>
            </div>
          )}
          {validation !== null && validation.mode_recommendations.length > 0 && (
            <div className="mode-recommendations">
              <h4>仿真模式建议</h4>
              <ul>
                {validation.mode_recommendations.map((rec, index) => (
                  <li key={index}>
                    <strong>{rec.step}</strong>: {rec.recommended_mode}
                    <span className="mode-reason">（{rec.reason}）</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
