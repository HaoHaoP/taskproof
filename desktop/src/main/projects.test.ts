/**
 * The registry write client, pinned branch by branch.
 *
 * These are the rules the desktop depends on and that a real 409 taught:
 * the optimistic-write handshake reads the hash first and carries it as
 * `expected_hash`, a conflict is handed back untouched (never retried), and
 * every transport failure becomes the same typed shape the renderer switches
 * on. The token lives on the mutations only.
 */
import { describe, expect, it, vi } from 'vitest'
import { classifyFailure, createProjectsClient } from './projects'

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

/** A recording fetch stub; `handlers` decide each response by url suffix. */
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

describe('createProjectsClient — hash handshake', () => {
  it('reads the registry hash and folds it into create', async () => {
    const { fetch, calls } = recorder((url) =>
      url.endsWith('/api/registry')
        ? json(200, { path: '/ws/projects.toml', hash: 'h-1', mtime: 1 })
        : json(201, { project: { id: 'app' } })
    )
    const client = createProjectsClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.create({ path: '/repo/app' })

    expect(result.ok).toBe(true)
    expect(calls.map((call) => [call.method, call.url])).toEqual([
      ['GET', `${BASE}/api/registry`],
      ['POST', `${BASE}/api/projects`]
    ])
    // The hash came from the read, not from the caller.
    expect(calls[1].body?.expected_hash).toBe('h-1')
    expect(calls[1].body?.path).toBe('/repo/app')
    // The token is on the mutation, never on the read.
    expect(calls[1].token).toBe('tok')
    expect(calls[0].token).toBeUndefined()
  })

  it('carries the hash into patch and remove too', async () => {
    const handler = (url: string): Response =>
      url.endsWith('/api/registry')
        ? json(200, { hash: 'h-9' })
        : url.endsWith('/api/projects/app')
          ? json(200, { project: { id: 'app' }, removed: 'app' })
          : json(404, { error: 'nope' })
    const { fetch, calls } = recorder(handler)
    const client = createProjectsClient({ baseUrl: BASE, token: 'tok', fetch })

    await client.patch('app', { group: 'g' })
    await client.remove('app')

    const mutations = calls.filter((call) => call.method !== 'GET')
    expect(mutations.map((call) => call.body?.expected_hash)).toEqual(['h-9', 'h-9'])
    expect(mutations.map((call) => call.method)).toEqual(['PATCH', 'DELETE'])
  })

  it('does not send the mutation when the registry read fails', async () => {
    const { fetch, calls } = recorder(() => json(404, { error: 'no registry' }))
    const client = createProjectsClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.create({ path: '/repo/app' })

    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('notfound')
    // Only the failed read; nothing was written.
    expect(calls).toHaveLength(1)
  })
})

describe('createProjectsClient — failure shapes', () => {
  it('surfaces a 409 as a conflict and never retries', async () => {
    const { fetch, calls } = recorder((url) =>
      url.endsWith('/api/registry')
        ? json(200, { hash: 'old' })
        : json(409, {
            error: 'conflict',
            hash: 'new',
            content: '[project]\nid = "x"\n',
            projects: [{ id: 'x' }]
          })
    )
    const client = createProjectsClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.patch('app', { group: 'g' })

    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error.kind).toBe('conflict')
      expect(result.error.status).toBe(409)
      expect(result.error.conflict?.hash).toBe('new')
      expect(result.error.conflict?.content).toContain('id = "x"')
    }
    // Exactly the read and the one mutation -- no automatic second attempt.
    expect(calls).toHaveLength(2)
  })

  it('maps 400 to invalid with the server message', async () => {
    const { fetch } = recorder((url) =>
      url.endsWith('/api/registry') ? json(200, { hash: 'h' }) : json(400, { error: 'path is required' })
    )
    const client = createProjectsClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.create({ path: '' })

    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error.kind).toBe('invalid')
      expect(result.error.message).toBe('path is required')
    }
  })

  it('maps 403 and 404 to their own kinds', () => {
    expect(classifyFailure(403, { error: 'forbidden' }).kind).toBe('forbidden')
    expect(classifyFailure(404, { error: 'no such project' }).kind).toBe('notfound')
  })

  it('folds a transport error into a network failure', async () => {
    const fetch = vi.fn(async () => {
      throw new Error('ECONNREFUSED')
    }) as unknown as typeof fetch
    const client = createProjectsClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.registry()

    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error.kind).toBe('network')
      expect(result.error.status).toBe(0)
      expect(result.error.message).toContain('ECONNREFUSED')
    }
  })
})

describe('createProjectsClient — probe', () => {
  it('posts the path with the token and no hash read', async () => {
    const { fetch, calls } = recorder(() =>
      json(200, {
        id: 'app',
        path: '/repo/app',
        group: 'app',
        verify: 'npm run build',
        verify_kind: 'build',
        probe: 'passed',
        probe_exit: 0,
        aliases: [],
        forbidden_paths: []
      })
    )
    const client = createProjectsClient({ baseUrl: BASE, token: 'tok', fetch })

    const result = await client.probe('/repo/app')

    expect(result.ok).toBe(true)
    if (result.ok) expect(result.value.probe).toBe('passed')
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe(`${BASE}/api/projects/probe`)
    expect(calls[0].method).toBe('POST')
    expect(calls[0].body).toEqual({ path: '/repo/app' })
    expect(calls[0].token).toBe('tok')
  })
})
