/**
 * The console write store, pinned branch by branch.
 *
 * The rules the endpoints taught, and that a DOM-less test can still hold:
 *  - a refused spawn (429) is a *notice*, never an error: the card was not
 *    admitted, so the store must not set `error` and must return false,
 *  - delete is terminal-only: opening the confirm for a live card is a no-op
 *    and confirming it sends no request at all,
 *  - the copy is read through the real i18n bundle, so a missing key fails here.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { i18n } from '../i18n'
import { useBoardStore } from './board'
import { isAcceptable, isDeletable, useTasksStore } from './tasks'
import type { Project, Task } from '../api/client'
import type { TaskResult, TaskWriteError } from '../../../preload/types'

function copy(key: string, detail = ''): string {
  return String(i18n.global.t(key, { detail }))
}

function ok<T>(value: T): TaskResult<T> {
  return { ok: true, value }
}

function fail<T = never>(error: TaskWriteError): TaskResult<T> {
  return { ok: false, error }
}

/** Only the methods a test exercises need to exist. */
function install(tasks: Record<string, unknown>, projects: Project[] = []): void {
  ;(globalThis as unknown as { window: unknown }).window = { tp: { tasks } }
  useBoardStore().projects = projects
}

function task(overrides: Partial<Task> = {}): Task {
  return { id: 't1', project: 'app', status: 'running', ...overrides } as Task
}

const PROJECT: Project = {
  id: 'app',
  path: '/srv/real/app',
  group: 'default',
  aliases: [],
  verify: null,
  verify_kind: 'build',
  forbidden_paths: ['/etc'],
  result_schema: 'default',
  auto_registered: false,
  probe: 'passed',
  probe_exit: 0,
  tasks: 0,
  in_progress: 0,
  failed: 0,
  last_activity: null
}

describe('tasks store — the dispatch form', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('seeds the blank form from the first registered project', () => {
    install({}, [PROJECT])
    const store = useTasksStore()
    store.openCompose()
    expect(store.composeOpen).toBe(true)
    expect(store.draft.project).toBe('app')
    expect(store.rerunOf).toBeNull()
  })

  it('dispatching now sends start:true and the four fields', async () => {
    const create = vi.fn(async (_payload: unknown) => ok({ task: { id: 't2' } }))
    install({ create }, [PROJECT])

    const store = useTasksStore()
    store.openCompose()
    store.setDraft({ project: 'app', brief: 'ship it', adapter: 'gemini', timeout: 900 })

    expect(await store.submit(true)).toBe(true)
    expect(create).toHaveBeenCalledTimes(1)
    expect(create.mock.calls[0][0]).toEqual({
      project: 'app',
      brief: 'ship it',
      adapter: 'gemini',
      timeout: 900,
      start: true
    })
    expect(store.composeOpen).toBe(false)
    expect(store.error).toBeNull()
  })

  it('save-for-later sends start:false', async () => {
    const create = vi.fn(async (_payload: unknown) => ok({ task: { id: 't3' } }))
    install({ create }, [PROJECT])

    const store = useTasksStore()
    store.openCompose()
    store.setDraft({ project: 'app', brief: 'later', adapter: 'codex', timeout: 60 })

    expect(await store.submit(false)).toBe(true)
    expect(create.mock.calls[0][0]).toMatchObject({ start: false })
  })

  it('blocks step one until the minimum fields are filled', () => {
    install({}, [PROJECT])
    const store = useTasksStore()
    store.openCompose()
    // Empty brief -> cannot proceed.
    expect(store.toSummary()).toBe(false)
    expect(store.summaryOpen).toBe(false)
    store.setDraft({ brief: 'go' })
    expect(store.toSummary()).toBe(true)
    expect(store.summaryOpen).toBe(true)
  })

  it('maps a 409 to the state copy and keeps the sheet open', async () => {
    const create = vi.fn(async (_payload: unknown) =>
      fail({ kind: 'state', status: 409, message: 'the task is in the wrong state' })
    )
    install({ create }, [PROJECT])

    const store = useTasksStore()
    store.openCompose()
    store.setDraft({ brief: 'go' })

    expect(await store.submit(true)).toBe(false)
    expect(store.error).toBe(copy('task.error.state', 'the task is in the wrong state'))
    expect(store.composeOpen).toBe(true)
  })

  it('maps a dropped transport to the network copy', async () => {
    const create = vi.fn(async (_payload: unknown) =>
      fail({ kind: 'network', status: 0, message: 'ECONNREFUSED' })
    )
    install({ create }, [PROJECT])

    const store = useTasksStore()
    store.openCompose()
    store.setDraft({ brief: 'go' })

    expect(await store.submit(false)).toBe(false)
    expect(store.error).toBe(copy('task.error.network', 'ECONNREFUSED'))
  })
})

describe('tasks store — stop', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('confirms the stop through a dialog before calling cancel', async () => {
    const cancel = vi.fn(async (_id: string) => ok({ task: { id: 't1' } }))
    install({ cancel })

    const store = useTasksStore()
    const live = task({ status: 'running' })
    store.openStop(live)
    expect(store.stopOpen).toBe(true)
    expect(cancel).not.toHaveBeenCalled()

    expect(await store.confirmStop()).toBe(true)
    expect(cancel).toHaveBeenCalledWith('t1')
    expect(store.stopOpen).toBe(false)
  })
})

describe('tasks store — accept (release a blocked card)', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('refuses to open the accept confirm for a card that is not blocked', () => {
    const accept = vi.fn(async (_id: string) => ok({ task: { id: 't1' } }))
    install({ accept })

    const store = useTasksStore()
    for (const status of ['running', 'verifying', 'done', 'failed', 'timeout', 'cancelled']) {
      store.openAccept(task({ status }))
      expect(store.acceptOpen).toBe(false)
    }
    expect(store.target).toBeNull()
    expect(accept).not.toHaveBeenCalled()
  })

  it('confirms the accept through a dialog before calling the API', async () => {
    const accept = vi.fn(async (_id: string) => ok({ task: { id: 't1', status: 'done' } }))
    install({ accept })

    const store = useTasksStore()
    store.openAccept(task({ status: 'blocked', verify_exit: 0 }))
    expect(store.acceptOpen).toBe(true)
    expect(accept).not.toHaveBeenCalled()

    expect(await store.confirmAccept()).toBe(true)
    expect(accept).toHaveBeenCalledWith('t1')
    expect(store.acceptOpen).toBe(false)
    expect(store.error).toBeNull()
    expect(store.notice).toBeNull()
  })

  it('treats a 409 (no longer blocked) as a notice + refresh, not an error', async () => {
    // The card was released elsewhere; instead of a scary error we say so and
    // return true so the caller refreshes -- no stale, still-clickable card.
    const accept = vi.fn(async (_id: string) =>
      fail({ kind: 'state', status: 409, message: 'task is not blocked' })
    )
    install({ accept })

    const store = useTasksStore()
    store.openAccept(task({ status: 'blocked' }))
    const result = await store.confirmAccept()

    expect(result).toBe(true)
    expect(store.acceptOpen).toBe(false)
    expect(store.error).toBeNull()
    expect(store.notice).toBe(copy('task.notice.stale'))
  })

  it('surfaces a 404 / forbidden / network as a hard error, not silence', async () => {
    for (const error of [
      { kind: 'notfound', status: 404, message: 'no such task' },
      { kind: 'forbidden', status: 403, message: 'bad token' },
      { kind: 'network', status: 0, message: 'ECONNREFUSED' }
    ] as const) {
      setActivePinia(createPinia())
      const accept = vi.fn(async (_id: string) => fail({ ...error }))
      install({ accept })

      const store = useTasksStore()
      store.openAccept(task({ status: 'blocked' }))
      const result = await store.confirmAccept()

      expect(result).toBe(false)
      expect(store.acceptOpen).toBe(true)
      expect(store.error).toBe(copy(`task.error.${error.kind}`, error.message))
    }
  })

  it('agrees with the exported blocked-only gate', () => {
    expect(isAcceptable({ status: 'blocked' })).toBe(true)
    expect(isAcceptable({ status: 'done' })).toBe(false)
  })
})

describe('tasks store — delete is terminal-only', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('refuses to open the confirm for a live card and sends nothing', async () => {
    const remove = vi.fn(async (_id: string) => ok({ removed: 't1' }))
    install({ remove })

    const store = useTasksStore()
    for (const status of ['running', 'verifying']) {
      store.openDelete(task({ status }))
      expect(store.deleteOpen).toBe(false)
    }
    expect(await store.confirmDelete()).toBe(false)
    expect(remove).not.toHaveBeenCalled()
  })

  it('deletes a terminal card after the confirm', async () => {
    const remove = vi.fn(async (_id: string) => ok({ removed: 't1' }))
    install({ remove })

    const store = useTasksStore()
    store.openDelete(task({ status: 'done' }))
    expect(store.deleteOpen).toBe(true)
    expect(await store.confirmDelete()).toBe(true)
    expect(remove).toHaveBeenCalledWith('t1')
    expect(store.deleteOpen).toBe(false)
  })

  it('agrees with the exported terminal gate', () => {
    expect(isDeletable({ status: 'cancelled' })).toBe(true)
    expect(isDeletable({ status: 'running' })).toBe(false)
  })
})
