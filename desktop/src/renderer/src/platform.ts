/**
 * Host detection, the API base URL and the browser settings mirror -- the three
 * places where the desktop host (the `window.tp` IPC bridge) and a plain browser
 * (the page the local service serves, or one opened from disk) genuinely differ.
 *
 * Everything here is a pure function over injected inputs. The tests run under
 * the node environment with fake `storage` / `location` objects and no DOM, and
 * the stores and components pass the real `window.tp` / `localStorage` in at
 * the edges. No `window` or `document` is touched at module load.
 */
import {
  CAP_MAX,
  CAP_MIN,
  COLUMN_CAP_KEYS,
  DEFAULT_COLUMN_CAPS,
  type DesktopSettings,
  type LanguageChoice,
  type PollChoice,
  type ServiceStatus,
  type ThemeChoice,
  type TpApi
} from '../../preload/types'

/** The loopback port the desktop child binds by default, and the browser
 *  fallback when the page is not served over http(s) (e.g. `file://`). */
export const DEFAULT_PORT = 8787

/** Where the browser host persists its settings mirror. */
export const SETTINGS_STORAGE_KEY = 'taskproof.settings'

/**
 * The code default for every field, matching the main process's initial
 * settings.json. A browser host has no main process, so a missing or corrupt
 * mirror falls back here -- field by field, never as a whole.
 */
export const FALLBACK: DesktopSettings = {
  theme: 'dark',
  language: 'system',
  poll: '2s',
  workspace: '',
  taskproofPath: '',
  portMode: 'auto',
  port: DEFAULT_PORT,
  launch: 'auto',
  notifyFail: false,
  notifyDone: false,
  dockBadge: false,
  tray: false,
  autostart: false,
  columnCaps: { ...DEFAULT_COLUMN_CAPS }
}

/**
 * Whether the Electron preload bridge is present. `window.tp` is absent when
 * the renderer is opened in a plain browser -- exactly when the desktop IPC
 * surface (service, the settings file, the shell, the app menu) has to stand
 * down rather than render dead controls.
 */
export function hasDesktopHost(tp: TpApi | undefined = window.tp): boolean {
  return tp != null
}

/** The slice of `location` the resolver reads -- injected so tests need no DOM. */
export interface HostLocation {
  protocol: string
  origin: string
  search: string
}

export interface ResolveApiBaseInput {
  /** The desktop host's service status, or `null` when there is no bridge. */
  tpStatus?: ServiceStatus | null
  /** The page's address; omitted (or non-http) skips the same-origin branch. */
  location?: HostLocation | null
}

/**
 * Who the board talks to.
 *
 * A desktop host's child port is authoritative. Without a bridge, a page served
 * over http(s) is by construction the same origin as the service that shipped
 * it -- that is preferred over the old `?port=` override so moving the service
 * to another port needs no manual address-bar edit. Everything else (`file://`,
 * an unknown protocol) keeps the old `?port=` / 8787 loopback fallback, which
 * is what the `file://` and dev-server usages rely on.
 */
export function resolveApiBase({ tpStatus, location }: ResolveApiBaseInput): string {
  if (tpStatus && tpStatus.port) return `http://127.0.0.1:${tpStatus.port}`
  const protocol = location?.protocol ?? ''
  if (protocol === 'http:' || protocol === 'https:') return location!.origin
  const override = new URLSearchParams(location?.search ?? '').get('port')
  return `http://127.0.0.1:${override ?? DEFAULT_PORT}`
}

/** The read/write slice of `localStorage` the mirror needs (faked in tests). */
export interface SettingsStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

const THEMES: readonly ThemeChoice[] = ['system', 'dark', 'light']
const LANGUAGES: readonly LanguageChoice[] = ['system', 'zh-CN', 'en']
const POLLS: readonly PollChoice[] = ['2s', 'off']

/** Accept a value only when it is one of the declared strings. */
function whitelisted<T extends string>(value: unknown, allowed: readonly T[]): T | undefined {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : undefined
}

/**
 * Read the browser settings mirror field by field. A missing storage, an absent
 * key, unparseable JSON or an out-of-shape object falls back to `FALLBACK`; a
 * single bad field falls back for that field alone, so one hand-edited value
 * never discards the rest. Theme / language / polling accept only their
 * whitelisted values; the column caps accept only declared keys whose value is
 * an in-range integer.
 */
export function readSettings(storage?: SettingsStorage | null): DesktopSettings {
  const out: DesktopSettings = { ...FALLBACK, columnCaps: { ...FALLBACK.columnCaps } }
  if (!storage) return out

  let parsed: unknown
  try {
    const text = storage.getItem(SETTINGS_STORAGE_KEY)
    if (text == null) return out
    parsed = JSON.parse(text)
  } catch {
    return out
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return out
  const raw = parsed as Record<string, unknown>

  const theme = whitelisted(raw.theme, THEMES)
  if (theme) out.theme = theme
  const language = whitelisted(raw.language, LANGUAGES)
  if (language) out.language = language
  const poll = whitelisted(raw.poll, POLLS)
  if (poll) out.poll = poll

  const caps = raw.columnCaps
  if (caps !== null && typeof caps === 'object' && !Array.isArray(caps)) {
    const table = caps as Record<string, unknown>
    for (const key of COLUMN_CAP_KEYS) {
      const value = table[key]
      if (typeof value === 'number' && Number.isInteger(value) && value >= CAP_MIN && value <= CAP_MAX) {
        out.columnCaps[key] = value
      }
    }
  }
  return out
}

/**
 * Merge a patch into the stored mirror and return the result, so the browser
 * host has a real "settings file" to reload from -- the same whole-file shape
 * the main process would have handed back. A refused write (storage full,
 * private mode) is swallowed: the in-memory value still wins for this session.
 */
export function mergeSettings(
  storage: SettingsStorage | null | undefined,
  patch: Partial<DesktopSettings>
): DesktopSettings {
  const current = readSettings(storage)
  const next: DesktopSettings = {
    ...current,
    ...patch,
    columnCaps: { ...current.columnCaps, ...(patch.columnCaps ?? {}) }
  }
  if (storage) {
    try {
      storage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(next))
    } catch {
      // Ignore: an unwritable storage must not throw out of a settings change.
    }
  }
  return next
}
