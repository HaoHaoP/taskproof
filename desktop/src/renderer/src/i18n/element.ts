/**
 * Element Plus locale wiring.
 *
 * EP keeps its own built-in strings -- the table's empty state, a dialog's
 * close-button aria-label, a message box's buttons -- in its *own* locale
 * bundles, completely separate from vue-i18n. Without one wired up it falls
 * back to its bundled English, so a Chinese UI leaks "No Data" (TP-card18).
 *
 * The bundle has to be *reactive*: the settings page switches language at
 * runtime, and `app.use(ElementPlus, { locale })` bakes the bundle in at
 * install time (a switch would then need a reload). So the root renders
 * `<el-config-provider :locale="epLocale">` around the app, and `epLocale` is a
 * computed over the *language choice* the settings store already flips.
 *
 * The choice is what is tracked -- not the resolved locale -- because "follow
 * the system" has to be re-resolved against the system language. That system
 * language is an *injectable* source (`resolveLocale`'s second argument): tests
 * pass a fixed one so they never depend on the machine they run on, and the
 * app passes nothing so the real system language is used.
 */
import { computed, toValue, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import type { Language } from 'element-plus/es/locale'
import en from 'element-plus/es/locale/lang/en'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import type { LanguageChoice } from '../../../preload/types'
import { resolveLocale, type SupportedLocale } from './locale'

/** The supported app locale -> the matching EP bundle. */
const BUNDLES: Record<SupportedLocale, Language> = {
  en,
  'zh-CN': zhCn
}

/**
 * The EP locale bundle for a language *choice*. A `system` choice is resolved
 * through `systemLocale` (defaulting to the real system language), so a caller
 * -- or a test -- can pin what "follow the system" means.
 */
export function elementLocale(choice: LanguageChoice, systemLocale?: string): Language {
  return BUNDLES[resolveLocale(choice, systemLocale)]
}

/**
 * The EP locale bundle for the *current* language choice, as a reactive value.
 * Feed it to `<el-config-provider :locale="epLocale">` at the app root so every
 * EP component in the tree -- including teleported dialogs -- follows the
 * language switch without a reload.
 *
 * `choice` is a reactive source (the settings store's `language` in the app);
 * `systemLocale` is injectable for tests and defaults to the real system
 * language.
 */
export function useElementLocale(
  choice: MaybeRefOrGetter<LanguageChoice>,
  systemLocale?: string
): ComputedRef<Language> {
  return computed(() => elementLocale(toValue(choice), systemLocale))
}
