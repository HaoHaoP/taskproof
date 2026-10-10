/**
 * Desktop settings, owned by the main process.
 *
 * One `settings.json` in the app's userData directory is the source of truth.
 * The renderer only ever sees it through the named IPC surface -- it never
 * reads or writes the file itself.
 */
import { app } from 'electron'
import { mkdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'
import type { DesktopSettings } from '../preload/types'
import { DEFAULT_COLUMN_CAPS, normalizeColumnCaps } from '../preload/types'

let cached: DesktopSettings | null = null

function defaults(): DesktopSettings {
  return {
    theme: 'dark',
    language: 'system',
    poll: '2s',
    workspace: join(app.getPath('home'), '.taskproof'),
    // Empty by default: `resolveLaunchCommand` then auto-resolves -- the bundled
    // runtime first, then `taskproof` on the (augmented) PATH, then
    // `python3 -m taskproof`. A non-empty value is a user override and wins
    // outright; the from-source / dev workflow still sets `TASKPROOF_CMD` to an
    // interpreter + args ("python3 -m taskproof") and so keeps its say.
    taskproofPath: process.env.TASKPROOF_CMD ?? '',
    portMode: 'auto',
    port: 8787,
    launch: 'auto',
    notifyFail: false,
    notifyDone: false,
    dockBadge: false,
    tray: false,
    autostart: false,
    // A fresh board matches today's: done / cancelled window at ten, the four
    // live columns unfolded. The user's own table rides in settings.json.
    columnCaps: { ...DEFAULT_COLUMN_CAPS }
  }
}

function settingsFile(): string {
  return join(app.getPath('userData'), 'settings.json')
}

export function get(): DesktopSettings {
  if (cached) return cached
  try {
    const raw: unknown = JSON.parse(readFileSync(settingsFile(), 'utf8'))
    // Forward-compatible migration: a file written by an earlier build simply
    // lacks the fields added since. Spreading it over the defaults backfills
    // every missing field while keeping every value that is already present,
    // so an old settings.json loads intact instead of resetting.
    const stored =
      raw !== null && typeof raw === 'object' && !Array.isArray(raw)
        ? (raw as Partial<DesktopSettings>)
        : {}
    // `columnCaps` is a nested object, so a shallow spread cannot backfill it:
    // an older file that predates the field (or names only some columns) would
    // replace the whole default table with its own partial one. Merge it key by
    // key instead, dropping unknown keys and converging the values.
    cached = { ...defaults(), ...stored, columnCaps: normalizeColumnCaps(stored.columnCaps) }
  } catch {
    // Missing or unreadable: fall back to defaults rather than failing to boot.
    cached = defaults()
  }
  return cached
}

export function set(patch: Partial<DesktopSettings>): DesktopSettings {
  const current = get()
  // Merge a caps patch over the *current* table before normalising, so a
  // one-column write (the header control's `+` / `-`) keeps the other five
  // caps rather than resetting them to their defaults.
  const columnCaps = patch.columnCaps
    ? normalizeColumnCaps({ ...current.columnCaps, ...patch.columnCaps })
    : current.columnCaps
  const next = { ...current, ...patch, columnCaps }
  cached = next
  try {
    const file = settingsFile()
    mkdirSync(dirname(file), { recursive: true })
    writeFileSync(file, `${JSON.stringify(next, null, 2)}\n`, 'utf8')
  } catch {
    // Persisting is best-effort; the in-memory value still applies this run.
  }
  return next
}
