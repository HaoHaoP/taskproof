/**
 * Types shared across the process boundary.
 *
 * The renderer's view of the main process is exactly this: a small, named
 * surface. There is deliberately no generic `invoke(channel, payload)` -- that
 * would hand the entire IPC surface to a renderer that loads remote-ish content
 * and renders agent output.
 *
 * The console is read-only: it reads the local API's board and drives the
 * service, settings, shell and app-menu surfaces. All project registration and
 * task dispatching live in the CLI; there is no write method here, and the app
 * never carries an API token.
 */

export type ServiceState = 'starting' | 'ready' | 'stopped' | 'failed'

export interface ServiceStatus {
  state: ServiceState
  /** The port the child actually bound, or null before it is up. */
  port: number | null
  workspace: string
  detail: string
}

export type ThemeChoice = 'system' | 'dark' | 'light'
export type LanguageChoice = 'system' | 'zh-CN' | 'en'
/** How often the renderer re-reads the local API; 'off' means only on demand. */
export type PollChoice = '2s' | 'off'
/** 'auto' lets the OS pick a free port; 'fixed' pins `port`. */
export type PortMode = 'auto' | 'fixed'
/** Whether the app spawns the local API itself on open ('auto') or not. */
export type LaunchMode = 'auto' | 'manual'

export interface DesktopSettings {
  theme: ThemeChoice
  language: LanguageChoice
  poll: PollChoice
  /** Workspace holding the SQLite store and projects.toml. */
  workspace: string
  /** Path to the taskproof executable (or a python it can be run with). */
  taskproofPath: string
  portMode: PortMode
  /** Only consulted while `portMode` is 'fixed'. */
  port: number
  /** 'auto' spawns the API on open; 'manual' waits for the user. */
  launch: LaunchMode
  notifyFail: boolean
  notifyDone: boolean
  dockBadge: boolean
  tray: boolean
  autostart: boolean
}

/** One adapter's verdict from `taskproof doctor`: installed, or why not. */
export interface AdapterStatus {
  name: string
  installed: boolean
  detail: string
}

/**
 * Where the app's launch argv came from, in the pinned priority order. The
 * settings page renders this so "one install and it works" is checkable, not a
 * claim: the user can see it resolved the bundled runtime, the PATH, or the
 * `python3` fallback.
 */
export type LaunchSource = 'setting' | 'bundled' | 'path' | 'python3'

/** The resolved launch command: its origin and the full argv the app would run. */
export interface LaunchInfo {
  source: LaunchSource
  /** The complete argv, including the launch flags -- copy-pasteable by hand. */
  argv: string[]
}

/** The settings page's read-only diagnostics: the launch command and git. */
export interface DiagnosticsInfo {
  launch: LaunchInfo
  /**
   * False when `git --version` fails on the (augmented) PATH. A missing git
   * disables the gate's worktree / out-of-scope checks but never blocks the app.
   */
  gitAvailable: boolean
}

/**
 * The three runtime versions the About sheet reports. Electron bundles a
 * specific Chromium and Node, so a bug report that only says "the app" is
 * hard to place -- these pin exactly which engine the user was running.
 */
export interface RuntimeVersions {
  electron: string
  chrome: string
  node: string
}

/**
 * Everything the About sheet needs, read once from the main process in a
 * single round trip. `cliVersion` is null when `taskproof --version` could not
 * be run or parsed -- the sheet shows an em dash rather than inventing a
 * number, and never hard-depends on the CLI being installed.
 */
export interface AboutInfo {
  /** `app.getVersion()`. */
  version: string
  /** The parsed `taskproof --version`, or null when it could not be read. */
  cliVersion: string | null
  runtime: RuntimeVersions
  /** `app.getPath('userData')`; the other three paths derive from the workspace. */
  userData: string
}

/**
 * Test-only assertions of main-process state (the menu-bar mark, the real Dock
 * badge, whether the window is hidden). It exists only when the app is launched
 * with `TP_DESKTOP_DIAG`, so the shipped renderer surface stays the narrow,
 * named set above -- this is the "IPC assertion" path the desktop-integration
 * card allows for state a renderer cannot otherwise observe.
 */
export interface DiagApi {
  state(): Promise<{
    tray: boolean
    trayTemplate: boolean
    badge: string
    windowVisible: boolean
  }>
  /** Invoke the exact handler the menu-bar click is wired to. */
  trayClick(): Promise<boolean>
}

export interface TpApi {
  service: {
    status(): Promise<ServiceStatus>
    /** Subscribe to state changes; returns an unsubscribe function. */
    onStatus(listener: (status: ServiceStatus) => void): () => void
    restart(): Promise<ServiceStatus>
  }
  settings: {
    get(): Promise<DesktopSettings>
    set(patch: Partial<DesktopSettings>): Promise<DesktopSettings>
  }
  shell: {
    /** Open a file or directory with the OS default application. */
    openPath(target: string): Promise<void>
    /**
     * Open a path, falling back to its containing directory when the file is
     * not there (the store, the registry, this month's event log may not exist
     * yet). Handing a missing file to `openPath` opens nothing.
     */
    reveal(target: string): Promise<void>
    /** Hand a URL (the source repo) to the OS browser. */
    openExternal(url: string): Promise<void>
  }
  app: {
    version(): Promise<string>
    /**
     * The adapter lamps for the About section: `taskproof doctor --json`'s
     * adapter list, or null when the check could not run. The renderer shows
     * an em dash for null rather than inventing a verdict.
     */
    adapters(): Promise<AdapterStatus[] | null>
    /** App / CLI / runtime versions and the userData path, in one round trip. */
    about(): Promise<AboutInfo>
    /**
     * The resolved launch command (source + full argv) and the git verdict,
     * for the settings page's diagnostic rows. Read-only; never a user setting.
     */
    diagnostics(): Promise<DiagnosticsInfo>
    /** Write the assembed diagnostic text to the system clipboard. */
    copyText(text: string): Promise<void>
    /**
     * The app menu's "About Taskproof" item. Returns an unsubscribe function;
     * the About sheet listens so the native menu opens the same dialog.
     */
    onShowAbout(listener: () => void): () => void
  }
  /** Present only with `TP_DESKTOP_DIAG`; see `DiagApi`. */
  diag?: DiagApi
}
