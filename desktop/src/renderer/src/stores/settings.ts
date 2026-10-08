/**
 * Renderer-side view of the desktop settings.
 *
 * The main process owns `settings.json` and is the source of truth; this store
 * only mirrors it and re-applies the two things the renderer owns the effects
 * of (the theme attribute and the locale).
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  DesktopSettings,
  LanguageChoice,
  LaunchMode,
  PollChoice,
  PortMode,
  ThemeChoice
} from '../../../preload/types'
import { setLocale } from '../i18n'

/** The booleans that back the desktop-integration switches. */
type FlagKey = 'notifyFail' | 'notifyDone' | 'dockBadge' | 'tray' | 'autostart'

const FALLBACK: DesktopSettings = {
  theme: 'dark',
  language: 'system',
  poll: '2s',
  workspace: '',
  taskproofPath: '',
  portMode: 'auto',
  port: 8787,
  launch: 'auto',
  notifyFail: false,
  notifyDone: false,
  dockBadge: false,
  tray: false,
  autostart: false
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<DesktopSettings>({ ...FALLBACK })
  const version = ref('')

  function applyTheme(choice: ThemeChoice): void {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const dark = choice === 'dark' || (choice === 'system' && prefersDark)
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    // Element Plus keys its own dark variables off this class.
    document.documentElement.classList.toggle('dark', dark)
  }

  async function load(): Promise<void> {
    const tp = window.tp
    if (tp) {
      settings.value = await tp.settings.get()
      version.value = await tp.app.version()
    }
    applyTheme(settings.value.theme)
    setLocale(settings.value.language)
  }

  /**
   * Writes go through the main process, which is the source of truth, but the
   * response is a snapshot of the *whole* file at the time it was read. Two
   * settings changed in quick succession therefore race: the earlier write's
   * response can land last and put its stale copy of the other field back on
   * screen (click "light" and then "off", and the theme can snap back to dark
   * while the file says light). The sequence number makes the newest write the
   * only one allowed to repaint.
   */
  let writeSeq = 0

  async function persist(patch: Partial<DesktopSettings>): Promise<void> {
    const seq = ++writeSeq
    settings.value = { ...settings.value, ...patch }
    applyTheme(settings.value.theme)
    setLocale(settings.value.language)
    const tp = window.tp
    if (!tp) return
    const saved = await tp.settings.set(patch)
    if (seq !== writeSeq) return
    settings.value = saved
    applyTheme(settings.value.theme)
    setLocale(settings.value.language)
  }

  function setTheme(theme: ThemeChoice): void {
    void persist({ theme })
  }

  function setLanguage(language: LanguageChoice): void {
    void persist({ language })
  }

  function setPoll(poll: PollChoice): void {
    void persist({ poll })
  }

  function setPortMode(portMode: PortMode): void {
    void persist({ portMode })
  }

  function setPort(port: number): void {
    void persist({ port })
  }

  function setLaunch(launch: LaunchMode): void {
    void persist({ launch })
  }

  function setTaskproofPath(taskproofPath: string): void {
    void persist({ taskproofPath })
  }

  /**
   * The desktop-integration switches. They persist now; the tray, Dock badge,
   * notifications and login item that read them are a later card -- but a
   * switch that only lived in memory would be decoration.
   */
  function setFlag(key: FlagKey, value: unknown): void {
    const patch: Partial<DesktopSettings> = {}
    patch[key] = Boolean(value)
    void persist(patch)
  }

  return {
    settings,
    version,
    load,
    persist,
    setTheme,
    setLanguage,
    setPoll,
    setPortMode,
    setPort,
    setLaunch,
    setTaskproofPath,
    setFlag,
    applyTheme
  }
})
