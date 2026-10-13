/**
 * Card 78 -- the renderer opened in a plain browser host (no `window.tp`).
 *
 * The pure half is exercised directly: the host check, the API base resolver
 * and the localStorage settings mirror all take injected `tp` / `location` /
 * `storage` inputs, so they run under the node test environment with no DOM.
 * The half that is a markup or script invariant -- which settings sections a
 * browser hides, how About degrades, and crucially that the *desktop* paths are
 * untouched -- is pinned by reading the SFC / store text, following the
 * `filterQuery.test.ts` house pattern.
 */
import { readFileSync } from 'node:fs'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_PORT,
  FALLBACK,
  SETTINGS_STORAGE_KEY,
  hasDesktopHost,
  mergeSettings,
  readSettings,
  resolveApiBase,
  type SettingsStorage
} from './platform'
import {
  CAP_MAX,
  CAP_MIN,
  COLUMN_CAP_KEYS,
  DEFAULT_COLUMN_CAPS,
  type TpApi
} from '../../preload/types'
import en from './i18n/en'
import zhCN from './i18n/zh-CN'

const fakeTp = {} as unknown as TpApi

afterEach(() => vi.unstubAllGlobals())

describe('hasDesktopHost', () => {
  it('reads the default window.tp as the host bridge', () => {
    vi.stubGlobal('window', { tp: fakeTp })
    expect(hasDesktopHost()).toBe(true)
    // A plain browser page has no bridge at all.
    vi.stubGlobal('window', { tp: undefined })
    expect(hasDesktopHost()).toBe(false)
  })

  it('reads an explicitly injected host too, so the check stays pure', () => {
    expect(hasDesktopHost(fakeTp)).toBe(true)
  })
})

const HTTP = { protocol: 'http:', origin: 'http://board.test:9100', search: '' }
const HTTPS = { protocol: 'https:', origin: 'https://board.example.test', search: '' }

describe('resolveApiBase', () => {
  it("prefers the desktop host's child port", () => {
    expect(
      resolveApiBase({
        tpStatus: { state: 'ready', port: 51234, workspace: '', detail: '' },
        location: HTTP
      })
    ).toBe('http://127.0.0.1:51234')
  })

  it('uses the page origin when the page itself is served over http', () => {
    expect(resolveApiBase({ tpStatus: null, location: HTTP })).toBe(HTTP.origin)
  })

  it('uses the page origin when the page is served over https', () => {
    expect(resolveApiBase({ tpStatus: null, location: HTTPS })).toBe(HTTPS.origin)
  })

  it('keeps the ?port= override for a non-http page (file:// / dev server)', () => {
    expect(
      resolveApiBase({
        tpStatus: null,
        location: { protocol: 'file:', origin: 'null', search: '?port=9999' }
      })
    ).toBe('http://127.0.0.1:9999')
  })

  it('falls back to the default loopback port for a non-http page with no override', () => {
    expect(
      resolveApiBase({
        tpStatus: null,
        location: { protocol: 'file:', origin: 'null', search: '' }
      })
    ).toBe(`http://127.0.0.1:${DEFAULT_PORT}`)
    expect(DEFAULT_PORT).toBe(8787)
  })

  it('treats a missing location as the loopback fallback (node / no DOM)', () => {
    expect(resolveApiBase({ tpStatus: null })).toBe(`http://127.0.0.1:${DEFAULT_PORT}`)
    expect(resolveApiBase({ tpStatus: null, location: null })).toBe(
      `http://127.0.0.1:${DEFAULT_PORT}`
    )
  })

  it('ignores a host status that has no port yet', () => {
    expect(
      resolveApiBase({
        tpStatus: { state: 'starting', port: null, workspace: '', detail: '' },
        location: HTTP
      })
    ).toBe(HTTP.origin)
  })
})

/** A Map-backed localStorage stand-in; `data` is exposed for write assertions. */
function fakeStorage(
  initial: Record<string, string> = {}
): SettingsStorage & { data: Record<string, string> } {
  const data: Record<string, string> = { ...initial }
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value
    }
  }
}

/** Storage holding one JSON-encoded settings value. */
function stored(value: unknown): SettingsStorage {
  return fakeStorage({ [SETTINGS_STORAGE_KEY]: JSON.stringify(value) })
}

describe('readSettings', () => {
  it('returns the code defaults when there is no storage at all', () => {
    expect(readSettings()).toEqual(FALLBACK)
    expect(readSettings(null)).toEqual(FALLBACK)
  })

  it('returns the defaults when the mirror key is absent', () => {
    expect(readSettings(fakeStorage())).toEqual(FALLBACK)
  })

  it('returns the defaults on unparseable JSON', () => {
    expect(readSettings(fakeStorage({ [SETTINGS_STORAGE_KEY]: '{not json' }))).toEqual(FALLBACK)
  })

  it('returns the defaults when the stored value is not a settings object', () => {
    for (const raw of ['5', '"dark"', 'null', '[1,2,3]']) {
      expect(readSettings(fakeStorage({ [SETTINGS_STORAGE_KEY]: raw })), raw).toEqual(FALLBACK)
    }
  })

  it('accepts whitelisted theme / language / poll values', () => {
    const out = readSettings(stored({ theme: 'light', language: 'en', poll: 'off' }))
    expect(out.theme).toBe('light')
    expect(out.language).toBe('en')
    expect(out.poll).toBe('off')
  })

  it('falls back field by field, so one bad value never discards the rest', () => {
    const out = readSettings(stored({ theme: 'light', language: 'fr', poll: '5s' }))
    expect(out.theme).toBe('light')
    expect(out.language).toBe(FALLBACK.language)
    expect(out.poll).toBe(FALLBACK.poll)
  })

  it('keeps only declared, in-range integer column caps', () => {
    const out = readSettings(
      stored({
        columnCaps: {
          running: 5, // valid integer
          verifying: 2.5, // a float is not a cap
          done: CAP_MIN, // 0 is the lower bound and must be kept, not treated as "missing"
          cancelled: CAP_MAX, // 200 is the upper bound
          blocked: -1, // below the range
          abnormal: '5', // the wrong type
          rogue: 7 // not a declared column key
        }
      })
    )
    expect(out.columnCaps.running).toBe(5)
    expect(out.columnCaps.verifying).toBe(DEFAULT_COLUMN_CAPS.verifying)
    expect(out.columnCaps.done).toBe(0)
    expect(out.columnCaps.cancelled).toBe(200)
    expect(out.columnCaps.blocked).toBe(DEFAULT_COLUMN_CAPS.blocked)
    expect(out.columnCaps.abnormal).toBe(DEFAULT_COLUMN_CAPS.abnormal)
    expect('rogue' in out.columnCaps).toBe(false)
  })

  it('exposes exactly the declared column keys after a read', () => {
    const out = readSettings(stored({ columnCaps: { done: 3 } }))
    expect(Object.keys(out.columnCaps).sort()).toEqual([...COLUMN_CAP_KEYS].sort())
  })
})

describe('mergeSettings', () => {
  it('merges a patch into the stored mirror and writes the whole file back', () => {
    const storage = fakeStorage({ [SETTINGS_STORAGE_KEY]: JSON.stringify({ theme: 'light' }) })
    const next = mergeSettings(storage, { poll: 'off' })
    expect(next.theme).toBe('light')
    expect(next.poll).toBe('off')
    // The write is the whole file, and a reload reads back exactly that value.
    expect(JSON.parse(storage.data[SETTINGS_STORAGE_KEY])).toEqual(next)
    expect(readSettings(storage)).toEqual(next)
  })

  it('shallow-merges columnCaps so one column does not wipe the others', () => {
    const storage = fakeStorage({
      [SETTINGS_STORAGE_KEY]: JSON.stringify({ columnCaps: { done: 3 } })
    })
    const next = mergeSettings(storage, { columnCaps: { cancelled: 5 } })
    expect(next.columnCaps.done).toBe(3)
    expect(next.columnCaps.cancelled).toBe(5)
    expect(next.columnCaps.running).toBe(DEFAULT_COLUMN_CAPS.running)
  })

  it('never throws when the storage refuses the write (quota / private mode)', () => {
    const storage: SettingsStorage = {
      getItem: () => null,
      setItem: () => {
        throw new Error('QuotaExceededError')
      }
    }
    expect(() => mergeSettings(storage, { theme: 'light' })).not.toThrow()
    expect(mergeSettings(storage, { theme: 'light' }).theme).toBe('light')
  })

  it('merges in memory even with no storage (defaults plus the patch)', () => {
    const next = mergeSettings(null, { language: 'en' })
    expect(next.language).toBe('en')
    expect(next.theme).toBe(FALLBACK.theme)
  })
})

const settingsStore = readFileSync(new URL('./stores/settings.ts', import.meta.url), 'utf-8')
const boardStore = readFileSync(new URL('./stores/board.ts', import.meta.url), 'utf-8')
const settingsView = readFileSync(new URL('./views/SettingsView.vue', import.meta.url), 'utf-8')
const matrixView = readFileSync(new URL('./views/MatrixView.vue', import.meta.url), 'utf-8')
const aboutDialog = readFileSync(new URL('./components/AboutDialog.vue', import.meta.url), 'utf-8')

describe('settings store: the desktop path stays byte-for-byte (card 78)', () => {
  it('keeps the main-process read/write and the write-sequence guard unchanged', () => {
    expect(settingsStore).toContain('settings.value = await tp.settings.get()')
    expect(settingsStore).toContain('version.value = await tp.app.version()')
    expect(settingsStore).toContain('const saved = await tp.settings.set(patch)')
    expect(settingsStore).toContain('if (seq !== writeSeq) return')
  })

  it('reads and writes the localStorage mirror only on the no-tp branch', () => {
    expect(settingsStore).toContain('settings.value = readSettings(settingsStorage())')
    expect(settingsStore).toContain('settings.value = mergeSettings(settingsStorage(), patch)')
    expect(settingsStore).toMatch(/if \(!tp\) \{\s*settings\.value = mergeSettings\(settingsStorage\(\), patch\)\s*return\s*\}/)
  })
})

describe('board store: shared base resolver, restart only with a host (card 78)', () => {
  it('resolves the base URL through the pure resolver from platform.ts', () => {
    expect(boardStore).toContain("import { resolveApiBase } from '../platform'")
    expect(boardStore).toContain('resolveApiBase({ tpStatus: status, location })')
    expect(boardStore).toContain('resolveApiBase({ tpStatus: null, location })')
  })

  it('only restarts the child process when a desktop host is present', () => {
    const retry = boardStore.slice(
      boardStore.indexOf('async function retry'),
      boardStore.indexOf('async function watchService')
    )
    expect(retry).toContain('const tp = window.tp')
    expect(retry).toContain('if (tp) {')
    expect(retry).toContain('await tp.service.restart()')
    // The old unguarded optional-chain call is the defect itself.
    expect(boardStore).not.toContain('window.tp?.service.restart()')
  })

  it('records the API version from /api/health only without a host', () => {
    expect(boardStore).toContain('if (!window.tp) version.value = health.version')
  })
})

describe('SettingsView hides the host-only groups in a browser (card 78)', () => {
  it('gates the service / diagnostics / desktop-integration sections on hasHost', () => {
    expect(settingsView).toContain('const hasHost = hasDesktopHost()')
    for (const key of ['service', 'diagnostics', 'desktop']) {
      expect(settingsView, key).toMatch(
        new RegExp(
          `<section v-if="hasHost" class="setgroup">\\s*<h4>\\{\\{ t\\('settings\\.${key}'\\) \\}\\}</h4>`
        )
      )
    }
  })

  it('keeps the appearance and about groups visible without a host', () => {
    expect(settingsView).toMatch(
      /<section class="setgroup">\s*<h4>\{\{ t\('settings\.appearance'\) \}\}<\/h4>/
    )
    expect(settingsView).toMatch(
      /<section class="setgroup">\s*<h4>\{\{ t\('settings\.about'\) \}\}<\/h4>/
    )
  })

  it('shows a browser note explaining what is hidden', () => {
    expect(settingsView).toContain(
      '<p v-if="!hasHost" class="sub browser-note">{{ t(\'settings.browserNote\') }}</p>'
    )
  })

  it('falls back to the API version for the read-only version row', () => {
    expect(settingsView).toContain("settings.version || board.version || '0.1.0'")
  })

  it('keeps the matrix column-cap control (the fourth browser setting) ungated', () => {
    expect(matrixView).toContain('settings.setColumnCap(key, command)')
    expect(matrixView).not.toContain('hasDesktopHost')
  })
})

describe('AboutDialog degrades without the IPC shell (card 78)', () => {
  it("falls back to the board store's API version when there is no main process", () => {
    expect(aboutDialog).toContain(
      'info.value?.version || settings.version || board.version || EM_DASH'
    )
  })

  it('opens the repo in a new tab when there is no IPC shell', () => {
    expect(aboutDialog).toContain("window.open(REPO_URL, '_blank', 'noopener,noreferrer')")
  })

  it('keeps the desktop shell path unchanged when the bridge is present', () => {
    expect(aboutDialog).toContain('tp.shell.openExternal(REPO_URL)')
  })

  it('skips the app-menu subscription when onShowAbout is absent', () => {
    expect(aboutDialog).toContain('window.tp?.app?.onShowAbout?.(() => openAbout()) ?? null')
  })
})

describe('the browser note is in both locales (card 78)', () => {
  it('declares a non-empty settings.browserNote in zh-CN and en', () => {
    expect(zhCN.settings.browserNote.length).toBeGreaterThan(0)
    expect(en.settings.browserNote.length).toBeGreaterThan(0)
  })
})
