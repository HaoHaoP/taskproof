/**
 * The macOS app menu and the CLI version probe, pinned in the main process.
 *
 * Two card-25 rules live here and nowhere else:
 *
 *  - the App submenu's **first** item is our own "About Taskproof", not
 *    Electron's default `role: 'about'` panel. Clicking it must raise the same
 *    renderer event the About sheet listens for.
 *  - `taskproof --version` is parsed loosely: a missing binary, a crash or a
 *    stray word all collapse to null (an em dash in the UI), never an error.
 *
 * Importing `index.ts` would normally boot the app, so electron is mocked and
 * `whenReady` never resolves -- the module's top-level wiring runs, its exported
 * builders stay callable, and nothing actually opens.
 */
import { describe, expect, it, vi } from 'vitest'
import type { MenuItemConstructorOptions } from 'electron'
import { appMenuTemplate, parseCliVersion } from './index'

vi.mock('electron', async () => {
  const os = await vi.importActual<typeof import('node:os')>('node:os')
  const fs = await vi.importActual<typeof import('node:fs')>('node:fs')
  const userData = fs.mkdtempSync(`${os.tmpdir()}/tp-about-`)
  return {
    app: {
      name: 'Taskproof',
      getPath: (name: string) => (name === 'appData' ? os.tmpdir() : userData),
      setPath: () => {},
      getVersion: () => '0.1.0',
      getAppPath: () => process.cwd(),
      setAppUserModelId: () => {},
      dock: { setIcon: () => {} },
      whenReady: () => new Promise(() => {}),
      on: () => {}
    },
    BrowserWindow: class {},
    ipcMain: { handle: () => {} },
    Menu: { buildFromTemplate: () => ({}), setApplicationMenu: () => {} },
    shell: { openPath: async () => '', openExternal: async () => {} },
    clipboard: { writeText: () => {}, readText: () => '' }
  }
})

/** The App submenu's items, as a plain array for indexing in the assertions. */
function appSubmenu(template: MenuItemConstructorOptions[]): MenuItemConstructorOptions[] {
  return template[0].submenu as MenuItemConstructorOptions[]
}

describe('appMenuTemplate', () => {
  it('puts "About Taskproof" first in the App submenu, not the default About', () => {
    const template = appMenuTemplate(() => {})
    const items = appSubmenu(template)

    // The card's requirement: the first item is ours, and there is no residual
    // `role: 'about'` for Electron to turn back into its default panel.
    expect(items[0].label).toBe('关于 Taskproof')
    expect(items[0].role).toBeUndefined()
    expect(JSON.stringify(template)).not.toContain('"about"')
  })

  it('wires the About item to the renderer event', () => {
    const onAbout = vi.fn()
    const items = appSubmenu(appMenuTemplate(onAbout))
    items[0].click?.({} as never, {} as never, {} as never)
    expect(onAbout).toHaveBeenCalledOnce()
  })

  it('keeps an Edit menu (copy / paste) and a Window menu', () => {
    const template = appMenuTemplate(() => {})
    const labels = template.map((item) => item.label)
    expect(labels).toContain('Edit')
    expect(labels).toContain('Window')

    const edit = template.find((item) => item.label === 'Edit')
    const roles = (edit?.submenu as MenuItemConstructorOptions[]).map((item) => item.role)
    expect(roles).toContain('copy')
    expect(roles).toContain('paste')
  })
})

describe('parseCliVersion', () => {
  it('reads the version out of `taskproof --version`', () => {
    // The real CLI prints `taskproof 0.0.1`.
    expect(parseCliVersion('taskproof 0.0.1')).toBe('0.0.1')
    expect(parseCliVersion('0.0.1\n')).toBe('0.0.1')
  })

  it('returns null for anything that is not a version, so the UI shows a dash', () => {
    expect(parseCliVersion(null)).toBeNull()
    expect(parseCliVersion(undefined)).toBeNull()
    expect(parseCliVersion('')).toBeNull()
    expect(parseCliVersion('command not found')).toBeNull()
  })
})
