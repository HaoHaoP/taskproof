/**
 * zh-CN + en, following the system locale, falling back to **en**.
 *
 * Only UI chrome is translated. Task briefs and summaries are user data and are
 * never sent through the translator.
 */
import { createI18n } from 'vue-i18n'
import type { LanguageChoice } from '../../../preload/types'
import en from './en'
import { resolveLocale } from './locale'
import zhCN from './zh-CN'

export { SUPPORTED, resolveLocale, type SupportedLocale } from './locale'

export const i18n = createI18n({
  legacy: false,
  locale: resolveLocale('system'),
  fallbackLocale: 'en',
  messages: { en, 'zh-CN': zhCN }
})

/** Switching at runtime, without a reload. */
export function setLocale(choice: LanguageChoice): void {
  i18n.global.locale.value = resolveLocale(choice)
}
