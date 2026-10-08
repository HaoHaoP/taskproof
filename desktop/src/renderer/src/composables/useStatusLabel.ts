import { useI18n } from 'vue-i18n'

/**
 * A status label that degrades to the raw word rather than to a missing-key path.
 *
 * If the API reports a status this build has no translation for, showing
 * `status.foo` would be worse than showing `foo` -- and showing nothing at all
 * would be the bug this whole contract exists to prevent.
 */
export function useStatusLabel(): (status: string) => string {
  const { t, te } = useI18n()
  return (status: string): string => {
    const key = `status.${status}`
    return te(key) ? t(key) : status
  }
}
