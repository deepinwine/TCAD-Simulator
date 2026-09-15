import type {RuntimeStatus} from '../api/types';
import {useI18n} from '../i18n/I18nContext';
import type {TranslationKey} from '../i18n/catalogs';

const STATUS_KEYS: Record<RuntimeStatus, TranslationKey> = {
  ready: 'status.ready',
  dirty: 'status.dirty',
  running: 'status.running',
  done: 'status.done',
  error: 'status.error',
};

interface StatusBadgeProps {
  status: RuntimeStatus;
}

export function StatusBadge({status}: StatusBadgeProps) {
  const {t} = useI18n();
  const copy = t(STATUS_KEYS[status]);
  return (
    <span className={`status-badge status-${status}`} aria-label={t('status.label', {status: copy})}>
      <span className="status-dot" aria-hidden="true" />
      {copy}
    </span>
  );
}
