import {useEffect, useReducer, useRef, useState, type KeyboardEvent} from 'react';
import type {MaskAsset, MaskAssetApplyView, TcadApi} from '../api/types';
import {TcadApiError} from '../api/client';
import {ErrorNotice} from '../components/ErrorNotice';
import {LanguageSwitcher} from '../components/LanguageSwitcher';
import {useI18n, type TranslationKey} from '../i18n/I18nContext';
import {createMaskEditorState, maskEditorReducer} from './editorReducer';
import {MaskCanvas} from './MaskCanvas';
const shapeFieldKeys = [
  'xNm',
  'yNm',
  'widthNm',
  'heightNm',
  'rotationDeg',
  'cxNm',
  'cyNm',
  'radiusNm',
  'points',
];
export interface MaskWorkbenchProps {
  api: TcadApi;
  initialAsset: MaskAsset;
  stepIndex: number;
  onApply(payload: MaskAssetApplyView): void;
  onClose(): void;
  onError?(error: unknown): void;
}
function NumericField({
  label,
  value,
  onChange,
  onValidity,
  positive = false,
  nonNegative = false,
  integer = false,
}: {
  label: string;
  value: number;
  onChange(value: number): void;
  onValidity(invalid: boolean): void;
  positive?: boolean;
  nonNegative?: boolean;
  integer?: boolean;
}) {
  const [raw, setRaw] = useState(String(value));
  const [invalid, setInvalid] = useState(false);
  const {t} = useI18n();
  useEffect(() => {
    setRaw(String(value));
    setInvalid(false);
    onValidity(false);
  }, [value]); // retain incomplete text until a new canonical value arrives
  return (
    <label className="mask-field">
      {label}
      <input
        aria-label={label}
        type="number"
        step={integer ? 1 : 'any'}
        value={raw}
        aria-invalid={invalid}
        onChange={(event) => {
          const next = event.target.value;
          setRaw(next);
          const parsed = Number(next);
          const bad =
            next.trim() === '' ||
            !Number.isFinite(parsed) ||
            (positive && parsed <= 0) ||
            (nonNegative && parsed < 0) ||
            (integer && (!Number.isInteger(parsed) || parsed < 0 || parsed > 65535));
          setInvalid(bad);
          onValidity(bad);
          if (!bad) onChange(parsed);
        }}
      />
      {invalid && <span role="alert">{t('workbench.invalid')}</span>}
    </label>
  );
}

export function MaskWorkbench({
  api,
  initialAsset,
  stepIndex,
  onApply,
  onClose,
  onError,
}: MaskWorkbenchProps) {
  const [state, dispatch] = useReducer(maskEditorReducer, initialAsset, createMaskEditorState);
  const {t} = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const controllers = useRef(new Set<AbortController>());
  const mounted = useRef(true);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState<TcadApiError | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [inputEpoch, setInputEpoch] = useState(0);
  const [transient, setTransient] = useState(false);
  const [pendingImport, setPendingImport] = useState<File | null>(null);
  const [imported, setImported] = useState(false);
  const [invalidFields, setInvalidFields] = useState<Record<string, boolean>>({});
  const [moveX, setMoveX] = useState(0);
  const [moveY, setMoveY] = useState(0);
  const invalid = Object.values(invalidFields).some(Boolean);
  const selected = state.asset.shapes.find(
    (shape) => state.selection.length === 1 && state.selection[0] === shape.id,
  );
  const layer = state.asset.layers.find((item) => item.id === state.activeLayerId);
  const validity = (key: string) => (bad: boolean) =>
    setInvalidFields((previous) => (previous[key] === bad ? previous : {...previous, [key]: bad}));
  useEffect(() => {
    mounted.current = true;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();
    return () => {
      mounted.current = false;
      for (const controller of controllers.current) controller.abort();
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    setInvalidFields((previous) =>
      Object.fromEntries(Object.entries(previous).filter(([key]) => !shapeFieldKeys.includes(key))),
    );
  }, [selected?.id]);
  const discard = () => {
    if (busyRef.current) return;
    if (state.dirty || invalid || transient) setConfirmDiscard(true);
    else onClose();
  };
  const keyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      discard();
    }
    if (event.key === 'Tab') {
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
        ) ?? [],
      ).filter((node) => !node.closest('[inert]') && !node.classList.contains('visually-hidden'));
      const first = focusable[0];
      const last = focusable.at(-1);
      if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === dialogRef.current)
      ) {
        event.preventDefault();
        last?.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || document.activeElement === dialogRef.current)
      ) {
        event.preventDefault();
        first?.focus();
      }
    }
  };
  async function request(operation: (signal: AbortSignal) => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    controllers.current.add(controller);
    try {
      await operation(controller.signal);
    } catch (caught) {
      if (controller.signal.aborted || !mounted.current) return;
      const failure =
        caught instanceof TcadApiError
          ? caught
          : new TcadApiError('unexpected_client_error', {
              code: 'unexpected_client_error',
              status: 0,
            });
      setError(failure);
      onError?.(failure);
    } finally {
      controllers.current.delete(controller);
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const save = () =>
    request(async (signal) => {
      const payload = await api.saveAndApplyMaskAsset({asset: state.asset, stepIndex}, signal);
      if (signal.aborted || !mounted.current) return;
      onApply(payload);
      onClose();
    });
  const importFile = (file: File) =>
    request(async (signal) => {
      const payload = await api.importAndApplyMaskAsset(file, stepIndex, signal);
      if (signal.aborted || !mounted.current) return;
      onApply(payload);
      dispatch({type: 'replaceAsset', asset: payload.asset});
      setInputEpoch((epoch) => epoch + 1);
      setInvalidFields({});
      setImported(true);
    });
  const exportFile = (format: 'json' | 'gds') =>
    request(async (signal) => {
      const blob = await api.exportMaskAsset(state.asset.id, state.asset.revision, format, signal);
      if (signal.aborted || !mounted.current) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${state.asset.id}-r${state.asset.revision}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    });
  const field = (
    key: string,
    value: number,
    onChange: (next: number) => void,
    options: {positive?: boolean; nonNegative?: boolean; integer?: boolean} = {},
  ) => (
    <NumericField
      key={`${inputEpoch}:${key}:${shapeFieldKeys.includes(key) ? selected?.id : ''}`}
      label={t(`workbench.${key}` as TranslationKey)}
      value={value}
      onChange={onChange}
      onValidity={validity(key)}
      {...options}
    />
  );
  const shapeFields =
    selected === undefined
      ? []
      : Object.entries(selected).filter(
          ([key, value]) => typeof value === 'number' && key !== 'id',
        );
  return (
    <div
      className="mask-workbench-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={t('workbench.title')}
      tabIndex={-1}
      ref={dialogRef}
      onKeyDown={keyboard}
    >
      <header className="mask-workbench-header" inert={confirmDiscard ? true : undefined}>
        <h1>{t('workbench.title')}</h1>
        <span>
          {state.asset.id} · {t('workbench.revision', {revision: state.asset.revision})}
        </span>
        <LanguageSwitcher />
        <button
          disabled={busy || state.past.length === 0}
          onClick={() => {
            dispatch({type: 'undo'});
            setInputEpoch((epoch) => epoch + 1);
            setInvalidFields({});
          }}
        >
          {t('workbench.undo')}
        </button>
        <button
          disabled={busy || state.future.length === 0}
          onClick={() => {
            dispatch({type: 'redo'});
            setInputEpoch((epoch) => epoch + 1);
            setInvalidFields({});
          }}
        >
          {t('workbench.redo')}
        </button>
        <button disabled={busy} onClick={() => fileRef.current?.click()}>
          {t('workbench.import')}
        </button>
        <input
          ref={fileRef}
          className="visually-hidden"
          type="file"
          accept=".json,.gds,.oas"
          aria-label={t('workbench.importFile')}
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (file) {
              if (state.dirty || invalid || transient) {
                setPendingImport(file);
                setConfirmDiscard(true);
              } else void importFile(file);
            }
          }}
        />
        <button
          disabled={busy || state.dirty || invalid || state.asset.revision < 1}
          onClick={() => void exportFile('json')}
        >
          {t('workbench.exportJson')}
        </button>
        <button
          disabled={busy || state.dirty || invalid || state.asset.revision < 1}
          onClick={() => void exportFile('gds')}
        >
          {t('workbench.exportGds')}
        </button>
      </header>
      {error && (
        <ErrorNotice
          title={t('error.operationTitle')}
          error={error.code === 'dependency_missing' ? undefined : error}
          message={error.code === 'dependency_missing' ? t('workbench.dependency') : undefined}
        />
      )}
      {imported && <p role="status">{t('workbench.imported')}</p>}
      <div className="mask-workbench-body" inert={busy || confirmDiscard ? true : undefined}>
        <aside className="mask-workbench-tools">
          <h2>{t('workbench.tools')}</h2>
          <div className="mask-tool-grid">
            {(['select', 'rectangle', 'circle', 'hole', 'line', 'polygon'] as const).map((tool) => (
              <button
                key={tool}
                aria-pressed={state.tool === tool}
                onClick={() => dispatch({type: 'setTool', tool})}
              >
                {t(`workbench.${tool}`)}
              </button>
            ))}
          </div>
          <p>{t('workbench.polygonHint')}</p>
          <h2>{t('workbench.layers')}</h2>
          <label className="mask-field">
            {t('workbench.activeLayer')}
            <select
              value={state.activeLayerId}
              onChange={(event) =>
                dispatch({
                  type: 'setActiveLayer',
                  layerId: event.target.value,
                })
              }
            >
              {state.asset.layers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.layer}/{item.datatype})
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => {
              const next = Math.max(0, ...state.asset.layers.map((item) => item.layer)) + 1;
              const id = `layer-${crypto.randomUUID()}`;
              dispatch({
                type: 'addLayer',
                layer: {
                  id,
                  layer: next,
                  datatype: 0,
                  name: `L${next}`,
                  visible: true,
                },
              });
              dispatch({type: 'setActiveLayer', layerId: id});
            }}
          >
            {t('workbench.addLayer')}
          </button>
          {layer && (
            <>
              <label className="mask-field">
                {t('workbench.layerName')}
                <input
                  value={layer.name}
                  onChange={(event) =>
                    dispatch({
                      type: 'patchLayer',
                      id: layer.id,
                      patch: {name: event.target.value},
                    })
                  }
                />
              </label>
              {field(
                'layer',
                layer.layer,
                (value) =>
                  dispatch({
                    type: 'patchLayer',
                    id: layer.id,
                    patch: {layer: value},
                  }),
                {integer: true},
              )}
              {field(
                'datatype',
                layer.datatype,
                (value) =>
                  dispatch({
                    type: 'patchLayer',
                    id: layer.id,
                    patch: {datatype: value},
                  }),
                {integer: true},
              )}
            </>
          )}
          {state.asset.layers.map((item) => (
            <label key={item.id}>
              <input
                type="checkbox"
                checked={item.visible}
                onChange={(event) =>
                  dispatch({
                    type: 'patchLayer',
                    id: item.id,
                    patch: {visible: event.target.checked},
                  })
                }
              />
              {t('workbench.visible')} {item.name}
            </label>
          ))}
          <label>
            <input
              type="checkbox"
              checked={state.gridVisible}
              onChange={(event) => dispatch({type: 'setGrid', gridVisible: event.target.checked})}
            />
            {t('workbench.grid')}
          </label>
          {field('snap', state.snapNm, (snapNm) => dispatch({type: 'setSnap', snapNm}), {
            nonNegative: true,
          })}
        </aside>
        <section className="mask-workbench-canvas">
          <MaskCanvas
            key={inputEpoch}
            state={state}
            dispatch={dispatch}
            onTransientChanged={setTransient}
          />
        </section>
        <aside className="mask-workbench-inspector">
          <label className="mask-field">
            {t('workbench.assetName')}
            <input
              value={state.asset.name}
              onChange={(event) =>
                dispatch({
                  type: 'patchAsset',
                  patch: {name: event.target.value},
                })
              }
            />
          </label>
          {state.asset.boundsNm.map((value, index) =>
            field(`bounds${index}`, value, (next) => {
              const bounds = [...state.asset.boundsNm] as [number, number, number, number];
              bounds[index] = next;
              dispatch({type: 'patchAsset', patch: {boundsNm: bounds}});
            }),
          )}
          <h2>{t('workbench.inspector')}</h2>
          {selected ? (
            <>
              <span>{selected.id}</span>
              <label className="mask-field">
                {t('workbench.shapeLayer')}
                <select
                  value={selected.layerId}
                  onChange={(event) =>
                    dispatch({
                      type: 'patchShape',
                      id: selected.id,
                      patch: {layerId: event.target.value},
                    })
                  }
                >
                  {state.asset.layers.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              {shapeFields.map(([key, value]) =>
                field(
                  key,
                  value as number,
                  (next) =>
                    dispatch({
                      type: 'patchShape',
                      id: selected.id,
                      patch: {[key]: next},
                    }),
                  {
                    positive: ['widthNm', 'heightNm', 'radiusNm'].includes(key),
                  },
                ),
              )}
              {'pointsNm' in selected && (
                <label className="mask-field">
                  {t('workbench.points')}
                  <textarea
                    key={`${selected.id}-${JSON.stringify(selected.pointsNm)}`}
                    defaultValue={JSON.stringify(selected.pointsNm)}
                    onBlur={(event) => {
                      try {
                        const points: unknown = JSON.parse(event.target.value);
                        if (
                          !Array.isArray(points) ||
                          points.length < 2 ||
                          !points.every(
                            (p) =>
                              Array.isArray(p) &&
                              p.length === 2 &&
                              p.every((n) => typeof n === 'number' && Number.isFinite(n)),
                          )
                        )
                          throw new Error('invalid');
                        dispatch({
                          type: 'patchShape',
                          id: selected.id,
                          patch: {
                            pointsNm: points as readonly (readonly [number, number])[],
                          },
                        });
                        validity('points')(false);
                      } catch {
                        validity('points')(true);
                      }
                    }}
                  />
                </label>
              )}
            </>
          ) : (
            <p>{t('workbench.emptySelection')}</p>
          )}
          {state.selection.length > 0 && (
            <>
              {field('moveX', moveX, setMoveX)}
              {field('moveY', moveY, setMoveY)}
              <button
                disabled={invalid}
                onClick={() => dispatch({type: 'moveSelection', dxNm: moveX, dyNm: moveY})}
              >
                {t('workbench.move')}
              </button>
              <button onClick={() => dispatch({type: 'deleteSelection'})}>
                {t('workbench.delete')}
              </button>
            </>
          )}
        </aside>
      </div>
      <footer className="mask-workbench-footer" inert={confirmDiscard ? true : undefined}>
        <p>
          {t('workbench.importHint')} {t('workbench.exportHint')}
        </p>
        <button
          disabled={
            busy ||
            transient ||
            invalid ||
            !state.asset.name.trim() ||
            state.asset.boundsNm[2] <= state.asset.boundsNm[0] ||
            state.asset.boundsNm[3] <= state.asset.boundsNm[1]
          }
          onClick={() => void save()}
        >
          {busy ? t('workbench.busy') : t('workbench.save')}
        </button>
        <button disabled={busy} onClick={discard}>
          {t('workbench.discard')}
        </button>
      </footer>
      {confirmDiscard && (
        <div
          className="mask-discard-confirm"
          role="alertdialog"
          aria-label={t('workbench.discardMessage')}
        >
          <p>{t('workbench.discardMessage')}</p>
          <button
            autoFocus
            onClick={() => {
              setConfirmDiscard(false);
              setPendingImport(null);
            }}
          >
            {t('workbench.cancel')}
          </button>
          <button
            onClick={() => {
              if (pendingImport) {
                const file = pendingImport;
                setPendingImport(null);
                setConfirmDiscard(false);
                void importFile(file);
              } else onClose();
            }}
          >
            {t('workbench.confirm')}
          </button>
        </div>
      )}
    </div>
  );
}
