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
 *   - the first poll only seeds the backlog (no retrospective notice); a card
 *     that appears afterwards raises one `new Notification(...)`, never more;
 *   - `close` is prevented and the window hidden only while `tray` is on;
 *   - a dev build never calls `app.setLoginItemSettings`, while a packaged one
 *     still aligns the login item with the switch on toggle.
 */
import { afterAll, describe, expect, it, vi } from 'vitest'
import { readFileSync, writeFileSync } from 'node:fs'

/** A stub API child: prints the port/token lines the real CLI prints, then serves
 *  the two read endpoints the poller consumes. Writes `<pid> <port>` when up. */
const FAKE_API = `
import { createServer } from 'node:http'
import { readFileSync, writeFileSync } from 'node:fs'
const argv = process.argv.slice(2)
const i = argv.indexOf('--port')
const want = i >= 0 ? Number(argv[i + 1]) : 0
const log = process.env.FAKE_API_LOG
const tasksFile = process.env.FAKE_API_TASKS
const srv = createServer((req, res) => {
  res.setHeader('content-type', 'application/json')
  if (req.url.startsWith('/api/summary')) return res.end(JSON.stringify({ summary: { failed: 2, cancelled: 1 } }))
  if (req.url.startsWith('/api/tasks')) {
    let tasks = []
    try { tasks = JSON.parse(readFileSync(tasksFile, 'utf8')) } catch {}
    return res.end(JSON.stringify({ tasks }))
  }
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
    tasksFile: '',
    isPackaged: false,
    diag: [] as string[],
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
  // The stub serves its task list from a file the test can grow mid-run, so it
  // can prove the seeding rule: a fresh launch opens onto a full backlog and
  // must stay silent, and only a card that appears *after* that can notify.
  H.tasksFile = path.join(dir, 'tasks.json')
  process.env.FAKE_API_TASKS = H.tasksFile
  fs.writeFileSync(
    H.tasksFile,
    JSON.stringify([
      { id: 'h-f1', status: 'failed', project: 'proj' },
      { id: 'h-f2', status: 'blocked', project: 'proj' },
      { id: 'h-f3', status: 'timeout', project: 'proj' },
      { id: 'h-f4', status: 'failed', project: 'proj' },
      { id: 'h-d1', status: 'done', project: 'proj' },
      { id: 'h-d2', status: 'done', project: 'proj' },
      { id: 'h-d3', status: 'done', project: 'proj' }
    ])
  )
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
      get isPackaged() {
        return H.isPackaged
      },
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

// Capture the gated `[diag]` trace the main process writes to stdout, so the
// test can assert on the notifications it *did not* raise (and on the autostart
// note a dev build leaves instead of touching the login items). Non-diag writes
// pass straight through to vitest's own reporter.
const originalStdoutWrite = process.stdout.write.bind(process.stdout)
process.stdout.write = ((chunk: string | Uint8Array, ...rest: unknown[]): boolean => {
  const text = typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8')
  for (const line of text.split('\n')) {
    if (line.startsWith('[diag]')) H.diag.push(line.trim())
  }
  return originalStdoutWrite(chunk as never, ...(rest as never[]))
}) as typeof process.stdout.write

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
    { timeout: 15_000, interval: 100 }
  )
  const [pid, port] = readFileSync(H.logFile, 'utf8').trim().split(' ').map(Number)
  return { pid, port }
}

const set = (patch: Record<string, unknown>): unknown => H.ipc['tp:settings:set']({}, patch)

afterAll(async () => {
  // Put stdout back so vitest's own reporting is untouched after this file.
  process.stdout.write = originalStdoutWrite
  // Quiet the poller and stop the stub child so the worker can exit cleanly.
  set({ dockBadge: false, notifyFail: false })
  try {
    const [pid] = readFileSync(H.logFile, 'utf8').trim().split(' ').map(Number)
    if (pid) process.kill(pid, 'SIGKILL')
  } catch {
    /* already gone */
  }
})

// NOTE: the waits below are deliberately generous. This suite runs the real poll
// loop against a stub child, and the machine it runs on is routinely busy with
// several task lanes at once -- an 8s budget for "the next poll lands" was flaky
// (it failed once under load and passed on every calm re-run, which is a corrupt
// signal for a lane's acceptance). Budgets are per-wait, not per-suite.
describe('desktop integration (stubbed electron + stubbed API child)', { timeout: 40_000 }, () => {
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
    await vi.waitFor(() => expect(H.badge).toContain('2'), { timeout: 15_000 })
    expect(H.badge).not.toContain('3')
  })

  it('seeds the whole backlog on the first poll, then fires once for a new id', async () => {
    await childUp()
    // One successful poll paints the badge; that same poll seeded the seven
    // historical cards (four not-passing + three done) the stub starts with.
    await vi.waitFor(() => expect(H.badge).toContain('2'), { timeout: 15_000 })
    // (1) A fresh launch onto a full backlog raises nothing, and the main-process
    // trace carries no `notify` line at all.
    expect(H.notifications).toEqual([])
    expect(H.diag.some((line) => line.includes('notify'))).toBe(false)

    // (2) A card that only shows up *after* the seed fires exactly one notice.
    const history = JSON.parse(readFileSync(H.tasksFile, 'utf8')) as Array<Record<string, string>>
    writeFileSync(
      H.tasksFile,
      JSON.stringify([...history, { id: 't-new', status: 'failed', project: 'proj' }])
    )
    await vi.waitFor(
      () => expect(H.notifications.filter((n) => n.body.includes('t-new'))).toHaveLength(1),
      { timeout: 15_000 }
    )
    const fired = H.notifications.find((n) => n.body.includes('t-new'))
    expect(fired?.title).toBe('验收未通过')
    expect(fired?.body).toBe('proj · t-new')
    expect(H.diag).toContain('[diag] notify 验收未通过 t-new')

    // The same id on later polls stays quiet: one notification per id, ever.
    await new Promise((r) => setTimeout(r, 4500))
    expect(H.notifications.filter((n) => n.body.includes('t-new'))).toHaveLength(1)
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

  it('a dev build never writes a login item and says so', async () => {
    await childUp()
    // The stub is not packaged: boot and every toggle must leave the OS alone --
    // no stray "Electron" login item.
    expect(H.isPackaged).toBe(false)
    set({ autostart: false })
    set({ autostart: true })
    await new Promise((r) => setTimeout(r, 300))
    expect(H.loginItems).toEqual([])
    expect(H.diag).toContain(
      '[diag] autostart skipped: not packaged (takes effect only in a packaged build)'
    )
  })

  it('a packaged build still aligns the login item with the switch', async () => {
    H.isPackaged = true
    try {
      set({ autostart: false })
      await vi.waitFor(() => expect(H.loginItems.some((s) => s.openAtLogin === false)).toBe(true))
      set({ autostart: true })
      await vi.waitFor(() => expect(H.loginItems.some((s) => s.openAtLogin === true)).toBe(true))
    } finally {
      H.isPackaged = false
    }
  })

  it('reports tray + template + real badge over the diagnostic IPC', async () => {
    await childUp()
    set({ tray: true })
    await vi.waitFor(() => expect(H.badge).toContain('2'), { timeout: 15_000 })
    const state = (await H.ipc['tp:diag:state']()) as { tray: boolean; trayTemplate: boolean; badge: string }
    expect(state.tray).toBe(true)
    expect(state.trayTemplate).toBe(true)
    expect(state.badge).toBe('2')
  })
})
