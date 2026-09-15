import {useI18n} from '../i18n/I18nContext';

export function LanguageSwitcher() {
  const {locale, setLocale, t} = useI18n();
  return (
    <div className="language-switcher" role="group" aria-label={t('language.label')}>
      <button
        type="button"
        className="language-switcher-button"
        aria-pressed={locale === 'zh-CN'}
        onClick={() => setLocale('zh-CN')}
      >
        {t('language.zh')}
      </button>
      <button
        type="button"
        className="language-switcher-button"
        aria-pressed={locale === 'en'}
        onClick={() => setLocale('en')}
      >
        {t('language.en')}
      </button>
    </div>
  );
}
