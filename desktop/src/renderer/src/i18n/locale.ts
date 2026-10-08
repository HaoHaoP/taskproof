/**
 * Locale resolution, kept free of any vue-i18n import so it stays pure and
 * testable without a DOM.
 */
import type { LanguageChoice } from '../../../preload/types'

export const SUPPORTED = ['en', 'zh-CN'] as const
export type SupportedLocale = (typeof SUPPORTED)[number]

/** System locale -> a supported one; anything else falls back to `en`. */
export function resolveLocale(
  choice: LanguageChoice,
  system: string = typeof navigator === 'undefined' ? 'en' : navigator.language
): SupportedLocale {
  if (choice !== 'system') return choice
  return system.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en'
}
