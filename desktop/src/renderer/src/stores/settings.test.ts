/**
 * The settings store writes through the main process, which answers with a
 * snapshot of the whole file. These tests pin the ordering rule that keeps two
 * quick clicks from undoing each other on screen.
 *
 * The failure they reproduce is a real one: clicking "poll: off" and then
 * "theme: light" left the window dark while settings.json said light, because
 * the earlier write's response (a snapshot taken before the theme was written)
 * landed last and was painted.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../i18n', () => ({ setLocale: vi.fn() }))

import { useSettingsStore } from './settings'
import { DEFAULT_COLUMN_CAPS, type DesktopSettings } from '../../../preload/types'

const BASE: DesktopSettings = {
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
  autostart: false,
  columnCaps: { ...DEFAULT_COLUMN_CAPS }
}

interface Pending {
  patch: Partial<DesktopSettings>
  resolve: (settings: DesktopSettings) => void
}

/** Every theme the store painted, in order, so a revert is visible. */
let painted: string[] = []
let pending: Pending[] = []

function installHost(): void {
  painted = []
  pending = []
  ;(globalThis as unknown as { document: unknown }).document = {
    documentElement: {
      setAttribute: (_name: string, value: string) => painted.push(value),
      classList: { toggle: () => {} }
    }
  }
  ;(globalThis as unknown as { window: unknown }).window = {
    matchMedia: () => ({ matches: false }),
    tp: {
      settings: {
        get: async () => ({ ...BASE }),
        // Resolved by hand so a test can make an early write answer late.
        set: (patch: Partial<DesktopSettings>) =>
          new Promise<DesktopSettings>((resolve) => pending.push({ patch, resolve }))
      },
      app: { version: async () => '0.1.0' }
    }
  }
}

/** Let the queued microtasks of the store's `await` chains run. */
async function settle(): Promise<void> {
  for (let i = 0; i < 4; i += 1) await Promise.resolve()
}

describe('settings persist ordering', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    installHost()
  })

  it('paints the newest click when an earlier write answers last', async () => {
    const store = useSettingsStore()
    store.setPoll('off') // write 1
    store.setTheme('light') // write 2
    await settle()
    expect(pending).toHaveLength(2)

    // Write 2 answers first, as the file looks after both writes.
    pending[1].resolve({ ...BASE, theme: 'light', poll: 'off' })
    await settle()
    // Write 1 answers last, carrying a snapshot from before write 2 landed.
    pending[0].resolve({ ...BASE, theme: 'dark', poll: 'off' })
    await settle()

    // The stale snapshot must not be repainted, and must not win.
    expect(painted.at(-1)).toBe('light')
    expect(store.settings.theme).toBe('light')
    expect(store.settings.poll).toBe('off')
  })

  it('paints a change immediately, without waiting for the write', async () => {
    const store = useSettingsStore()
    store.setTheme('light')
    // No resolve() yet: the click has to show up straight away.
    expect(painted.at(-1)).toBe('light')
    expect(store.settings.theme).toBe('light')
    pending[0].resolve({ ...BASE, theme: 'light' })
    await settle()
    expect(store.settings.theme).toBe('light')
  })

  it('adopts the file when the newest write is the one that answers', async () => {
    const store = useSettingsStore()
    store.setTheme('light')
    await settle()
    // The main process may have more in it than we sent (another window, a
    // field we do not write from here). The newest answer is authoritative.
    pending[0].resolve({ ...BASE, theme: 'light', workspace: '/Users/someone/.taskproof' })
    await settle()
    expect(store.settings.workspace).toBe('/Users/someone/.taskproof')
  })

  it('writes a desktop-integration switch through to the main process', async () => {
    const store = useSettingsStore()
    // Every switch must reach settings.json -- a switch that only repaints here
    // would look alive while doing nothing. The patch carries just that field.
    store.setFlag('notifyFail', true)
    store.setFlag('tray', true)
    await settle()
    expect(pending.map((p) => p.patch)).toEqual([{ notifyFail: true }, { tray: true }])
    // And it shows on screen without waiting for the write to come back.
    expect(store.settings.notifyFail).toBe(true)
    expect(store.settings.tray).toBe(true)
  })

  it('writes a per-column display cap, keeping the other columns', async () => {
    const store = useSettingsStore()
    store.setColumnCap('done', 3)
    await settle()
    expect(pending[0].patch).toEqual({
      columnCaps: { ...DEFAULT_COLUMN_CAPS, done: 3 }
    })
    // The change shows immediately, before the write answers.
    expect(store.settings.columnCaps.done).toBe(3)
    expect(store.settings.columnCaps.cancelled).toBe(10)
  })

  it('coerces a switch payload to a boolean before it hits the patch', async () => {
    const store = useSettingsStore()
    // Element Plus' switch emits `boolean | string | number`; the store must not
    // leak a truthy string into settings.json.
    store.setFlag('dockBadge', 'false')
    await settle()
    expect(pending[0].patch).toEqual({ dockBadge: true })
    expect(store.settings.dockBadge).toBe(true)
  })
})
