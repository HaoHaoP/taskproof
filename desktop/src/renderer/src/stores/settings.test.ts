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
import type { DesktopSettings } from '../../../preload/types'

const BASE: DesktopSettings = {
  theme: 'dark',
  language: 'system',
  poll: '2s',
  workspace: '',
  taskproofPath: ''
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
})
