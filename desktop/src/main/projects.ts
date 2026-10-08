/**
 * The main process's client for the registry write surface.
 *
 * Two things live here, and nowhere else:
 *
 *  - the write token. It is read from the child's stdout (see `service.ts`) and
 *    attached as `X-Taskproof-Token` on every mutation. It is never returned to
 *    the renderer, never written to disk, never logged.
 *  - the optimistic-write handshake. Before any mutation we read
 *    `GET /api/registry` and carry that hash into the request as
 *    `expected_hash`. A `409` means the file changed since we looked; it is
 *    handed back to the caller as a structured conflict and **never retried**.
 *
 * Only the standard fetch is used, and it is injectable so the shape of every
 * branch (success / 409 / 400 / network) can be pinned by a unit test.
 */
import type {
  ConflictSnapshot,
  ProbeRecord,
  ProjectCreatePayload,
  ProjectPatch,
  ProjectRecord,
  RegistryMeta,
  RegistryResult,
  WriteError
} from '../preload/types'

export interface ProjectsClient {
  registry(): Promise<RegistryResult<RegistryMeta>>
  probe(path: string): Promise<RegistryResult<ProbeRecord>>
  create(payload: ProjectCreatePayload): Promise<RegistryResult<{ project: ProjectRecord }>>
  patch(id: string, patch: ProjectPatch): Promise<RegistryResult<{ project: ProjectRecord }>>
  remove(id: string): Promise<RegistryResult<{ removed: string }>>
}

export interface ProjectsClientOptions {
  /** e.g. `http://127.0.0.1:51234`; empty while the service is not up. */
  baseUrl: string
  token: string
  /** Injectable for tests; defaults to the process-global fetch. */
  fetch?: typeof fetch
}

function plainObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : null
}

/** The server's `{"error": "..."}` message, or a per-status fallback. */
function messageOf(body: unknown, fallback: string): string {
  const record = plainObject(body)
  const message = record?.error
  return typeof message === 'string' && message ? message : fallback
}

function conflictOf(body: unknown): ConflictSnapshot {
  const record = plainObject(body) ?? {}
  const projects = record.projects
  return {
    hash: typeof record.hash === 'string' ? record.hash : '',
    content: typeof record.content === 'string' ? record.content : '',
    projects: Array.isArray(projects) ? (projects as ProjectRecord[]) : []
  }
}

/** Map a non-2xx response onto the typed failure the renderer switches on. */
export function classifyFailure(status: number, body: unknown): WriteError {
  if (status === 409) {
    return {
      kind: 'conflict',
      status,
      message: 'the registry changed on disk since it was read',
      conflict: conflictOf(body)
    }
  }
  if (status === 403) {
    return { kind: 'forbidden', status, message: messageOf(body, 'forbidden') }
  }
  if (status === 404) {
    return { kind: 'notfound', status, message: messageOf(body, 'no such project') }
  }
  if (status === 400) {
    return { kind: 'invalid', status, message: messageOf(body, 'invalid request') }
  }
  // 405 (write surface closed) and anything unexpected: still a failure, still
  // carries the server's message when it gave one.
  return { kind: 'invalid', status, message: messageOf(body, `the service answered ${status}`) }
}

export function createProjectsClient(options: ProjectsClientOptions): ProjectsClient {
  const doFetch = options.fetch ?? fetch
  const tokenHeader: Record<string, string> = { 'x-taskproof-token': options.token }

  async function request<T>(path: string, init: RequestInit): Promise<RegistryResult<T>> {
    let response: Response
    try {
      response = await doFetch(options.baseUrl + path, init)
    } catch (cause) {
      return {
        ok: false,
        error: {
          kind: 'network',
          status: 0,
          message: `cannot reach the local service: ${String(cause)}`
        }
      }
    }
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    if (response.ok) return { ok: true, value: body as T }
    return { ok: false, error: classifyFailure(response.status, body) }
  }

  function get<T>(path: string): Promise<RegistryResult<T>> {
    return request<T>(path, { headers: { accept: 'application/json' } })
  }

  function mutate<T>(path: string, method: string, payload: unknown): Promise<RegistryResult<T>> {
    return request<T>(path, {
      method,
      headers: { accept: 'application/json', 'content-type': 'application/json', ...tokenHeader },
      body: JSON.stringify(payload)
    })
  }

  /** Read the hash, then fold it into the mutation body as `expected_hash`. */
  async function withHash<T>(
    build: (expectedHash: string) => Promise<RegistryResult<T>>
  ): Promise<RegistryResult<T>> {
    const meta = await get<RegistryMeta>('/api/registry')
    if (!meta.ok) return meta
    return build(meta.value.hash)
  }

  return {
    registry: () => get<RegistryMeta>('/api/registry'),

    probe: (path) =>
      mutate<ProbeRecord>('/api/projects/probe', 'POST', { path: String(path) }),

    create: (payload) =>
      withHash((expected_hash) =>
        mutate<{ project: ProjectRecord }>('/api/projects', 'POST', { ...payload, expected_hash })
      ),

    patch: (id, patch) =>
      withHash((expected_hash) =>
        mutate<{ project: ProjectRecord }>(
          `/api/projects/${encodeURIComponent(String(id))}`,
          'PATCH',
          { ...patch, expected_hash }
        )
      ),

    remove: (id) =>
      withHash((expected_hash) =>
        mutate<{ removed: string }>(
          `/api/projects/${encodeURIComponent(String(id))}`,
          'DELETE',
          { expected_hash }
        )
      )
  }
}
