import {
  app,
  BrowserWindow,
  clipboard,
  ipcMain,
  Menu,
  nativeImage,
  Notification,
  shell,
  Tray,
  type MenuItemConstructorOptions
} from 'electron'
import { spawn } from 'child_process'
import { existsSync, mkdirSync } from 'fs'
import { dirname, join } from 'path'
import * as settings from './settings'
import { ApiService, type LaunchSpec } from './service'
import { runDoctor } from './doctor'
import { createProjectsClient, type ProjectsClient } from './projects'
import { createTasksClient, type TasksClient } from './tasks'
import { launchFlags, resolveLaunchCommand, spawnOnBoot, type ResolvedLaunchCommand } from './launch'
import { gitAvailable } from './git'
import { ensureWorkspace } from './workspace'
import {
  DONE,
  NOT_PASSING,
  NotificationTracker,
  notPassingCount,
  notificationBody,
  type NotifiableTask
} from './desktop'
import type {
  AboutInfo,
  DesktopSettings,
  ProjectCreatePayload,
  ProjectPatch,
  TaskCreatePayload
} from '../preload/types'

// The app's display name is now "Taskproof", but Electron derives `userData`
// from the package name -- so a rename (or a bumped productName) would silently
// move the directory and orphan the user's settings.json. Pin it to the
// historical `.../Application Support/taskproof-desktop` path, before anything
// reads it, so upgrades keep the same file.
const userDataDir = join(app.getPath('appData'), 'taskproof-desktop')
mkdirSync(userDataDir, { recursive: true })
app.setPath('userData', userDataDir)

let mainWindow: BrowserWindow | null = null

/**
 * TEST SEAM, *not* a user setting: the acceptance harness points this at a fake
 * bundled runtime (`<tmp>/res/python/bin/python3` plus `<resources>/src`). A
 * shipped app always reads `process.resourcesPath`, the directory Electron
 * fills beside the app bundle. It is never stored in settings.json and never
 * shown in the UI.
 */
function resourcesPath(): string {
  return process.env.TASKPROOF_RESOURCES || process.resourcesPath
}

/**
 * The OS the OS-integration paths (Dock badge, login item) branch on. Normally
 * this is exactly `process.platform`.
 *
 * TEST SEAM, *not* a user setting: the acceptance harness points
 * `TP_DESKTOP_PLATFORM` at another OS so the non-native branches really execute
 * on a machine of any OS -- CI runs Linux, and a macOS dev can drive the
 * linux/win32 branches without a second box. A shipped app sets no such
 * variable and reads the real `process.platform`. Read live (not cached) so the
 * harness can flip it mid-run.
 */
function platform(): NodeJS.Platform {
  return (process.env.TP_DESKTOP_PLATFORM as NodeJS.Platform | undefined) ?? process.platform
}

/**
 * Resolve the child's command for a given settings snapshot, from the live
 * environment. Kept per-snapshot so a settings change can compare its before
 * and after argv without the cached `settings.get()` having already moved on.
 */
function resolveFor(current: DesktopSettings): ResolvedLaunchCommand {
  return resolveLaunchCommand({
    setting: current.taskproofPath,
    resourcesPath: resourcesPath(),
    pathEnv: process.env.PATH ?? '',
    platform: process.platform,
    exists: existsSync
  })
}

/** The full argv (resolved command + launch flags) for a settings snapshot. */
function argvFor(current: DesktopSettings): string[] {
  return [...resolveFor(current).argv, ...launchFlags(current)]
}

/**
 * The child's argv, recomputed on every spawn -- so a settings change that lands
 * mid-session is honoured by the restart the settings handler triggers, not only
 * on the next app launch. Every decision (setting vs bundled vs PATH vs python3,
 * and the augmented PATH handed to the child) comes from `resolveLaunchCommand`,
 * which is what makes the settings page's "source" line truthful.
 */
function launchSpec(): LaunchSpec {
  const current = settings.get()
  const resolved = resolveFor(current)
  const spec: LaunchSpec = {
    command: resolved.argv[0],
    // The global `--workspace` flag precedes the subcommand; `--allow-write`
    // belongs to `api` and opens the token-protected write surface.
    args: [...resolved.argv.slice(1), ...launchFlags(current)],
    workspace: current.workspace,
    env: resolved.env
  }
  diag(`spawn ${spec.command} ${spec.args.join(' ')}`)
  return spec
}

const api = new ApiService(launchSpec)

/**
 * The write client, rebuilt whenever the service comes up on a new port or a
 * new token. Everything that talks HTTP-with-a-token goes through here; the
 * renderer only ever sees the named IPC methods below.
 */
let projectsClient: ProjectsClient | null = null
let tasksClient: TasksClient | null = null
/** `${port}:${token}` at the moment both clients were minted. A service
 *  restart changes both, so this is the single trigger that re-mints them. */
let clientKey = ''

/**
 * Both write clients are minted together, off the same port/token snapshot.
 * Keeping them in one place means a restart swaps them atomically -- there is
 * no window where the registry client has the new token and the task client
 * still holds the old one.
 */
function ensureClients(): { projects: ProjectsClient; tasks: TasksClient } {
  const port = api.getStatus().port
  const token = api.getToken() ?? ''
  const key = `${port}:${token}`
  if (!projectsClient || !tasksClient || clientKey !== key) {
    const baseUrl = port ? `http://127.0.0.1:${port}` : ''
    projectsClient = createProjectsClient({ baseUrl, token })
    tasksClient = createTasksClient({ baseUrl, token })
    clientKey = key
  }
  return { projects: projectsClient, tasks: tasksClient }
}

function projects(): ProjectsClient {
  return ensureClients().projects
}

/** The task control client. Same token, same lifetime, different surface. */
function tasks(): TasksClient {
  return ensureClients().tasks
}

// ---------------------------------------------------------------------------
// Desktop integration: tray, Dock badge, notifications, launch-at-login.
//
// These are the switches the settings page used to only persist. The renderer
// owns the *data* it already polls, but the read endpoints are not token-gated,
// so the main process reads `/api/summary` and `/api/tasks` itself -- one owner
// for the badge and the notification de-duplication, and the write token stays
// where it belongs (this process).
// ---------------------------------------------------------------------------

/** How often the main process re-reads the API while a switch needs the data. */
const DESKTOP_POLL_MS = 2_000
/** One poll's task window; the badge comes from the exact `/api/summary` counts
 *  so a row beyond this window still can't undercount it. */
const TASK_SCAN_LIMIT = 1_000

let tray: Tray | null = null
/** The loaded mark's template flag, cached for the diagnostic assertion. */
let trayTemplate = false
/** Set on `before-quit`, so the close-to-tray interceptor gets out of the way
 *  and a real Quit actually tears the window (and the child) down. */
let quitting = false
let desktopTimer: ReturnType<typeof setInterval> | undefined
let lastSummary: Record<string, number> | null = null
const notifier = new NotificationTracker()

/**
 * Gated diagnostic trace. Off unless `TP_DESKTOP_DIAG` is set, so a normal run
 * stays silent; when it is set the main process narrates the desktop state it
 * cannot otherwise show -- the menu-bar mark, the Dock badge, the exact argv it
 * spawns, every notification -- to stdout. This is how a headless check asserts
 * the switches really took effect, rather than reading the UI by eye.
 */
function diag(message: string): void {
  if (process.env.TP_DESKTOP_DIAG) process.stdout.write(`[diag] ${message}\n`)
}

/** True while at least one switch needs the API polled for it. */
function desktopFeaturesOn(): boolean {
  const current = settings.get()
  return current.dockBadge || current.notifyFail || current.notifyDone
}

/** A child that exists (or is on its way up); a failed/stopped one does not. */
function serviceRunning(): boolean {
  const state = api.getStatus().state
  return state === 'starting' || state === 'ready'
}

/** The menu-bar mark, loaded from the repo's `build/` beside the app icon. */
function trayImage(): Electron.NativeImage {
  const image = nativeImage.createFromPath(join(app.getAppPath(), 'build', 'trayTemplate.png'))
  // The `Template` suffix already carries the macOS semantics; this is the belt
  // to that suspenders, as the card asks.
  image.setTemplateImage(true)
  const size = image.getSize()
  trayTemplate = image.isTemplateImage()
  diag(
    `trayImage template=${trayTemplate} empty=${image.isEmpty()} size=${size.width}x${size.height}`
  )
  return image
}

function showWindow(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow()
    return
  }
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.show()
  mainWindow.focus()
}

function hideWindow(): void {
  mainWindow?.hide()
}

/** The menu-bar click and the diagnostic "click" share this one path. */
function onTrayClick(): void {
  showWindow()
}

/**
 * Build or destroy the tray to match the switch. Idempotent: flipping the switch
 * back and forth creates once and destroys once, never a second orphaned icon.
 */
function syncTray(): void {
  if (settings.get().tray) {
    if (tray) return
    tray = new Tray(trayImage())
    tray.setToolTip('Taskproof')
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: '唤回窗口', click: () => showWindow() },
        { label: '隐藏窗口', click: () => hideWindow() },
        { type: 'separator' },
        { label: '退出 Taskproof', click: () => app.quit() }
      ])
    )
    tray.on('click', () => onTrayClick())
    diag('tray created')
    return
  }
  if (tray) {
    tray.destroy()
    tray = null
    diag('tray destroyed')
  }
}

/**
 * Paint the Dock badge from the latest summary. `n == 0` (and a missing summary,
 * and the switch being off) all clear it, so a badge never outlives its facts.
 */
function applyBadge(): void {
  // The Dock badge is macOS-only. Anywhere else there is no Dock to paint, so
  // say so out loud rather than returning silently -- a user who wonders why the
  // badge never appears gets a clue, and the skip is assertable on any host.
  if (platform() !== 'darwin' || !app.dock) {
    diag('dock badge skipped: unsupported on this platform')
    return
  }
  if (!settings.get().dockBadge || lastSummary === null) {
    app.dock.setBadge('')
    return
  }
  const n = notPassingCount(lastSummary)
  app.dock.setBadge(n > 0 ? String(n) : '')
  diag(`badge ${n > 0 ? n : '(clear)'}`)
}

/**
 * `app.setLoginItemSettings` is a macOS + Windows API; every other platform has
 * no login-item mechanism to align with, so the switch is a no-op there.
 */
function supportsLoginItems(): boolean {
  const p = platform()
  return p === 'darwin' || p === 'win32'
}

/**
 * Align the login item with the switch. macOS and Windows are the platforms
 * this is for.
 *
 * Only a *packaged* build may touch the OS login items. In a dev run
 * (`app.isPackaged === false`) the executable is `node_modules/electron`, so
 * `setLoginItemSettings` would drop a stray login item literally named
 * "Electron" pointing at the dev binary -- and leave it behind when the run
 * ends. So a dev build never calls it; the switch only takes effect once the
 * app is packaged. The diagnostic output says so, too.
 */
function syncAutostart(): void {
  // No login-item mechanism here: leave the OS strictly alone and say why, so
  // the skip is observable instead of silent.
  if (!supportsLoginItems()) {
    diag('autostart skipped: unsupported platform')
    return
  }
  if (!app.isPackaged) {
    diag('autostart skipped: not packaged (takes effect only in a packaged build)')
    return
  }
  const openAtLogin = Boolean(settings.get().autostart)
  app.setLoginItemSettings({ openAtLogin })
  diag(`autostart ${openAtLogin}`)
}

async function readJson(url: string): Promise<unknown> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`GET ${url} -> ${response.status}`)
  return response.json()
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : null
}

function storeSummary(summary: unknown): void {
  const record = asRecord(summary)
  if (!record) {
    lastSummary = null
    return
  }
  const counts: Record<string, number> = {}
  for (const [status, value] of Object.entries(record)) {
    if (typeof value === 'number') counts[status] = value
  }
  lastSummary = counts
}

function raiseNotification(title: string, task: NotifiableTask): void {
  if (!Notification.isSupported()) {
    diag(`notify-unsupported ${task.id}`)
    return
  }
  diag(`notify ${title} ${task.id}`)
  new Notification({ title, body: notificationBody(task) }).show()
}

/**
 * How long to wait between poll-driven attempts to (re)establish the port.
 *
 * The stdout handshake already gives a slow child a whole timeout window to
 * announce itself, so this only spaces out attempts when a child fails
 * *instantly* -- and keeps a broken binary from spawn-looping on every tick.
 */
const START_BACKOFF_MS = 5_000
/** The last time a poll-driven start was issued; 0 means "never". */
let lastStartAttempt = 0

/**
 * Re-establish the connection when a poll finds no port.
 *
 * The port is read from the child's stdout exactly once, with a timeout; if that
 * read times out the child is killed and the app would otherwise stay "not
 * connected" forever -- a slow machine would never recover. Retrying here lets
 * the next tick re-spawn and re-read the port. It never guesses a port, and
 * `launch: 'manual'` is left alone: there the user starts the service.
 */
function recoverPort(): void {
  if (quitting) return
  if (!spawnOnBoot(settings.get().launch)) return
  const state = api.getStatus().state
  // Already coming up (or up): the port reader is still listening, so just wait.
  if (state === 'starting' || state === 'ready') return
  const now = Date.now()
  if (now - lastStartAttempt < START_BACKOFF_MS) return
  lastStartAttempt = now
  diag(`poll retry: no port yet (service ${state}); restarting`)
  void api.start()
}

async function pollDesktop(): Promise<void> {
  const port = api.getStatus().port
  if (!port) {
    lastSummary = null
    applyBadge()
    // "No port" must be its own unmissable line. It used to print only the Dock
    // skip -- exactly what a *real* poll prints off macOS -- so a stuck port and
    // a working poll looked identical in the trace. That was the CI blind spot.
    diag('poll skipped: no port yet')
    recoverPort()
    return
  }
  const current = settings.get()
  const base = `http://127.0.0.1:${port}`
  try {
    if (current.dockBadge) {
      storeSummary(asRecord(await readJson(`${base}/api/summary`))?.summary)
    } else {
      lastSummary = null
    }
    applyBadge()

    let taskCount = 0
    if (current.notifyFail || current.notifyDone) {
      const rawTasks = asRecord(await readJson(`${base}/api/tasks?limit=${TASK_SCAN_LIMIT}`))?.tasks
      const rows: unknown[] = Array.isArray(rawTasks) ? rawTasks : []
      const tasks: NotifiableTask[] = []
      for (const row of rows) {
        const record = asRecord(row)
        if (!record) continue
        tasks.push({
          id: String(record.id ?? ''),
          status: String(record.status ?? ''),
          project: record.project ? String(record.project) : undefined
        })
      }
      taskCount = tasks.length
      if (!notifier.isPrimed) {
        // The first task list of this launch only *seeds*: every id that is
        // already here (the entire backlog) is remembered, and nothing fires.
        // Otherwise a fresh start would re-notify every historical card.
        notifier.seed(tasks)
      } else {
        if (current.notifyFail) {
          for (const task of notifier.claim(tasks, NOT_PASSING)) raiseNotification('验收未通过', task)
        }
        if (current.notifyDone) {
          for (const task of notifier.claim(tasks, DONE)) raiseNotification('任务完成', task)
        }
      }
    }
    // The one line that proves a *real* poll happened: the port it read and how
    // many tasks came back. Emitted after the seed/claim, so a waiter that sees
    // it can trust the first-poll seeding already happened.
    diag(`poll port=${port} tasks=${taskCount}`)
  } catch (error) {
    // The service may be mid-restart; the next tick tries again rather than
    // clearing a badge on one dropped read.
    lastSummary = null
    applyBadge()
    const detail = error instanceof Error ? error.message : String(error)
    diag(`poll failed port=${port}: ${detail}`)
  }
}

/** Start the pump only while a switch needs it; stop it the moment they do not. */
function syncDesktopPoll(): void {
  if (desktopFeaturesOn()) {
    if (!desktopTimer) {
      void pollDesktop()
      desktopTimer = setInterval(() => void pollDesktop(), DESKTOP_POLL_MS)
    }
    return
  }
  stopDesktopPoll()
}

function stopDesktopPoll(): void {
  if (desktopTimer) clearInterval(desktopTimer)
  desktopTimer = undefined
}

/**
 * Reconcile everything a settings patch can touch. Called for every successful
 * write, so the switches are true behaviour the instant they land -- no restart
 * of the app required.
 */
function onSettingsChanged(before: DesktopSettings, after: DesktopSettings): void {
  if (before.tray !== after.tray) syncTray()
  if (before.autostart !== after.autostart) syncAutostart()
  if (before.dockBadge !== after.dockBadge) applyBadge()

  const argvChanged = argvFor(before).join('\u0000') !== argvFor(after).join('\u0000')
  if (argvChanged) {
    // A changed argv only takes effect on a fresh child. A manual service that
    // is not running stays down -- the user starts it when they are ready.
    if (serviceRunning() || after.launch === 'auto') void api.start()
  } else if (before.launch !== 'auto' && after.launch === 'auto') {
    // Manual -> auto: the promise is "open the window and it is up".
    void api.start()
  }
  syncDesktopPoll()
}

/**
 * The About sheet's version trio, part three: `taskproof --version`.
 *
 * The CLI may not be installed (the app is happy to run without it), may be a
 * wrapper that prints extra text, or may be pointed at a source checkout
 * (`python -m taskproof`). So the raw stdout is scraped for a semver-shaped
 * token and anything else -- a crash, a missing binary, a bare "command
 * not found" -- becomes null, which the sheet renders as an em dash. There is
 * deliberately no error surface here: a missing CLI must never break the app.
 */
export function parseCliVersion(raw: string | null | undefined): string | null {
  if (raw == null) return null
  const match = String(raw).match(/(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)/)
  return match ? match[1] : null
}

const CLI_VERSION_TIMEOUT_MS = 5_000

/** Run `taskproof --version` and return the parsed version, or null. */
function runCliVersion(): Promise<string | null> {
  const resolved = resolveFor(settings.get())
  const argv = [...resolved.argv, '--version']
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(argv[0], argv.slice(1), {
        stdio: ['ignore', 'pipe', 'ignore'],
        env: { ...process.env, ...resolved.env }
      })
    } catch {
      resolve(null)
      return
    }

    let out = ''
    let settled = false
    const finish = (value: string | null): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(value)
    }
    const timer = setTimeout(() => {
      child.kill()
      finish(null)
    }, CLI_VERSION_TIMEOUT_MS)

    child.stdout?.setEncoding('utf8')
    child.stdout?.on('data', (chunk: string) => {
      out = (out + chunk).slice(-4_096)
    })
    child.once('error', () => finish(null))
    child.once('exit', () => finish(parseCliVersion(out)))
  })
}

/** The About sheet's payload, gathered in the main process. */
async function aboutInfo(): Promise<AboutInfo> {
  return {
    version: app.getVersion(),
    cliVersion: await runCliVersion(),
    runtime: {
      electron: process.versions.electron ?? '',
      chrome: process.versions.chrome ?? '',
      node: process.versions.node ?? ''
    },
    userData: app.getPath('userData')
  }
}

/** Ask the renderer to open the About sheet (used by the app menu). */
function showAbout(): void {
  mainWindow?.webContents.send('tp:app:show-about')
}

/**
 * The macOS application menu, built by hand so the App submenu's first item is
 * our own "About Taskproof" instead of Electron's default `role: 'about'`
 * panel. Edit (copy / paste) and Window are kept so standard shortcuts keep
 * working; `autoHideMenuBar` does not touch the macOS menu bar.
 */
export function appMenuTemplate(onAbout: () => void): MenuItemConstructorOptions[] {
  return [
    {
      label: app.name,
      submenu: [
        { label: '关于 Taskproof', click: () => onAbout() },
        { type: 'separator' },
        { role: 'services' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'pasteAndMatchStyle' },
        { role: 'selectAll' }
      ]
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        { type: 'separator' },
        { role: 'front' }
      ]
    }
  ]
}

function createWindow(): void {
  // In dev the running bundle is Electron's own, so the Dock shows Electron's icon
  // and name unless we say otherwise. Packaged builds pick up build/icon.icns on
  // their own (electron-builder); this line is what makes the dev window show the
  // real mark. macOS only -- there is no app.dock on the other platforms.
  if (process.platform === 'darwin' && app.dock) {
    // setIcon throws when the image cannot be loaded, and this runs inside the
    // async path that creates the window: one missing asset (a packaging mistake)
    // meant the app came up with no window at all. Degrade to "no dock icon".
    const icon = nativeImage.createFromPath(join(app.getAppPath(), 'build', 'icon.png'))
    if (icon.isEmpty()) {
      diag('dock icon missing; skipping setIcon')
    } else {
      app.dock.setIcon(icon)
    }
  }

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 700,
    show: false,
    autoHideMenuBar: true,
    // Keep the OS traffic lights and inset them over our own mast, which
    // reserves 78px on the left for them. The prototype's three dots are a
    // browser mockup, so they are deliberately not ported.
    titleBarStyle: 'hiddenInset',
    // Matches the dark canvas, so there is no white flash before the renderer
    // paints.
    backgroundColor: '#1c1c1e',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow?.show())

  // Close-to-tray: while the switch is on, the close button hides the window
  // instead of tearing it down, so the child keeps serving and the
  // notifications keep firing. The application menu's Quit still exits -- the
  // `quitting` flag is how it gets past this.
  mainWindow.on('close', (event) => {
    if (!quitting && settings.get().tray) {
      event.preventDefault()
      mainWindow?.hide()
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Never open a second Electron window for a link; hand it to the OS.
    void shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function registerIpc(): void {
  // Test-only assertions, present only under TP_DESKTOP_DIAG. They report the
  // main-process state a renderer cannot observe otherwise (the menu-bar mark,
  // the real Dock badge) and let a headless check drive the tray-click path.
  if (process.env.TP_DESKTOP_DIAG) {
    ipcMain.handle('tp:diag:state', () => ({
      tray: tray !== null,
      trayTemplate,
      badge: platform() === 'darwin' && app.dock ? app.dock.getBadge() : '',
      windowVisible: Boolean(mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible())
    }))
    ipcMain.handle('tp:diag:tray-click', () => {
      onTrayClick()
      return true
    })
  }
  ipcMain.handle('tp:service:status', () => api.getStatus())
  ipcMain.handle('tp:service:restart', () => api.start())
  ipcMain.handle('tp:settings:get', () => settings.get())
  ipcMain.handle('tp:settings:set', (_event, patch: Partial<DesktopSettings>) => {
    const before = settings.get()
    const next = settings.set(patch)
    // The switches are behaviour, not decoration: reconcile the tray, the badge,
    // the login item and (when the argv changed) the child right here.
    onSettingsChanged(before, next)
    return next
  })
  ipcMain.handle('tp:shell:open-path', async (_event, target: string) => {
    await shell.openPath(String(target))
  })
  // The About sheet's paths may not exist yet (the store, this month's log).
  // `openPath` on a missing file opens nothing, so fall back to the directory
  // that would hold it -- the user can still get to the data location.
  ipcMain.handle('tp:shell:reveal', async (_event, target: string) => {
    const path = String(target)
    const toOpen = existsSync(path) ? path : dirname(path)
    await shell.openPath(toOpen)
  })
  ipcMain.handle('tp:shell:open-external', async (_event, url: string) => {
    // Only ever hand http(s) to the OS; a `file:`/custom scheme here would be
    // an escalation. The renderer only ever passes the source repo link.
    const target = String(url)
    if (/^https?:\/\//i.test(target)) await shell.openExternal(target)
  })
  ipcMain.handle('tp:app:version', () => app.getVersion())
  ipcMain.handle('tp:app:about', () => aboutInfo())
  // Spelled out rather than `clipboard.writeText(text)` inline so the channel
  // is greppable: this is the only place diagnostic text reaches the clipboard,
  // and the text is assembled in the renderer (which never holds the token).
  ipcMain.handle('tp:app:copy-text', (_event, text: string) => {
    clipboard.writeText(String(text))
  })
  // The About group's adapter lamps. The API has no adapter endpoint, so this
  // is the CLI's own self-check; it resolves null when it cannot answer.
  ipcMain.handle('tp:app:adapters', () => {
    const resolved = resolveFor(settings.get())
    return runDoctor({
      command: resolved.argv[0],
      prefixArgs: resolved.argv.slice(1),
      workspace: settings.get().workspace,
      env: resolved.env
    })
  })
  // The settings page's read-only diagnostics: the *effective* launch command
  // (its source and its full argv, so "which taskproof?" is checkable) and the
  // git verdict. Both come from the same resolution the child uses -- no second,
  // staler answer.
  ipcMain.handle('tp:app:diagnostics', async () => {
    const resolved = resolveFor(settings.get())
    return {
      launch: { source: resolved.source, argv: argvFor(settings.get()) },
      gitAvailable: await gitAvailable(resolved.env)
    }
  })

  // Registry writes. Each answers with a typed result; the token and the
  // expected_hash handshake stay in this process.
  ipcMain.handle('tp:projects:registry', () => projects().registry())
  ipcMain.handle('tp:projects:probe', (_event, path: string) => projects().probe(String(path)))
  ipcMain.handle('tp:projects:create', (_event, payload: ProjectCreatePayload) =>
    projects().create(payload)
  )
  ipcMain.handle('tp:projects:patch', (_event, id: string, patch: ProjectPatch) =>
    projects().patch(String(id), patch)
  )
  ipcMain.handle('tp:projects:remove', (_event, id: string) => projects().remove(String(id)))

  // Task control. Same narrow shape as the registry writes above: the token and
  // the HTTP verb stay in this process, the renderer gets a typed result.
  ipcMain.handle('tp:tasks:create', (_event, payload: TaskCreatePayload) =>
    tasks().create(payload)
  )
  ipcMain.handle('tp:tasks:advance', (_event, id: string) => tasks().advance(String(id)))
  ipcMain.handle('tp:tasks:cancel', (_event, id: string) => tasks().cancel(String(id)))
  ipcMain.handle('tp:tasks:accept', (_event, id: string) => tasks().accept(String(id)))
  ipcMain.handle('tp:tasks:remove', (_event, id: string) => tasks().remove(String(id)))
  ipcMain.handle('tp:tasks:patch-queue-seq', (_event, id: string, seq: number | null) =>
    tasks().patchQueueSeq(String(id), seq)
  )
}

api.onStatus((status) => {
  mainWindow?.webContents.send('tp:service:changed', status)
  // A port change invalidates the last summary; re-read (or clear) on the next
  // tick. The badge and the pump follow the service's own lifecycle.
  if (!status.port) lastSummary = null
  applyBadge()
  syncDesktopPoll()
})

app.whenReady().then(async () => {
  app.setAppUserModelId('com.taskproof.desktop')
  // First boot: make the workspace real (directory + a minimal, project-less
  // registry) before anything reads it, so a fresh install is usable instead of
  // quietly pointing at a directory that isn't there. Never touches tasks, never
  // overwrites an existing file.
  ensureWorkspace(settings.get().workspace)
  registerIpc()
  Menu.setApplicationMenu(Menu.buildFromTemplate(appMenuTemplate(showAbout)))
  createWindow()
  // Warm the git verdict in the background: a missing git is a settings-page
  // notice, never a boot gate -- the app must come up with or without it.
  void gitAvailable(resolveFor(settings.get()).env)
  // The desktop switches are aligned once at boot. `launch` is the only one that
  // decides whether a child exists at all.
  syncTray()
  syncAutostart()
  // Start the service (when it is meant to be up) *before* the pump, so the first
  // poll sees either a real port or a start in progress -- never a bare "no port"
  // that would make it try to re-spawn the very child we are about to start.
  if (spawnOnBoot(settings.get().launch)) {
    await api.start()
  } else {
    applyBadge()
  }
  syncDesktopPoll()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// The child server must not outlive the app, however the app ends.
app.on('before-quit', () => {
  quitting = true
  stopDesktopPoll()
  if (tray) {
    tray.destroy()
    tray = null
  }
  api.stop()
})
process.on('exit', () => api.stop())
