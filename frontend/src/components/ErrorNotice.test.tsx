import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';
import {TcadApiError} from '../api/client';
import {I18nProvider} from '../i18n/I18nContext';
import {ErrorNotice} from './ErrorNotice';

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

function renderNotice(code: string, locale: 'zh-CN' | 'en' = 'zh-CN') {
  window.localStorage.setItem('tcad.locale.v1', locale);
  render(
    <I18nProvider>
      <ErrorNotice
        title="Test error"
        error={new TcadApiError('Authorization: Bearer secret-token', {status: 500, code})}
      />
    </I18nProvider>,
  );
  return screen.getByRole('alert');
}

describe('ErrorNotice error-code boundary', () => {
  it.each(['constructor', 'toString', '__proto__'])(
    'treats prototype code %s as an unknown error without throwing', code => {
      const alert = renderNotice(code);
      expect(alert).toHaveTextContent('发生未预期的错误。');
      expect(alert).not.toHaveTextContent('Authorization: Bearer secret-token');
    },
  );

  it.each([
    ['worker_timeout', '工作进程超时，请稍后重试。', 'The worker timed out. Please try again shortly.'],
    ['restore_failed', '无法恢复所选快照。', 'Unable to restore the selected snapshot.'],
    ['snapshot_unavailable', '所选快照暂不可用。', 'The selected snapshot is currently unavailable.'],
  ])('renders %s with stable translations in both locales', (code, zh, en) => {
    expect(renderNotice(code)).toHaveTextContent(zh);
    cleanup();
    expect(renderNotice(code, 'en')).toHaveTextContent(en);
  });
});
