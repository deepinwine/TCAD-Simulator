import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  detectInitialLocale,
  en,
  type Locale,
  type TranslationKey,
  zhCN,
} from './catalogs';

const STORAGE_KEY = 'tcad.locale.v1';
const catalogs: Record<Locale, Record<TranslationKey, string>> = {
  'zh-CN': zhCN,
  en,
};

export interface I18nContextValue {
  locale: Locale;
  setLocale(locale: Locale): void;
  t(key: TranslationKey, params?: Record<string, string | number>): string;
}

function translate(
  locale: Locale,
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  const template = catalogs[locale][key];
  if (template === undefined) {
    if (import.meta.env.DEV) throw new Error(`Missing translation: ${locale}.${key}`);
    return key;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params?.[name] === undefined ? match : String(params[name])
  ));
}

const defaultValue: I18nContextValue = {
  locale: 'zh-CN',
  setLocale: () => undefined,
  t: (key, params) => translate('zh-CN', key, params),
};

const I18nContext = createContext<I18nContextValue>(defaultValue);

function storedLocale(): string | null {
  try {
    return window.localStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

export function I18nProvider({children}: {children: ReactNode}) {
  const [locale, setLocaleState] = useState<Locale>(() => detectInitialLocale(
    storedLocale(),
    typeof navigator === 'undefined' ? [] : navigator.languages,
  ));
  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage?.setItem(STORAGE_KEY, next);
    } catch {
      // 浏览器禁用存储时，语言仍在当前会话内生效。
    }
  }, []);
  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>) => translate(locale, key, params),
    [locale],
  );
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  const value = useMemo(() => ({locale, setLocale, t}), [locale, setLocale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}

export type {Locale, TranslationKey} from './catalogs';
