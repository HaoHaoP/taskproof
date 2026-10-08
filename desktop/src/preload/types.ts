/**
 * Types shared across the process boundary.
 *
 * The renderer's view of the main process is exactly this: a small, named
 * surface. There is deliberately no generic `invoke(channel, payload)` -- that
 * would hand the entire IPC surface to a renderer that loads remote-ish content
 * and renders agent output.
 *
 * Registry writes go through `TpApi.projects`. That surface is deliberately
 * narrow: it speaks in these result types, and the write token lives only in the
 * main process. The renderer asks for "create this project" and gets back either
 * the new record or a structured failure -- never a token, never an HTTP verb.
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

export interface DesktopSettings {
  theme: ThemeChoice
  language: LanguageChoice
  poll: PollChoice
  /** Workspace holding the SQLite store and projects.toml. */
  workspace: string
  /** Path to the taskproof executable (or a python it can be run with). */
  taskproofPath: string
}

// -- registry --------------------------------------------------------------

/** `GET /api/registry`: the optimistic-write handshake. */
export interface RegistryMeta {
  path: string
  /** SHA-256 of the registry's raw bytes, lowercase hex. */
  hash: string
  mtime: number
}

/**
 * The acceptance-probe verdict. The API can report `null` for a project that
 * declares a verify command it has never run; the UI folds that into `none`.
 */
export type ProbeVerdict = 'passed' | 'failed' | 'none'

/** A project as the API returns it (list, create, patch). */
export interface ProjectRecord {
  id: string
  path: string
  group: string
  aliases: string[]
  verify: string | null
  verify_kind: string
  forbidden_paths: string[]
  result_schema: string
  auto_registered: boolean
  probe: ProbeVerdict | null
  probe_exit: number | null
}

/** `POST /api/projects/probe` -- the registration draft, before it is stored. */
export interface ProbeRecord {
  id: string
  path: string
  group: string
  verify: string | null
  verify_kind: string
  probe: ProbeVerdict | null
  probe_exit: number | null
  aliases: string[]
  forbidden_paths: string[]
}

/**
 * The body of a `409 conflict`: the registry changed on disk since we read the
 * hash. Nothing was written; the caller decides whether to reload or re-apply.
 */
export interface ConflictSnapshot {
  /** The hash of the file *now* -- what a retry would have to build on. */
  hash: string
  /** The file text at the moment of the clash, so the user can see the drift. */
  content: string
  projects: ProjectRecord[]
}

/**
 * How a registry request failed, mirroring the HTTP contract:
 *  - `conflict`  409 -- the registry changed under us; nothing was written
 *  - `invalid`   400 -- a field was rejected
 *  - `forbidden` 403 -- the token was missing or wrong
 *  - `notfound`  404 -- no such project id
 *  - `network`   the request never reached a response
 */
export type WriteErrorKind = 'conflict' | 'invalid' | 'forbidden' | 'notfound' | 'network'

export interface WriteError {
  kind: WriteErrorKind
  status: number
  /** Human copy from the server, or the transport error. Never the token. */
  message: string
  /** Present only when `kind === 'conflict'`. */
  conflict?: ConflictSnapshot
}

/** Every registry call answers with this: a value, or a typed failure. */
export type RegistryResult<T> = { ok: true; value: T } | { ok: false; error: WriteError }

export interface ProjectCreatePayload {
  path: string
  id?: string
  group?: string
  aliases?: string[]
  verify?: string | null
  verify_kind?: string
  forbidden_paths?: string[]
  /** The probe verdict, so it is stored alongside the registration. */
  probe?: string | null
  probe_exit?: number | null
}

/** Mutable project fields. `id` and `path` are immutable and not accepted. */
export interface ProjectPatch {
  aliases?: string[]
  group?: string
  verify?: string | null
  verify_kind?: string
  forbidden_paths?: string[]
  result_schema?: string
}

export interface ProjectsApi {
  registry(): Promise<RegistryResult<RegistryMeta>>
  probe(path: string): Promise<RegistryResult<ProbeRecord>>
  create(payload: ProjectCreatePayload): Promise<RegistryResult<{ project: ProjectRecord }>>
  patch(id: string, patch: ProjectPatch): Promise<RegistryResult<{ project: ProjectRecord }>>
  remove(id: string): Promise<RegistryResult<{ removed: string }>>
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
  /**
   * Registry writes. Every method answers with a `RegistryResult`, never
   * throwing across the IPC boundary -- a rejected promise would lose the shape
   * the UI needs (which failure, and the conflict body).
   */
  projects: ProjectsApi
}
