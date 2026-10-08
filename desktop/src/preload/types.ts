/**
 * Types shared across the process boundary.
 *
 * The renderer's view of the main process is exactly this: a small, named
 * surface. There is deliberately no generic `invoke(channel, payload)` -- that
 * would hand the entire IPC surface to a renderer that loads remote-ish content
 * and renders agent output.
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

export interface DesktopSettings {
  theme: ThemeChoice
  language: LanguageChoice
  /** Workspace holding the SQLite store and projects.toml. */
  workspace: string
  /** Path to the taskproof executable (or a python it can be run with). */
  taskproofPath: string
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
  }
  app: {
    version(): Promise<string>
  }
}
