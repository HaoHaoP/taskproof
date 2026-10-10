/**
 * The main process's client for the task control surface.
 *
 * This is the sibling of `projects.ts`, with one deliberate difference: task
 * writes are **not** registry writes, so there is no `expected_hash` handshake.
 * Every mutation still carries the write token, and the token itself never
 * leaves this process -- the renderer only ever sees a named IPC method's typed
 * result.
 *
 * The one branch that is not a plain success/failure is `429`: a refused spawn.
 * It is not "the task failed" -- nothing changed, so the caller is handed a
 * `concurrency` failure carrying the server's `reason` (`group` vs `cap`) and
 * told to retry later. Conflating it with a hard error would make the UI treat a
 * "retry later" refusal as a permanent one.
 *
 * Only the standard fetch is used, and it is injectable so every branch
 * (success / 409 / 400 / 404 / 429 / network) can be pinned by a unit test.
 */
import type {
  TaskCreatePayload,
  TaskResult,
  TaskRow,
  TaskWriteError
} from '../preload/types'

export interface TasksClient {
  create(payload: TaskCreatePayload): Promise<TaskResult<{ task: TaskRow }>>
  cancel(id: string): Promise<TaskResult<{ task: TaskRow }>>
  accept(id: string): Promise<TaskResult<{ task: TaskRow }>>
  remove(id: string): Promise<TaskResult<{ removed: string }>>
}

export interface TasksClientOptions {
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

/**
 * Map a non-2xx response onto the typed failure the renderer switches on.
 *
 * The reasons are the control plane's, not the registry's: 429 is its own kind
 * (retry later) and 409 is a state conflict (the action does not apply to this
 * row *right now*), never a lost-update conflict.
 */
export function classifyTaskFailure(status: number, body: unknown): TaskWriteError {
  if (status === 429) {
    const record = plainObject(body) ?? {}
    const reason = record.reason === 'cap' ? 'cap' : 'group'
    const detail = typeof record.detail === 'string' ? record.detail : ''
    const hint = typeof record.hint === 'string' ? record.hint : undefined
    return {
      kind: 'concurrency',
      status,
      reason,
      detail,
      hint,
      message: messageOf(body, detail || 'the concurrency gate refused the spawn')
    }
  }
  if (status === 409) {
    return { kind: 'state', status, message: messageOf(body, 'the task is in the wrong state') }
  }
  if (status === 403) {
    return { kind: 'forbidden', status, message: messageOf(body, 'forbidden') }
  }
  if (status === 404) {
    return { kind: 'notfound', status, message: messageOf(body, 'no such task') }
  }
  if (status === 400) {
    return { kind: 'invalid', status, message: messageOf(body, 'invalid request') }
  }
  // 405 (write surface closed) and anything unexpected: still a failure, still
  // carries the server's message when it gave one.
  return { kind: 'invalid', status, message: messageOf(body, `the service answered ${status}`) }
}

export function createTasksClient(options: TasksClientOptions): TasksClient {
  const doFetch = options.fetch ?? fetch
  const tokenHeader: Record<string, string> = { 'x-taskproof-token': options.token }

  async function request<T>(path: string, method: string, payload?: unknown): Promise<TaskResult<T>> {
    let response: Response
    try {
      response = await doFetch(options.baseUrl + path, {
        method,
        headers: {
          accept: 'application/json',
          ...(payload === undefined ? {} : { 'content-type': 'application/json' }),
          ...tokenHeader
        },
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) })
      })
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
    return { ok: false, error: classifyTaskFailure(response.status, body) }
  }

  const segment = (id: string): string => encodeURIComponent(String(id))

  return {
    create: (payload) => request<{ task: TaskRow }>('/api/tasks', 'POST', payload),
    cancel: (id) => request<{ task: TaskRow }>(`/api/tasks/${segment(id)}/cancel`, 'POST'),
    accept: (id) => request<{ task: TaskRow }>(`/api/tasks/${segment(id)}/accept`, 'POST'),
    remove: (id) => request<{ removed: string }>(`/api/tasks/${segment(id)}`, 'DELETE')
  }
}
