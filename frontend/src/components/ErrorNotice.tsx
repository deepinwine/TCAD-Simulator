import type {TcadApiError} from '../api/client';
import {type I18nContextValue, useI18n} from '../i18n/I18nContext';
import type {TranslationKey} from '../i18n/catalogs';

interface ErrorNoticeProps {
  title: string;
  message?: string;
  error?: TcadApiError;
  parameterPath?: string;
  suggestion?: string;
  trustedSuggestion?: boolean;
  rolledBack?: boolean;
  actionLabel?: string;
  onAction?(): void;
}

const knownErrorKeys: Record<string, TranslationKey> = {
  network_error: 'error.network',
  invalid_json: 'error.invalidJson',
  unexpected_json_response: 'error.unexpectedJson',
  binary_request_failed: 'error.binaryRequest',
  binary_read_failed: 'error.binaryRead',
  unexpected_client_error: 'error.unexpectedClient',
  invalid_mask: 'error.invalidMask',
  invalid_recipe: 'error.invalidRecipe',
  undo_unavailable: 'error.undoUnavailable',
  no_valid_snapshot: 'error.noValidSnapshot',
  missing_mesh: 'error.missingMesh',
  stale_revision: 'error.staleRevision',
  internal_error: 'error.internal',
  failed: 'error.failed',
  worker_timeout: 'error.workerTimeout',
  restore_failed: 'error.restoreFailed',
  snapshot_unavailable: 'error.snapshotUnavailable',
  worker_died: 'error.failed',
  worker_send_failed: 'error.failed',
  worker_poll_failed: 'error.failed',
  worker_recv_failed: 'error.failed',
  canonical_update_failed: 'error.failed',
  invalid_snapshot: 'error.snapshotUnavailable',
  engine_missing: 'error.missingMesh',
  unsupported_step: 'error.failed',
  unsupported_geometry: 'error.missingMesh',
  unsupported_material: 'error.failed',
  geometry_backend: 'error.internal',
  no_geometry: 'error.missingMesh',
  step_failed: 'error.failed',
  unknown_backend: 'error.failed',
  unknown_demo: 'error.invalidRecipe',
  unknown_step: 'error.invalidRecipe',
  invalid_step: 'error.invalidRecipe',
  unknown_parameter: 'error.invalidRecipe',
  invalid_parameter: 'error.invalidRecipe',
  invalid_draft: 'error.invalidDraft',
  empty_recipe: 'error.invalidRecipe',
  unknown_material_mesh: 'error.missingMesh',
  no_recipe: 'error.invalidRecipe',
  invalid_database: 'error.internal',
};

function safeDiagnosticText(value: string): string | null {
  return /^[a-z][a-z0-9_]{0,63}$/i.test(value) ? value : null;
}

function safeParameterPath(value: string | undefined): string | undefined {
  return value !== undefined && /^[a-z][a-z0-9_.[\]"-]{0,127}$/i.test(value)
    ? value
    : undefined;
}

export function errorPresentation(
  error: TcadApiError,
  t: I18nContextValue['t'],
): {message: string; diagnostic?: string} {
  const knownKey = error.code !== undefined && Object.hasOwn(knownErrorKeys, error.code)
    ? knownErrorKeys[error.code]
    : undefined;
  if (knownKey !== undefined) return {message: t(knownKey)};

  const diagnostic: string[] = [];
  const code = error.code === undefined ? null : safeDiagnosticText(error.code);
  if (code !== null) diagnostic.push(`code: ${code}`);
  if (typeof error.details === 'object' && error.details !== null && !Array.isArray(error.details)) {
    const details = error.details as Record<string, unknown>;
    for (const key of ['index', 'stepIndex']) {
      const value = details[key];
      if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0) {
        diagnostic.push(`${key}: ${value}`);
      }
    }
  }
  return {
    message: t('error.unknown'),
    ...(diagnostic.length > 0 ? {diagnostic: diagnostic.join('\n')} : {}),
  };
}

export function ErrorNotice({
  title,
  message,
  error,
  parameterPath,
  suggestion,
  trustedSuggestion = false,
  rolledBack,
  actionLabel,
  onAction,
}: ErrorNoticeProps) {
  const {t} = useI18n();
  const presentation = error === undefined
    ? {message: message ?? ''}
    : errorPresentation(error, t);
  const displayedParameterPath = error === undefined
    ? parameterPath
    : safeParameterPath(parameterPath);
  const displayedSuggestion = error === undefined || trustedSuggestion
    ? suggestion
    : undefined;
  return (
    <div className="error-notice" role="alert">
      <span className="error-mark" aria-hidden="true">!</span>
      <div>
        <h2>{title}</h2>
        <p>{presentation.message}</p>
        {displayedParameterPath && <p>{t('error.parameterPath', {path: displayedParameterPath})}</p>}
        {displayedSuggestion && <p>{t('error.suggestion', {suggestion: displayedSuggestion})}</p>}
        {rolledBack === false && (
          <p className="rollback-warning">{t('error.rollbackWarning')}</p>
        )}
        {rolledBack === true && (
          <p className="rollback-confirmation">{t('error.rollbackConfirmation')}</p>
        )}
        {presentation.diagnostic !== undefined && (
          <details className="error-details">
            <summary>{t('error.details')}</summary>
            <pre>{presentation.diagnostic}</pre>
          </details>
        )}
        {actionLabel !== undefined && onAction !== undefined && (
          <button type="button" onClick={onAction}>{actionLabel}</button>
        )}
      </div>
    </div>
  );
}
