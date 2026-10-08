/**
 * The projects write store: what each failure leaves on screen.
 *
 * The copy is checked through the real i18n bundle, so a missing key would
 * fail the test rather than render the raw key. The important behavioural
 * rule is the conflict one: a 409 parks the store in the conflict state and
 * sends nothing further until the user chooses.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { i18n } from '../i18n'
import { useProjectsStore } from './projects'
import type { Project } from '../api/client'
import type { RegistryResult, WriteError } from '../../../preload/types'

function copy(key: string, detail = ''): string {
  return String(i18n.global.t(key, { detail }))
}

function ok<T>(value: T): RegistryResult<T> {
  return { ok: true, value }
}

function fail(error: WriteError): RegistryResult<never> {
  return { ok: false, error }
}

/** Only the methods a test exercises need to exist; the store reaches for the
 *  named ones at call time. */
function install(projects: Record<string, unknown>): void {
  ;(globalThis as unknown as { window: unknown }).window = { tp: { projects } }
}

const PROJECT: Project = {
  id: 'app',
  path: '/repo/app',
  group: 'default',
  aliases: ['web'],
  verify: 'npm run build',
  verify_kind: 'build',
  forbidden_paths: ['.git/'],
  result_schema: 'default',
  auto_registered: false,
  probe: 'passed',
  probe_exit: 0,
  tasks: 3,
  in_progress: 0,
  failed: 0,
  last_activity: null
}

const PROBE_RECORD = {
  id: 'app',
  path: '/repo/app',
  group: 'app',
  verify: 'npm run build',
  verify_kind: 'build',
  probe: 'passed' as const,
  probe_exit: 0,
  aliases: [],
  forbidden_paths: ['.git/']
}

function conflictError(): WriteError {
  return {
    kind: 'conflict',
    status: 409,
    message: 'the registry changed on disk since it was read',
    conflict: { hash: 'new', content: '[project]', projects: [] }
  }
}

describe('projects store — write branches', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('registers a probed draft and closes the sheet', async () => {
    const create = vi.fn(async (_payload: unknown) => ok({ project: { id: 'app' } }))
    install({ create, probe: async () => ok(PROBE_RECORD) })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/repo/app'
    await store.detect()

    expect(await store.register()).toBe(true)
    expect(create).toHaveBeenCalledTimes(1)
    expect(create.mock.calls[0][0]).toMatchObject({
      path: '/repo/app',
      id: 'app',
      group: 'app',
      verify: 'npm run build',
      verify_kind: 'build',
      forbidden_paths: ['.git/'],
      probe: 'passed'
    })
    expect(store.addOpen).toBe(false)
    expect(store.error).toBeNull()
  })

  it('surfaces a 409 as conflict and sends no further write', async () => {
    const create = vi.fn(async (_payload: unknown) => fail(conflictError()))
    install({ create, probe: async () => ok(PROBE_RECORD) })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/repo/app'
    await store.detect()

    expect(await store.register()).toBe(false)
    expect(store.conflict?.hash).toBe('new')
    expect(store.error).toBe(copy('proj.error.conflict'))
    // The rule: a conflict is never retried on its own.
    expect(create).toHaveBeenCalledTimes(1)
  })

  it('replays the interrupted write when the user keeps their edits', async () => {
    const create = vi
      .fn()
      .mockResolvedValueOnce(fail(conflictError()))
      .mockResolvedValueOnce(ok({ project: { id: 'app' } }))
    install({ create, probe: async () => ok(PROBE_RECORD) })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/repo/app'
    await store.detect()
    await store.register()

    expect(create).toHaveBeenCalledTimes(1)
    // Only now, on the user's say-so, does a second write go out.
    expect(await store.keepEdits()).toBe(true)
    expect(create).toHaveBeenCalledTimes(2)
    expect(store.conflict).toBeNull()
  })

  it('clears the conflict without writing when the user reloads', async () => {
    const create = vi.fn(async (_payload: unknown) => fail(conflictError()))
    install({ create, probe: async () => ok(PROBE_RECORD) })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/repo/app'
    await store.detect()
    await store.register()

    store.reloadFile()
    expect(store.conflict).toBeNull()
    expect(create).toHaveBeenCalledTimes(1)
  })

  it('maps a 400 to the invalid copy', async () => {
    const create = vi.fn(async (_payload: unknown) =>
      fail({ kind: 'invalid', status: 400, message: 'path does not exist' })
    )
    install({ create, probe: async () => ok(PROBE_RECORD) })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/repo/app'
    await store.detect()
    await store.register()

    expect(store.error).toBe(copy('proj.error.invalid', 'path does not exist'))
    expect(store.conflict).toBeNull()
  })

  it('maps a transport error to the network copy', async () => {
    const create = vi.fn(async (_payload: unknown) =>
      fail({ kind: 'network', status: 0, message: 'ECONNREFUSED' })
    )
    install({ create, probe: async () => ok(PROBE_RECORD) })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/repo/app'
    await store.detect()
    await store.register()

    expect(store.error).toBe(copy('proj.error.network', 'ECONNREFUSED'))
  })

  it('patches without ever sending id or path', async () => {
    const patch = vi.fn(async (_id: string, _body: Record<string, unknown>) =>
      ok({ project: { id: 'app' } })
    )
    install({ patch })

    const store = useProjectsStore()
    store.openEdit(PROJECT)
    store.draft.group = 'web'
    store.draft.aliases = 'app, frontend'

    expect(await store.save()).toBe(true)
    expect(patch).toHaveBeenCalledTimes(1)
    const [id, body] = patch.mock.calls[0]
    expect(id).toBe('app')
    expect(body).toMatchObject({
      group: 'web',
      aliases: ['app', 'frontend'],
      forbidden_paths: ['.git/'],
      result_schema: 'default'
    })
    expect(body).not.toHaveProperty('id')
    expect(body).not.toHaveProperty('path')
  })
})

describe('projects store — probe', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fills the draft from a successful probe', async () => {
    install({ probe: async () => ok(PROBE_RECORD) })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/repo/app'

    expect(await store.detect()).toBe(true)
    expect(store.draft.detected).toBe(true)
    expect(store.draft.id).toBe('app')
    expect(store.draft.verify).toBe('npm run build')
    expect(store.draft.verify_kind).toBe('build')
    expect(store.draft.forbidden).toBe('.git/')
    expect(store.draft.probe).toBe('passed')
    expect(store.error).toBeNull()
  })

  it('gives a readable error when the probe fails', async () => {
    install({
      probe: async () =>
        fail({ kind: 'invalid', status: 400, message: 'path does not exist: /nope' })
    })

    const store = useProjectsStore()
    store.openAdd()
    store.draft.path = '/nope'

    expect(await store.detect()).toBe(false)
    expect(store.draft.detected).toBe(false)
    expect(store.error).toBe(copy('proj.error.invalid', 'path does not exist: /nope'))
  })
})
