/**
 * Element Plus carries its own locale bundles, separate from vue-i18n. If one
 * is not wired to the app locale, EP's built-in strings (the table's empty
 * text, a dialog's close aria-label) leak English into a Chinese UI -- the
 * TP-card18 defect.
 *
 * These tests pin both halves of the fix: the choice -> bundle mapping (with the
 * *system* source injectable, so the result never depends on the machine the
 * suite runs on), and that the mapping is reactive over the live language
 * choice -- a switch repaints without a reload.
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import type { Language } from 'element-plus/es/locale'
import en from 'element-plus/es/locale/lang/en'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import type { LanguageChoice } from '../../../preload/types'
import { elementLocale, useElementLocale } from './element'

/** EP types `el` loosely; reach into a known key for the assertions. */
function elText(bundle: Language, path: [string, string]): string {
  const node = (bundle.el as Record<string, Record<string, string>>)[path[0]]
  return node[path[1]]
}

describe('elementLocale', () => {
  it('maps an explicit choice straight to the matching bundle', () => {
    expect(elementLocale('zh-CN')).toBe(zhCn)
    expect(elementLocale('en')).toBe(en)
  })

  it('resolves "system" through the injected system locale, falling back to en', () => {
    // Chinese system -> Chinese bundle.
    expect(elementLocale('system', 'zh-CN')).toBe(zhCn)
    expect(elementLocale('system', 'zh-Hans-CN')).toBe(zhCn)
    // English system -> English bundle.
    expect(elementLocale('system', 'en-GB')).toBe(en)
    // Unknown system language -> en (never an empty bundle).
    expect(elementLocale('system', 'fr-FR')).toBe(en)
    expect(elementLocale('system', 'de-DE')).toBe(en)
    expect(elementLocale('system', '')).toBe(en)
  })

  it('exposes the built-in strings the app actually relies on', () => {
    expect(elText(en, ['table', 'emptyText'])).toBe('No Data')
    expect(elText(zhCn, ['table', 'emptyText'])).toBe('暂无数据')
    expect(elText(en, ['dialog', 'close'])).toBe('Close this dialog')
    expect(elText(zhCn, ['dialog', 'close'])).toBe('关闭此对话框')
  })
})

describe('useElementLocale', () => {
  it('tracks the choice reactively, in place, without a reload', () => {
    const choice = ref<LanguageChoice>('en')
    // Pin the system source so this test is machine-independent, then prove the
    // computed follows the *choice* it was handed.
    const epLocale = useElementLocale(choice, 'en-US')

    expect(epLocale.value).toBe(en)
    const firstRead = epLocale.value

    choice.value = 'zh-CN'
    // Same computed, new bundle: proof the change flowed through the ref, not
    // through a one-shot snapshot taken at startup.
    expect(epLocale.value).toBe(zhCn)
    expect(epLocale.value).not.toBe(firstRead)
    expect(elText(epLocale.value, ['table', 'emptyText'])).toBe('暂无数据')

    choice.value = 'en'
    expect(epLocale.value).toBe(en)
    expect(elText(epLocale.value, ['table', 'emptyText'])).toBe('No Data')
  })

  it('reads the "system" choice through the injected system locale', () => {
    const choice = ref<LanguageChoice>('system')

    // Same live choice, two different system sources -> two different bundles.
    expect(useElementLocale(choice, 'zh-CN').value).toBe(zhCn)
    expect(elText(useElementLocale(choice, 'zh-CN').value, ['table', 'emptyText'])).toBe('暂无数据')
    expect(useElementLocale(choice, 'fr-FR').value).toBe(en)
  })
})
