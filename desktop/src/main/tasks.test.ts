/**
 * The task write client, pinned branch by branch.
 *
 * Two things a real 429 taught:
 *  - a refused spawn is its own kind (`concurrency`) carrying the server's
 *    `reason` (group vs cap), so the renderer can say "retry later" rather than
 *    "failed",
 *  - every mutation carries the write token; nothing else does. The token never
 *    leaves this process.
 *
 * `createTasksClient` is handed an injectable fetch, so each verb's method,
 * path, and body is asserted without a server.
 */
import { describe, expect, it } from 'vitest'
import { classifyTaskFailure, createTasksClient } from './tasks'
import type { TaskWriteError } from '../preload/types'

const BASE = 'http://127.0.0.1:51234'

function json(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as unknown as Response
}

interface Call {
  url: string
  method: string
  token: string | undefined
  body: Record<string, unknown> | null
}

function recorder(handler: (url: string, init: RequestInit) => Response): {
  fetch: typeof fetch
  calls: Call[]
} {
  const calls: Call[] = []
  const stub = (async (url: string, init: RequestInit = {}) => {
    const headers = (init.headers ?? {}) as Record<string, string>
    calls.push({
      url,
      method: init.method ?? 'GET',
      token: headers['x-taskproof-token'],
      body: init.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null
    })
    return handler(url, init)
  }) as unknown as typeof fetch
  return { fetch: stub, calls }
}

describe('classifyTaskFailure — the control-plane contract', () => {
  it('reads a 429 as a retryable refusal, carrying the reason', () => {
    const group = classifyTaskFailure(429, {
      error: 'concurrency refused',
      reason: 'group',
      detail: "group 'app' is busy",
      hint: 'try again later'
    })
    expect(group).toMatchObject({
      kind: 'concurrency',
      status: 429,
      reason: 'group',
      detail: "group 'app' is busy",
      hint: 'try again later'
    })

    const cap = classifyTaskFailure(429, {
      error: 'concurrency refused',
      reason: 'cap',
      detail: 'cap reached'
    })
    expect(cap.kind).toBe('concurrency')
    expect(cap.reason).toBe('cap')
  })

  it('defaults an unknown 429 reason to group rather than dropping the kind', () => {
    const err = classifyTaskFailure(429, { error: 'concurrency refused' })
    expect(err.kind).toBe('concurrency')
    expect(err.reason).toBe('group')
  })

  it('maps state / invalid / forbidden / notfound by status', () => {
    expect(classifyTaskFailure(409, { error: 'wrong state' }).kind).toBe('state')
    expect(classifyTaskFailure(400, { error: 'bad field' }).kind).toBe('invalid')
    expect(classifyTaskFailure(403, { error: 'nope' }).kind).toBe('forbidden')
    expect(classifyTaskFailure(404, { error: 'gone' }).kind).toBe('notfound')
  })

  it('carries the server message, and falls back when there is none', () => {
    expect(classifyTaskFailure(409, { error: 'wrong state' }).message).toBe('wrong state')
    expect(classifyTaskFailure(409, null).message).toBe('the task is in the wrong state')
    expect(classifyTaskFailure(500, 'boom').kind).toBe('invalid')
  })
})

describe('createTasksClient — verbs, paths, and the token', () => {
  it('fires one queued card with POST …/advance', async () => {
    const { fetch, calls } = recorder(() => json(200, { task: { id: 't1' } }))
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.advance('t1')

    expect(result.ok).toBe(true)
    expect(calls).toHaveLength(1)
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toBe(`${BASE}/api/tasks/t1/advance`)
    expect(calls[0].body).toBeNull()
    expect(calls[0].token).toBe('tok')
  })

  it('creates a task with POST /api/tasks and the full payload', async () => {
    const { fetch, calls } = recorder(() => json(201, { task: { id: 't9' } }))
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.create({
      project: 'app',
      brief: 'do it',
      adapter: 'codex',
      timeout: 600,
      start: false
    })

    expect(result.ok).toBe(true)
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toBe(`${BASE}/api/tasks`)
    expect(calls[0].body).toEqual({
      project: 'app',
      brief: 'do it',
      adapter: 'codex',
      timeout: 600,
      start: false
    })
    expect(calls[0].token).toBe('tok')
  })

  it('cancels with POST …/cancel', async () => {
    const { fetch, calls } = recorder(() => json(200, { task: { id: 't1' } }))
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    await client.cancel('t1')
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toBe(`${BASE}/api/tasks/t1/cancel`)
  })

  it('removes with DELETE …', async () => {
    const { fetch, calls } = recorder(() => json(200, { removed: 't1' }))
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.remove('t1')
    expect(result).toEqual({ ok: true, value: { removed: 't1' } })
    expect(calls[0].method).toBe('DELETE')
    expect(calls[0].url).toBe(`${BASE}/api/tasks/t1`)
  })

  it('patches only queue_seq with PATCH …', async () => {
    const { fetch, calls } = recorder(() => json(200, { task: { id: 't1' } }))
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    await client.patchQueueSeq('t1', 4)
    expect(calls[0].method).toBe('PATCH')
    expect(calls[0].url).toBe(`${BASE}/api/tasks/t1`)
    expect(calls[0].body).toEqual({ queue_seq: 4 })
    expect(calls[0].token).toBe('tok')
  })

  it('URL-encodes the id so an odd id cannot escape the path', async () => {
    const { fetch, calls } = recorder(() => json(200, { task: { id: 'a/b' } }))
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    await client.advance('a/b')
    expect(calls[0].url).toBe(`${BASE}/api/tasks/a%2Fb/advance`)
  })

  it('folds a failed response into the typed result (429 example)', async () => {
    const { fetch } = recorder(() =>
      json(429, { error: 'concurrency refused', reason: 'cap', detail: 'full' })
    )
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.advance('t1')
    expect(result.ok).toBe(false)
    const error = (result as { ok: false; error: TaskWriteError }).error
    expect(error.kind).toBe('concurrency')
    expect(error.reason).toBe('cap')
    expect(error.detail).toBe('full')
  })

  it('turns a dropped transport into a network failure', async () => {
    const fetch = (async () => {
      throw new Error('ECONNREFUSED')
    }) as unknown as typeof fetch
    const client = createTasksClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.advance('t1')
    expect(result.ok).toBe(false)
    expect((result as { ok: false; error: TaskWriteError }).error.kind).toBe('network')
  })
})
