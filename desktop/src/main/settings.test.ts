/**
 * settings.json migration and write-through, pinned.
 *
 * A file written by an earlier build lacks the fields added since (the port
 * mode, the launch behaviour, the desktop-integration switches). Reading it must
 * backfill every missing field from the defaults while keeping every value that
 * is already there -- otherwise an upgrade silently resets the app. And the new
 * switches must actually land on disk, or they are decoration.
 *
 * The main process owns the file, so this drives `settings.ts` directly against
 * a real temp directory rather than mocking the filesystem.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// `vi.mock` is hoisted above the imports, so the mutable path has to be too.
const h = vi.hoisted(() => ({ userData: '' }))

vi.mock('electron', () => ({
  app: {
    getPath: (name: string) => (name === 'home' ? '/Users/test' : h.userData)
  }
}))

beforeEach(() => {
  h.userData = mkdtempSync(join(tmpdir(), 'tp-settings-'))
  // `settings.ts` caches the file in a module-level variable; a fresh module
  // per test is what makes each case read its own temp directory.
  vi.resetModules()
})

afterEach(() => {
  rmSync(h.userData, { recursive: true, force: true })
})

function load(): Promise<typeof import('./settings')> {
  return import('./settings')
}

describe('settings.json migration', () => {
  it('backfills the new fields for an old file and keeps the old values', async () => {
    // A file as the previous build would have written it: five keys, no more.
    writeFileSync(
      join(h.userData, 'settings.json'),
      JSON.stringify({
        theme: 'light',
        language: 'en',
        poll: 'off',
        workspace: '/Users/someone/.taskproof',
        taskproofPath: '/opt/homebrew/bin/taskproof'
      })
    )

    const { get } = await load()
    const loaded = get()

    // Values already in the file win.
    expect(loaded.theme).toBe('light')
    expect(loaded.language).toBe('en')
    expect(loaded.poll).toBe('off')
    expect(loaded.workspace).toBe('/Users/someone/.taskproof')
    expect(loaded.taskproofPath).toBe('/opt/homebrew/bin/taskproof')

    // Every field added since is backfilled from the defaults.
    expect(loaded.portMode).toBe('auto')
    expect(loaded.port).toBe(8787)
    expect(loaded.launch).toBe('auto')
    expect(loaded.notifyFail).toBe(false)
    expect(loaded.notifyDone).toBe(false)
    expect(loaded.dockBadge).toBe(false)
    expect(loaded.tray).toBe(false)
    expect(loaded.autostart).toBe(false)
  })

  it('falls back to defaults when the file is missing', async () => {
    const { get } = await load()
    const loaded = get()
    expect(loaded.theme).toBe('dark')
    expect(loaded.portMode).toBe('auto')
    expect(loaded.launch).toBe('auto')
    // Empty by default so `resolveLaunchCommand` auto-resolves (bundled runtime,
    // then PATH, then python3); a fresh install must not be pinned to a bare
    // `taskproof` that only a login shell could find.
    expect(loaded.taskproofPath).toBe('')
  })

  it('persists a desktop-integration switch to disk for the next read', async () => {
    const { get, set } = await load()
    get() // seed the cache from the defaults
    set({ tray: true, autostart: true })

    // The file on disk carries the new flags...
    const onDisk = JSON.parse(readFileSync(join(h.userData, 'settings.json'), 'utf8'))
    expect(onDisk.tray).toBe(true)
    expect(onDisk.autostart).toBe(true)

    // ...and a fresh process (fresh module) reads them back.
    vi.resetModules()
    const reread = (await load()).get()
    expect(reread.tray).toBe(true)
    expect(reread.autostart).toBe(true)
  })
})
