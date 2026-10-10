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
 *   - `app.dock.setBadge('2')` for failed + blocked + timeout, ignoring
 *     cancelled -- *on macOS only*. The Dock exists there and nowhere else, so
 *     the other platforms assert the honest non-native fact instead: the OS is
 *     never touched and a `[diag] ... skipped` line says why;
 *   - the first poll only seeds the backlog (no retrospective notice); a card
 *     that appears afterwards raises one `new Notification(...)`, never more;
 *   - `close` is prevented and the window hidden only while `tray` is on;
 *   - `app.setLoginItemSettings` is macOS + Windows only: there a dev build
 *     still logs "not packaged" and a packaged one aligns the login item with
 *     the switch, while elsewhere no login item is ever created or modified.
 *
 * The OS-integration branches are chosen by a *platform seam* (`platform()` in
 * `index.ts`, read from `TP_DESKTOP_PLATFORM`). The suite drives that seam with
 * `usePlatform(...)`, so the linux/win32 branches really execute even on this
 * macOS box -- the same code paths the ubuntu CI runs for real.
 */
import { afterAll, describe, expect, it, vi } from 'vitest'
import { readFileSync, rmSync, writeFileSync } from 'node:fs'

/** A stub API child: prints the port line the real CLI prints, then serves the
 *  two read endpoints the poller consumes. Writes `<pid> <port>` when up. */
const FAKE_API = `
import { createServer } from 'node:http'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
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
  // Test seam only: while FAKE_API_HOLD points at an existing file, withhold the
  // port line -- a stand-in for a child that is slow to announce its port. A real
  // run never sets this, so a real child always announces immediately.
  const hold = process.env.FAKE_API_HOLD
  if (hold && existsSync(hold)) return
  process.stdout.write('taskproof api listening on http://127.0.0.1:' + port + '\\n')
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
    // Path to the file the FAKE_API hold seam watches (see FAKE_API above).
    holdFile: '',
    isPackaged: false,
    diag: [] as string[],
    ready: false,
    // The platform the main process is currently branched on. Real by default;
    // `usePlatform` overrides both this and `TP_DESKTOP_PLATFORM`.
    platform: process.platform as NodeJS.Platform
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
  // The child withholds its port line while this file exists; a test creates it
  // to reproduce the CI shape (a child that is up but has not announced a port).
  H.holdFile = path.join(dir, 'api-hold')
  process.env.FAKE_API_HOLD = H.holdFile
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

// The exact diagnostic lines the unsupported paths now emit. Asserting on them
// (rather than on silence) is what makes a *skip* observable on any platform.
const DOCK_SKIP_DIAG = '[diag] dock badge skipped: unsupported on this platform'
const AUTOSTART_UNSUPPORTED_DIAG = '[diag] autostart skipped: unsupported platform'
const AUTOSTART_UNPACKAGED_DIAG =
  '[diag] autostart skipped: not packaged (takes effect only in a packaged build)'

/** `app.setLoginItemSettings` is a macOS + Windows API, and nothing else. */
const loginItemsSupported = (p: NodeJS.Platform): boolean => p === 'darwin' || p === 'win32'

/**
 * The platform seam. `index.ts` reads `TP_DESKTOP_PLATFORM` live, so pointing it
 * at 'linux'/'win32' makes the *non-native* branches really execute on this
 * macOS host -- the exact code ubuntu CI runs. `H.platform` mirrors it so the
 * assertions can branch on the same value the main process used.
 */
function usePlatform(p: NodeJS.Platform): void {
  H.platform = p
  process.env.TP_DESKTOP_PLATFORM = p
}
/** Restore the host's real platform; always called from a `finally`. */
function resetPlatform(): void {
  H.platform = process.platform
  delete process.env.TP_DESKTOP_PLATFORM
}

/** The lines the poller emits about the API round trip, exact-text assertable. */
const POLL_OK_PREFIX = '[diag] poll port='
const POLL_NO_PORT_DIAG = '[diag] poll skipped: no port yet'

/**
 * Wait until a *fresh* real poll has landed.
 *
 * The old version waited on "the Dock badge is 2" (macOS) or "a Dock skip was
 * logged" (everywhere else). Both are already true from earlier tests, so the
 * wait returned instantly and the seed could land *after* the test had written
 * its "new" card -- the seed then swallowed it and no notification fired. That is
 * the CI failure this card pins. A real poll now logs `[diag] poll port=<n> ...`
 * *after* it seeds, so waiting for a line that appears after this call proves the
 * seed already happened. The no-port early return logs a different line
 * (`poll skipped: no port yet`) and can never satisfy this wait.
 */
async function waitForSummaryPoll(): Promise<void> {
  const before = H.diag.filter((line) => line.startsWith(POLL_OK_PREFIX)).length
  await vi.waitFor(
    () =>
      expect(H.diag.filter((line) => line.startsWith(POLL_OK_PREFIX)).length).toBeGreaterThan(
        before
      ),
    { timeout: 15_000 }
  )
}

/** Append a card to the stub's task list, so the next poll sees a brand-new id. */
function writeNewCard(id: string): void {
  const history = JSON.parse(readFileSync(H.tasksFile, 'utf8')) as Array<Record<string, string>>
  writeFileSync(
    H.tasksFile,
    JSON.stringify([...history, { id, status: 'failed', project: 'proj' }])
  )
}

afterAll(async () => {
  // Put stdout back so vitest's own reporting is untouched after this file.
  process.stdout.write = originalStdoutWrite
  // Drop any injected platform so nothing downstream is left pointed at a fake OS.
  resetPlatform()
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
    // summary { failed: 2, cancelled: 1 }. On macOS the badge must read "2",
    // never "3". Anywhere else there is no Dock to paint: the OS is left alone,
    // and the poller logs the honest skip instead of doing nothing silently.
    if (H.platform === 'darwin') {
      await vi.waitFor(() => expect(H.badge).toContain('2'), { timeout: 15_000 })
      expect(H.badge).not.toContain('3')
    } else {
      await vi.waitFor(() => expect(H.diag).toContain(DOCK_SKIP_DIAG), { timeout: 15_000 })
      expect(H.badge).toEqual([])
    }
  })

  it('seeds the whole backlog on the first poll, then fires once for a new id', async () => {
    H.notifySupported = true
    await childUp()
    // One real poll seeds the seven historical cards (four not-passing + three
    // done) the stub starts with; `waitForSummaryPoll` only returns once that
    // poll (and therefore the seed) has actually happened.
    await waitForSummaryPoll()
    // (1) A fresh launch onto a full backlog raises nothing, and the main-process
    // trace carries no `notify` line at all.
    expect(H.notifications).toEqual([])
    expect(H.diag.some((line) => line.includes('notify'))).toBe(false)

    // (2) A card that only shows up *after* the seed fires exactly one notice.
    writeNewCard('t-new')
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

  it('when notifications are unsupported: says so, shows nothing, and still de-dupes', async () => {
    // The honest other world: `Notification.isSupported()` is false (a headless
    // host, a locked-down OS). The claim must still be recorded -- exactly once --
    // and the trace must say why nothing was shown, instead of firing a fake.
    H.notifySupported = false
    try {
      await childUp()
      await waitForSummaryPoll()
      writeNewCard('t-unsupported')
      await vi.waitFor(
        () => expect(H.diag).toContain('[diag] notify-unsupported t-unsupported'),
        { timeout: 15_000 }
      )
      // Nothing was shown, and the id is remembered: later polls stay silent.
      expect(H.notifications.filter((n) => n.body.includes('t-unsupported'))).toHaveLength(0)
      await new Promise((r) => setTimeout(r, 4500))
      expect(H.notifications.filter((n) => n.body.includes('t-unsupported'))).toHaveLength(0)
      // Exactly one unsupported line for the id -- the de-dup holds here too.
      expect(
        H.diag.filter((line) => line === '[diag] notify-unsupported t-unsupported')
      ).toHaveLength(1)
    } finally {
      H.notifySupported = true
    }
  })

  it('recovers real polling after a child withholds its port (the CI shape)', async () => {
    // The CI failure in miniature: the child comes up but does not announce its
    // port yet. Before this card a "no port" tick looked just like a real poll in
    // the trace (both printed only the Dock skip), and the one-shot port read gave
    // up for good once it timed out. Here we hold the port back and prove the app
    // (a) says the poll was skipped, (b) invents no notice, and (c) recovers the
    // moment a later child announces -- without ever guessing a port.
    await childUp()
    // Prime the notifier off a *real* poll of the standing backlog first. This
    // file's notifier is module-level state shared across tests, so without this
    // the recovery test would only pass because an earlier test had primed it --
    // and would fail when run alone. Priming here makes the card added below a
    // genuinely *new* id no matter what ran before.
    await waitForSummaryPoll()
    const okCount = (): number => H.diag.filter((line) => line.startsWith(POLL_OK_PREFIX)).length
    const skipCount = (): number => H.diag.filter((line) => line === POLL_NO_PORT_DIAG).length
    const okBefore = okCount()
    const skipBefore = skipCount()
    const diagBefore = H.diag.length
    H.notifications.length = 0

    // Withhold the port line on the next child, then restart into it. The
    // restart promise blocks until the port read times out, so do not await it.
    writeFileSync(H.holdFile, '')
    void H.ipc['tp:service:restart']()

    // (a) The no-port tick is explicit and *distinct* from a real poll.
    await vi.waitFor(() => expect(skipCount()).toBeGreaterThan(skipBefore), { timeout: 15_000 })
    expect(H.diag.slice(diagBefore).filter((l) => l.startsWith(POLL_OK_PREFIX))).toHaveLength(0)

    // (b) Nothing is invented while there is no port: a card that appears now must
    // stay silent until a real poll can actually read it.
    writeNewCard('t-held')
    await new Promise((r) => setTimeout(r, 1_000))
    expect(H.notifications.filter((n) => n.body.includes('t-held'))).toHaveLength(0)
    expect(H.diag.slice(diagBefore).some((l) => l.includes('notify'))).toBe(false)

    // Release the hold, then let the launcher give up on child #1 and the poll
    // re-spawn: a child that announces recovers real polling.
    rmSync(H.holdFile, { force: true })
    await vi.waitFor(() => expect(okCount()).toBeGreaterThan(okBefore), { timeout: 30_000 })

    // (c) The recovered poll finally sees t-held -- one real notice, once.
    await vi.waitFor(
      () => expect(H.notifications.filter((n) => n.body.includes('t-held'))).toHaveLength(1),
      { timeout: 15_000 }
    )
    expect(H.diag).toContain('[diag] notify 验收未通过 t-held')
    await new Promise((r) => setTimeout(r, 4_500))
    expect(H.notifications.filter((n) => n.body.includes('t-held'))).toHaveLength(1)
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
    // darwin/win32 have the mechanism (and log "not packaged"); linux and the
    // rest have none and log the unsupported skip. Either way: nothing written.
    expect(H.diag).toContain(
      loginItemsSupported(H.platform) ? AUTOSTART_UNPACKAGED_DIAG : AUTOSTART_UNSUPPORTED_DIAG
    )
  })

  it('a packaged build aligns the login item with the switch where the OS has one', async () => {
    H.isPackaged = true
    try {
      if (loginItemsSupported(H.platform)) {
        // macOS / Windows: a packaged toggle is a real login item, on and off.
        set({ autostart: false })
        await vi.waitFor(() => expect(H.loginItems.some((s) => s.openAtLogin === false)).toBe(true))
        set({ autostart: true })
        await vi.waitFor(() => expect(H.loginItems.some((s) => s.openAtLogin === true)).toBe(true))
      } else {
        // No login-item mechanism: even packaged and switched on, the OS is
        // left strictly alone and the skip is logged.
        H.loginItems = []
        set({ autostart: true })
        await new Promise((r) => setTimeout(r, 300))
        expect(H.loginItems).toEqual([])
        expect(H.diag).toContain(AUTOSTART_UNSUPPORTED_DIAG)
      }
    } finally {
      H.isPackaged = false
    }
  })

  it('reports tray + template + real badge over the diagnostic IPC', async () => {
    await childUp()
    set({ tray: true })
    // Let a poll land, then read the same state the diagnostics page reads. A
    // real Dock badge exists on macOS only; everywhere else it is honestly ''
    // (the poller says why).
    await waitForSummaryPoll()
    const state = (await H.ipc['tp:diag:state']()) as {
      tray: boolean
      trayTemplate: boolean
      badge: string
    }
    expect(state.tray).toBe(true)
    expect(state.trayTemplate).toBe(true)
    expect(state.badge).toBe(H.platform === 'darwin' ? '2' : '')
  })

  // ---- Platform seam: run the non-native branches on this host --------------
  //
  // ubuntu CI exercises these for real; a macOS box normally never would, so
  // they would be dead assertions here. `usePlatform` points `index.ts` (via
  // `TP_DESKTOP_PLATFORM`) at another OS so the linux/win32 branches really
  // execute and are actually asserted. Each test restores the real platform.
  describe('OS-integration branches with an injected platform', () => {
    it('linux: the Dock is never touched and the skip is logged', async () => {
      usePlatform('linux')
      try {
        await childUp()
        // Clear what macOS painted before the switch, then prove *this* run
        // logs a fresh skip and still never calls setBadge.
        H.badge = []
        H.diag = []
        await vi.waitFor(() => expect(H.diag).toContain(DOCK_SKIP_DIAG), { timeout: 15_000 })
        set({ dockBadge: false })
        set({ dockBadge: true })
        await new Promise((r) => setTimeout(r, 300))
        expect(H.badge).toEqual([])
      } finally {
        resetPlatform()
      }
    })

    it('win32: there is no Dock either, so it skips the badge the same way', async () => {
      usePlatform('win32')
      try {
        await childUp()
        H.badge = []
        H.diag = []
        await vi.waitFor(() => expect(H.diag).toContain(DOCK_SKIP_DIAG), { timeout: 15_000 })
        await new Promise((r) => setTimeout(r, 300))
        expect(H.badge).toEqual([])
      } finally {
        resetPlatform()
      }
    })

    it('linux: no login-item mechanism -- nothing is written, and it says so', async () => {
      usePlatform('linux')
      H.isPackaged = true
      try {
        await childUp()
        H.loginItems = []
        H.diag = []
        set({ autostart: false })
        set({ autostart: true })
        await new Promise((r) => setTimeout(r, 300))
        expect(H.loginItems).toEqual([])
        expect(H.diag).toContain(AUTOSTART_UNSUPPORTED_DIAG)
      } finally {
        H.isPackaged = false
        resetPlatform()
      }
    })

    it('win32 unpackaged: leaves the OS alone and says why', async () => {
      usePlatform('win32')
      try {
        await childUp()
        H.loginItems = []
        H.diag = []
        expect(H.isPackaged).toBe(false)
        set({ autostart: false })
        set({ autostart: true })
        await new Promise((r) => setTimeout(r, 300))
        expect(H.loginItems).toEqual([])
        expect(H.diag).toContain(AUTOSTART_UNPACKAGED_DIAG)
      } finally {
        resetPlatform()
      }
    })

    it('win32 packaged: the switch and the login item stay aligned', async () => {
      usePlatform('win32')
      H.isPackaged = true
      try {
        await childUp()
        H.loginItems = []
        H.diag = []
        set({ autostart: false })
        await vi.waitFor(() =>
          expect(H.loginItems.some((s) => s.openAtLogin === false)).toBe(true)
        )
        set({ autostart: true })
        await vi.waitFor(() =>
          expect(H.loginItems.some((s) => s.openAtLogin === true)).toBe(true)
        )
        expect(H.diag).toContain('[diag] autostart true')
      } finally {
        H.isPackaged = false
        resetPlatform()
      }
    })
  })
})
