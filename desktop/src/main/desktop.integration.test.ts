/**
 * The desktop switches, exercised end to end in the main process.
 *
 * The card asks for real-window assertions (tray, Dock badge, notification
 * de-duplication, close-to-tray, autostart). This machine's sandbox cannot
 * launch a `.app` bundle at all (any bundle SIGABRTs in
 * `___RegisterApplication_block_invoke`), so the window cannot be opened here.
 * What this file does instead is drive the *real* `index.ts` -- the same wiring
 * the window would use -- against a stubbed `electron` and a stubbed API child,
 * and assert the calls the main process actually makes:
 *
 *   - `new Tray(...)` on the switch going on, `.destroy()` when it goes off;
 *   - `app.dock.setBadge('2')` for failed + blocked + timeout, ignoring cancelled;
 *   - one `new Notification(...)` per newly-failed id, none on the next poll;
 *   - `close` is prevented and the window hidden only while `tray` is on;
 *   - `app.setLoginItemSettings({ openAtLogin })` aligns once at boot and on toggle.
 */
import { afterAll, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'

/** A stub API child: prints the port/token lines the real CLI prints, then serves
 *  the two read endpoints the poller consumes. Writes `<pid> <port>` when up. */
const FAKE_API = `
import { createServer } from 'node:http'
import { writeFileSync } from 'node:fs'
const argv = process.argv.slice(2)
const i = argv.indexOf('--port')
const want = i >= 0 ? Number(argv[i + 1]) : 0
const log = process.env.FAKE_API_LOG
const srv = createServer((req, res) => {
  res.setHeader('content-type', 'application/json')
  if (req.url.startsWith('/api/summary')) return res.end(JSON.stringify({ summary: { failed: 2, cancelled: 1 } }))
  if (req.url.startsWith('/api/tasks')) return res.end(JSON.stringify({ tasks: [{ id: 't-f1', status: 'failed', project: 'proj' }] }))
  res.statusCode = 404; res.end('{}')
})
srv.listen(want, '127.0.0.1', () => {
  const port = srv.address().port
  writeFileSync(log, process.pid + ' ' + port)
  process.stdout.write('taskproof api listening on http://127.0.0.1:' + port + '\\n')
  process.stdout.write('taskproof api token fake-session-token\\n')
})
process.on('SIGTERM', () => process.exit(0))
`

const H = vi.hoisted(() => {
  return {
    trayCtor: 0,
    trayDestroy: 0,
    badge: [] as string[],
    loginItems: [] as Array<{ openAtLogin: boolean }>,
    notifications: [] as Array<{ title: string; body: string }>,
    notifySupported: true,
    windows: [] as any[],
    ipc: {} as Record<string, (...a: any[]) => unknown>,
    on: {} as Record<string, Array<(...a: any[]) => void>>,
    logFile: '',
    ready: false
  }
})

vi.mock('electron', async () => {
  const fs = await vi.importActual<typeof import('node:fs')>('node:fs')
  const os = await vi.importActual<typeof import('node:os')>('node:os')
  const path = await vi.importActual<typeof import('node:path')>('node:path')

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tp-dint-'))
  const appData = path.join(dir, 'appData')
  const userData = path.join(appData, 'taskproof-desktop')
  fs.mkdirSync(userData, { recursive: true })
  const script = path.join(dir, 'fake-api.mjs')
  fs.writeFileSync(script, FAKE_API)
  const ws = path.join(dir, 'ws')
  fs.mkdirSync(ws, { recursive: true })
  H.logFile = path.join(dir, 'api-port.txt')
  process.env.FAKE_API_LOG = H.logFile
  // Off-by-default diagnostics are switched on here so the captured IPC surface
  // (tp:diag:*) is registered, exactly as the real-window harness would use it.
  process.env.TP_DESKTOP_DIAG = '1'
  fs.writeFileSync(
    path.join(userData, 'settings.json'),
    JSON.stringify({
      theme: 'dark',
      language: 'en',
      poll: '2s',
      workspace: ws,
      taskproofPath: `${process.execPath} ${script}`,
      portMode: 'auto',
      port: 0,
      launch: 'auto',
      notifyFail: true,
      notifyDone: false,
      dockBadge: true,
      tray: true,
      autostart: true
    })
  )

  class FakeWindow {
    webContents = { send: () => {}, setWindowOpenHandler: () => {} }
    hidden = false
    destroyed = false
    handlers: Record<string, Array<(...a: any[]) => void>> = {}
    constructor() {
      H.windows.push(this)
    }
    on(event: string, cb: (...a: any[]) => void) {
      ;(this.handlers[event] ||= []).push(cb)
      return this
    }
    emit(event: string, ...args: any[]) {
      for (const cb of this.handlers[event] ?? []) cb(...args)
    }
    isDestroyed() {
      return this.destroyed
    }
    isMinimized() {
      return false
    }
    isVisible() {
      return !this.hidden
    }
    restore() {}
    show() {
      this.hidden = false
    }
    hide() {
      this.hidden = true
    }
    focus() {}
    loadURL() {
      return Promise.resolve()
    }
    loadFile() {
      return Promise.resolve()
    }
    setWindowOpenHandler() {}
  }

  class FakeTray {
    constructor() {
      H.trayCtor++
    }
    setToolTip() {}
    setContextMenu() {}
    on() {}
    destroy() {
      H.trayDestroy++
    }
  }

  class FakeNotification {
    constructor(opts: { title: string; body: string }) {
      H.notifications.push(opts)
    }
    static isSupported() {
      return H.notifySupported
    }
    show() {}
  }

  return {
    app: {
      name: 'Taskproof',
      getPath: (name: string) => (name === 'appData' ? appData : name === 'home' ? dir : userData),
      setPath: () => {},
      getVersion: () => '0.1.0',
      getAppPath: () => process.cwd(),
      setAppUserModelId: () => {},
      setLoginItemSettings: (s: { openAtLogin: boolean }) => H.loginItems.push(s),
      dock: { setIcon: () => {}, setBadge: (v: string) => H.badge.push(v), getBadge: () => H.badge.at(-1) ?? '' },
      whenReady: () => Promise.resolve(),
      quit: () => {},
      on: (event: string, cb: (...a: any[]) => void) => {
        ;(H.on[event] ||= []).push(cb)
      }
    },
    BrowserWindow: Object.assign(FakeWindow, { getAllWindows: () => H.windows }),
    ipcMain: {
      handle: (channel: string, fn: (...a: any[]) => unknown) => {
        H.ipc[channel] = fn
      }
    },
    Menu: { buildFromTemplate: () => ({ items: [], template: [] }), setApplicationMenu: () => {} },
    nativeImage: {
      createFromPath: () => ({
        setTemplateImage: () => {},
        isTemplateImage: () => true,
        isEmpty: () => false,
        getSize: () => ({ width: 18, height: 18 })
      })
    },
    Notification: FakeNotification,
    Tray: FakeTray,
    shell: { openPath: async () => '', openExternal: async () => {} },
    clipboard: { writeText: () => {}, readText: () => '' }
  }
})

// Import after the mock is registered; the top-level wiring runs and whenReady
// resolves on the next microtask, so `api.start()` (auto) spawns the fake child.
await import('./index')

/** Wait until the stub child is up (it writes `<pid> <port>` when listening). */
async function childUp(): Promise<{ pid: number; port: number }> {
  await vi.waitFor(
    () => {
      try {
        const raw = readFileSync(H.logFile, 'utf8').trim()
        if (raw) H.ready = true
        expect(raw).not.toBe('')
      } catch {
        throw new Error('child not up yet')
      }
    },
    { timeout: 8000, interval: 100 }
  )
  const [pid, port] = readFileSync(H.logFile, 'utf8').trim().split(' ').map(Number)
  return { pid, port }
}

const set = (patch: Record<string, unknown>): unknown => H.ipc['tp:settings:set']({}, patch)

afterAll(async () => {
  // Quiet the poller and stop the stub child so the worker can exit cleanly.
  set({ dockBadge: false, notifyFail: false })
  try {
    const [pid] = readFileSync(H.logFile, 'utf8').trim().split(' ').map(Number)
    if (pid) process.kill(pid, 'SIGKILL')
  } catch {
    /* already gone */
  }
})

describe('desktop integration (stubbed electron + stubbed API child)', { timeout: 20_000 }, () => {
  it('creates the tray on boot and destroys/re-creates it as the switch flips', async () => {
    await childUp()
    await vi.waitFor(() => expect(H.trayCtor).toBeGreaterThanOrEqual(1))
    const afterBoot = H.trayCtor
    set({ tray: false })
    await vi.waitFor(() => expect(H.trayDestroy).toBeGreaterThanOrEqual(1))
    set({ tray: true })
    await vi.waitFor(() => expect(H.trayCtor).toBe(afterBoot + 1))
    // leave it on for the close-to-tray assertions below
  })

  it('paints the Dock badge from failed + blocked + timeout, never cancelled', async () => {
    await childUp()
    // summary { failed: 2, cancelled: 1 } -> the badge must read "2", not "3".
    await vi.waitFor(() => expect(H.badge).toContain('2'), { timeout: 8000 })
    expect(H.badge).not.toContain('3')
  })

  it('notifies once for a newly-failed task and stays quiet on the next poll', async () => {
    await childUp()
    await vi.waitFor(() => expect(H.notifications.length).toBeGreaterThanOrEqual(1), { timeout: 8000 })
    const first = H.notifications.filter((n) => n.body.includes('t-f1'))
    expect(first).toHaveLength(1)
    expect(first[0].title).toBe('验收未通过')
    expect(first[0].body).toBe('proj · t-f1')
    // Several more 2s polls: the id was claimed, so nothing else fires for it.
    await new Promise((r) => setTimeout(r, 4500))
    expect(H.notifications.filter((n) => n.body.includes('t-f1'))).toHaveLength(1)
  })

  it('close-to-tray: hides (not quits) while tray is on, tears down when off', async () => {
    await childUp()
    set({ tray: true })
    const win = H.windows[0]
    let prevented = false
    win.emit('close', { preventDefault: () => (prevented = true) })
    expect(prevented).toBe(true)
    expect(win.isVisible()).toBe(false)
    // tray off -> the same close is a real close (no preventDefault)
    set({ tray: false })
    prevented = false
    win.emit('close', { preventDefault: () => (prevented = true) })
    expect(prevented).toBe(false)
  })

  it('aligns the login item at boot and on toggle', async () => {
    await vi.waitFor(() => expect(H.loginItems.some((s) => s.openAtLogin)).toBe(true))
    set({ autostart: false })
    await vi.waitFor(() => expect(H.loginItems.some((s) => s.openAtLogin === false)).toBe(true))
  })

  it('reports tray + template + real badge over the diagnostic IPC', async () => {
    await childUp()
    set({ tray: true })
    await vi.waitFor(() => expect(H.badge).toContain('2'), { timeout: 8000 })
    const state = (await H.ipc['tp:diag:state']()) as { tray: boolean; trayTemplate: boolean; badge: string }
    expect(state.tray).toBe(true)
    expect(state.trayTemplate).toBe(true)
    expect(state.badge).toBe('2')
  })
})
