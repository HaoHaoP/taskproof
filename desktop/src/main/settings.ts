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

let cached: DesktopSettings | null = null

function defaults(): DesktopSettings {
  return {
    theme: 'dark',
    language: 'system',
    poll: '2s',
    workspace: join(app.getPath('home'), '.taskproof'),
    // Resolved on PATH by default; the from-source workflow points this at a
    // python interpreter script instead.
    taskproofPath: process.env.TASKPROOF_CMD ?? 'taskproof'
  }
}

function settingsFile(): string {
  return join(app.getPath('userData'), 'settings.json')
}

export function get(): DesktopSettings {
  if (cached) return cached
  try {
    const raw = JSON.parse(readFileSync(settingsFile(), 'utf8')) as Partial<DesktopSettings>
    cached = { ...defaults(), ...raw }
  } catch {
    // Missing or unreadable: fall back to defaults rather than failing to boot.
    cached = defaults()
  }
  return cached
}

export function set(patch: Partial<DesktopSettings>): DesktopSettings {
  const next = { ...get(), ...patch }
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
