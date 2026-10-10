/**
 * The store's own rules -- the reasoning the UI depends on but that is not tied
 * to a particular view.
 *
 * The board's project selection lives in the address bar now (the matrix's
 * multi-select), so the store no longer keeps a visibility map; what is left
 * here is the pump: switching polling off must actually stop it rather than
 * merely relabelling it, and a launch that is merely slow must not be reported
 * as offline.
 *
 * The log tail is part of the same pump: it continues from the server's `next`
 * cursor, refuses to auto-continue while polling is off, and stops the moment
 * the tab closes.
 *
 * No sockets: the local API is stubbed. For the log tests the stub answers the
 * handful of endpoints the store touches with fixture pages.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useBoardStore } from './board'
import type { ProjectGroup, TaskLog } from '../api/client'

describe('polling and start-up', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    ;(globalThis as unknown as { window: unknown }).window = { tp: undefined }
    ;(globalThis as unknown as { location: unknown }).location = { search: '' }
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('no local service in this test')))
    )
    vi.useFakeTimers()
  })

  afterEach(() => {
    useBoardStore().stop()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('turning polling off stops the pump, and on restarts it', () => {
    const store = useBoardStore()
    store.setPoll('2s')
    expect(store.polling).toBe(true)
    store.setPoll('off')
    expect(store.polling).toBe(false)
    expect(store.poll).toBe('off')
    store.setPoll('2s')
    expect(store.polling).toBe(true)
  })

  it('the blank state is not shown while the service is merely starting', () => {
    // `connected` starts false; claiming "offline" before anything has failed
    // would flash a full-page error on every launch.
    const store = useBoardStore()
    expect(store.connected).toBe(false)
    expect(store.lastError).toBeNull()
  })
})

/** A minimal Response stand-in: the client only reads `ok`, `status`, `json`. */
function json(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as unknown as Response
}

/** Drain the promise chain hung off a fire-and-forget `void readLog()` without
 *  advancing the fake clock (which would also fire the tail's interval). */
async function flushMicrotasks(times = 12): Promise<void> {
  for (let i = 0; i < times; i += 1) await Promise.resolve()
}

const PAGE_ONE: TaskLog = {
  task_id: 't1',
  offset: 0,
  next: 5,
  text: 'abcde',
  eof: false,
  size: 11,
  omitted: 7
}
const PAGE_TWO: TaskLog = {
  task_id: 't1',
  offset: 5,
  next: 11,
  text: 'fghijk',
  eof: true,
  size: 11,
  omitted: 0
}

/**
 * The D2 shape-C grouped view. The board draws one row per *project*, so the
 * store holds `GET /api/projects?by=project` and derives the lane -> project
 * map from its nested `taskgroups` -- the flat one-row-per-lane view is left
 * for the projects page and the empty-state banner.
 */
const GROUPS = [
  {
    id: 'alpha',
    path: '/w/alpha',
    aliases: ['a'],
    taskgroups: [
      { id: 'alpha-core', project: 'alpha', path: '/w/alpha/core' },
      { id: 'alpha-web', project: 'alpha', path: '/w/alpha/web' }
    ],
    summary: {
      running: 1,
      verifying: 0,
      done: 3,
      failed: 1,
      blocked: 0,
      timeout: 0,
      cancelled: 0
    }
  },
  {
    id: 'beta',
    path: '/w/beta',
    aliases: [],
    taskgroups: [{ id: 'beta', project: 'beta', path: '/w/beta' }],
    summary: {
      running: 0,
      verifying: 0,
      done: 0,
      failed: 0,
      blocked: 0,
      timeout: 0,
      cancelled: 0
    }
  }
] as unknown as ProjectGroup[]

describe('the grouped view (one row per project)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    ;(globalThis as unknown as { window: unknown }).window = { tp: undefined }
    ;(globalThis as unknown as { location: unknown }).location = { search: '' }
    vi.stubGlobal(
      'fetch',
      vi.fn((input: unknown) => {
        const url = String(input)
        // Match the grouped view before the flat one: both contain `/api/projects`.
        if (url.includes('/api/projects?by=project')) {
          return Promise.resolve(json({ projects: GROUPS }))
        }
        if (url.endsWith('/api/health')) return Promise.resolve(json({ ok: true, version: 'test' }))
        if (url.includes('/api/summary')) return Promise.resolve(json({ summary: {} }))
        if (url.includes('/api/projects')) return Promise.resolve(json({ projects: [] }))
        if (url.includes('/api/tasks')) return Promise.resolve(json({ tasks: [] }))
        return Promise.reject(new Error(`unexpected request: ${url}`))
      })
    )
  })

  afterEach(() => {
    useBoardStore().dispose()
    vi.unstubAllGlobals()
  })

  it('holds the grouped view and reads the lane -> project map off its lanes', async () => {
    const store = useBoardStore()
    await store.refresh()

    expect(store.projectGroups.map((group) => group.id)).toEqual(['alpha', 'beta'])
    // One project + its nested taskgroups + summary, held as fetched.
    expect(store.projectGroups[0].taskgroups.map((lane) => lane.id)).toEqual([
      'alpha-core',
      'alpha-web'
    ])
    expect(store.projectGroups[0].summary).toMatchObject({ running: 1, done: 3, failed: 1 })
    // The map comes from `taskgroups[].project`, not a second request.
    expect(store.laneProject).toEqual({
      'alpha-core': 'alpha',
      'alpha-web': 'alpha',
      beta: 'beta'
    })
    // The flat view is still fetched (the projects page reads it) but is not
    // the board's row source.
    expect(store.projects).toEqual([])
  })
})

describe('the log tail', () => {
  let logCalls: string[]

  beforeEach(() => {
    setActivePinia(createPinia())
    ;(globalThis as unknown as { window: unknown }).window = { tp: undefined }
    ;(globalThis as unknown as { location: unknown }).location = { search: '' }
    logCalls = []
    vi.stubGlobal(
      'fetch',
      vi.fn((input: unknown) => {
        const url = String(input)
        // The log URL also contains `/api/tasks`, so it has to be matched first.
        if (url.includes('/log')) {
          logCalls.push(url)
          return Promise.resolve(json(url.includes('offset=') ? PAGE_TWO : PAGE_ONE))
        }
        if (url.endsWith('/api/health')) return Promise.resolve(json({ ok: true, version: 'test' }))
        if (url.includes('/api/summary')) return Promise.resolve(json({ summary: {} }))
        if (url.includes('/api/projects')) return Promise.resolve(json({ projects: [] }))
        if (url.includes('/api/tasks')) return Promise.resolve(json({ tasks: [] }))
        return Promise.reject(new Error(`unexpected request: ${url}`))
      })
    )
    vi.useFakeTimers()
  })

  afterEach(() => {
    useBoardStore().dispose()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('continues from `next` and appends the next page onto the tail', async () => {
    const store = useBoardStore()
    store.startLog('t1')
    await flushMicrotasks()

    // The first read carries no cursor; its `omitted` and `next` are recorded.
    expect(store.logText).toBe('abcde')
    expect(store.logNext).toBe(5)
    expect(store.logOmitted).toBe(7)

    // One tick, one continuation: the second page is requested from `next`
    // and its text is appended, not replaced.
    await vi.advanceTimersByTimeAsync(1000)
    await flushMicrotasks()

    expect(store.logText).toBe('abcdefghijk')
    expect(store.logNext).toBe(11)
    expect(store.logEof).toBe(true)
    expect(logCalls.some((url) => url.endsWith('/api/tasks/t1/log?offset=5'))).toBe(true)
  })

  it('does not auto-continue while the global pump is off', async () => {
    const store = useBoardStore()
    store.setPoll('off')
    await flushMicrotasks()

    store.startLog('t1')
    await flushMicrotasks()
    expect(store.logText).toBe('abcde')

    // The first page still loaded, but with polling off nothing keeps reading:
    // only the manual refresh button may pull more.
    logCalls = []
    await vi.advanceTimersByTimeAsync(5000)
    await flushMicrotasks()
    expect(logCalls).toEqual([])
    expect(store.logNext).toBe(5)
  })

  it('stops the tail when the tab closes or switches away', async () => {
    const store = useBoardStore()
    store.startLog('t1')
    await flushMicrotasks()

    logCalls = []
    store.stopLog()
    await vi.advanceTimersByTimeAsync(5000)
    await flushMicrotasks()

    expect(logCalls).toEqual([])
    // The loaded text survives the close, so returning resumes where it left.
    expect(store.logText).toBe('abcde')
  })
})
