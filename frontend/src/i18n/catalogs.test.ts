import {fireEvent, render, screen} from '@testing-library/react';
import {createElement, StrictMode} from 'react';
import {describe, expect, it, vi} from 'vitest';
import {I18nProvider, useI18n} from './I18nContext';
import {detectInitialLocale, en, zhCN} from './catalogs';

describe('translation catalogs', () => {
  it('集中管理创建表单、构建反馈与工作区新增文案', () => {
    expect(zhCN).toMatchObject({'addStep.title': '配置步骤', 'addStep.confirm': '确认添加', 'parameter.applyAndBuild': '应用并构建到此步', 'toolbar.recipeActions': '配方操作', 'workspace.parameterWidth': '参数栏宽度'});
    expect(en).toMatchObject({'addStep.title': 'Configure step', 'addStep.confirm': 'Add step', 'parameter.applyAndBuild': 'Apply and build to this step', 'toolbar.recipeActions': 'Recipe actions', 'workspace.parameterWidth': 'Parameter pane width'});
  });
  it('keeps zh-CN and en keys in exact parity', () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zhCN).sort());
  });

  it('contains the required Chinese interface copy', () => {
    expect(zhCN['toolbar.runAll']).toBe('全部运行');
    expect(zhCN['parameter.empty']).toBe('选择一个工艺步骤以查看参数');
    expect(zhCN['error.network']).toContain('连接');
  });
});

describe('detectInitialLocale', () => {
  it('prefers a valid stored locale', () => {
    expect(detectInitialLocale('en', ['zh-CN'])).toBe('en');
    expect(detectInitialLocale('zh-CN', ['en-US'])).toBe('zh-CN');
  });

  it('falls back to browser language and then English', () => {
    expect(detectInitialLocale(null, ['fr-FR', 'zh-Hans'])).toBe('zh-CN');
    expect(detectInitialLocale('invalid', ['en-US'])).toBe('en');
    expect(detectInitialLocale(null, [])).toBe('en');
  });
});

function TranslationProbe() {
  const {locale, setLocale, t} = useI18n();
  return createElement(
    'div',
    undefined,
    createElement('output', {'data-testid': 'locale'}, locale),
    createElement(
      'output',
      {'data-testid': 'translation'},
      t('viewer.hitPoint', {name: '{SiO2}', point: '{1, 2, 3}'}),
    ),
    createElement('button', {type: 'button', onClick: () => setLocale('en')}, 'switch'),
  );
}

describe('I18nProvider', () => {
  it('在 StrictMode 初始渲染时不写入存储，切换时只写一次', () => {
    const setItem = vi.spyOn(window.localStorage, 'setItem');
    render(
      createElement(
        StrictMode,
        undefined,
        createElement(I18nProvider, undefined, createElement(TranslationProbe)),
      ),
    );

    expect(screen.getByTestId('locale')).toHaveTextContent('zh-CN');
    expect(screen.getByTestId('translation')).toHaveTextContent('{SiO2} · 命中点 ({1, 2, 3})');
    expect(setItem).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', {name: 'switch'}));

    expect(screen.getByTestId('locale')).toHaveTextContent('en');
    expect(screen.getByTestId('translation')).toHaveTextContent('{SiO2} · hit point ({1, 2, 3})');
    expect(setItem).toHaveBeenCalledTimes(1);
    expect(setItem).toHaveBeenCalledWith('tcad.locale.v1', 'en');
  });
});
