/**
 * The dispatch form's reasoning, pinned without a DOM.
 *
 * Three rules the real endpoints taught:
 *  - "run again" is a *prefill*, so all four fields must come from the original
 *    task -- and the timeout, which is not a row column, must be recovered from
 *    the task's event stream rather than replaced by the default,
 *  - the consequence summary must carry the project's *real path* (never the
 *    id) and its effective protected paths, with an empty list kept as an empty
 *    list so the view can say "none" without guessing,
 *  - the form is exactly four fields.
 */
import { describe, expect, it } from 'vitest'
import {
  ADAPTERS,
  DEFAULT_TIMEOUT,
  consequenceSummary,
  draftFromTask,
  draftValid,
  emptyDraft,
  timeoutFromEvents
} from './compose'
import type { Project, Task, TaskEvent } from './api/client'

function task(overrides: Partial<Task>): Task {
  return { project: 'app', brief: 'do the thing', adapter: 'claude', ...overrides } as Task
}

function event(payload: Record<string, unknown> | null): TaskEvent {
  return { id: 1, task_id: 't1', ts: '2026-01-01T00:00:00Z', event: 'queued', payload }
}

const PROJECT: Project = {
  id: 'app',
  path: '/srv/real/app',
  group: 'default',
  aliases: [],
  verify: null,
  verify_kind: 'build',
  forbidden_paths: ['/etc', '~/.ssh'],
  result_schema: 'default',
  auto_registered: false,
  probe: 'passed',
  probe_exit: 0,
  tasks: 0,
  in_progress: 0,
  failed: 0,
  last_activity: null
}

describe('emptyDraft — the fixed four-field vocabulary', () => {
  it('seeds the first adapter, a default timeout, and the given project', () => {
    const draft = emptyDraft('app')
    expect(draft).toEqual({
      project: 'app',
      brief: '',
      adapter: ADAPTERS[0],
      timeout: DEFAULT_TIMEOUT
    })
  })

  it('offers exactly the four adapters, codex first', () => {
    expect([...ADAPTERS]).toEqual(['codex', 'claude', 'gemini', 'opencode'])
  })
})

describe('consequenceSummary — assemble what the confirmation shows', () => {
  it('uses the project real path, not the id, and its protected paths', () => {
    const summary = consequenceSummary(
      { project: 'app', brief: 'x', adapter: 'gemini', timeout: 900 },
      PROJECT
    )
    expect(summary).toEqual({
      project: 'app',
      path: '/srv/real/app',
      adapter: 'gemini',
      timeout: 900,
      forbiddenPaths: ['/etc', '~/.ssh']
    })
  })

  it('keeps an empty protected-path list as empty (the view says "none")', () => {
    const summary = consequenceSummary(
      { project: 'app', brief: 'x', adapter: 'codex', timeout: 60 },
      { ...PROJECT, forbidden_paths: [] }
    )
    expect(summary.forbiddenPaths).toEqual([])
  })

  it('degrades to a blank path when the project record is gone', () => {
    const summary = consequenceSummary(
      { project: 'ghost', brief: 'x', adapter: 'codex', timeout: 60 },
      undefined
    )
    expect(summary.path).toBe('')
    expect(summary.forbiddenPaths).toEqual([])
  })
})

describe('draftFromTask — the run-again prefill', () => {
  it('copies all four original fields, recovering the timeout from events', () => {
    const draft = draftFromTask(
      task({ project: 'web', brief: 'fix the build', adapter: 'opencode' }),
      [event({ timeout: 42 })]
    )
    expect(draft).toEqual({
      project: 'web',
      brief: 'fix the build',
      adapter: 'opencode',
      timeout: 42
    })
  })

  it('takes the latest timeout an event carried', () => {
    const draft = draftFromTask(task({}), [
      event({ timeout: 30 }),
      { ...event({ timeout: 600 }), id: 2 }
    ])
    expect(draft.timeout).toBe(600)
  })

  it('falls back to the default when no event carries a timeout', () => {
    expect(draftFromTask(task({}), []).timeout).toBe(DEFAULT_TIMEOUT)
    expect(draftFromTask(task({}), [event({ other: 1 })]).timeout).toBe(DEFAULT_TIMEOUT)
  })

  it('defaults the adapter when the original never recorded one', () => {
    const draft = draftFromTask(task({ adapter: null }), [event({ timeout: 10 })])
    expect(draft.adapter).toBe(ADAPTERS[0])
  })

  it('never invents a source-task field (v1 keeps the ledger flat)', () => {
    const draft = draftFromTask(task({}), [event({ timeout: 10 })])
    expect(draft).not.toHaveProperty('source')
    expect(Object.keys(draft).sort()).toEqual(['adapter', 'brief', 'project', 'timeout'])
  })
})

describe('timeoutFromEvents', () => {
  it('reads only finite numeric timeouts, newest first', () => {
    expect(timeoutFromEvents([event({ timeout: 'soon' }), event({ timeout: 5 })])).toBe(5)
    expect(timeoutFromEvents([event({ timeout: Number.NaN })])).toBeNull()
    expect(timeoutFromEvents([event(null)])).toBeNull()
  })
})

describe('draftValid — the minimum to leave step one', () => {
  it('needs a project, a non-empty brief, and a positive timeout', () => {
    expect(draftValid({ project: 'app', brief: 'x', adapter: 'codex', timeout: 60 })).toBe(true)
    expect(draftValid({ project: '', brief: 'x', adapter: 'codex', timeout: 60 })).toBe(false)
    expect(draftValid({ project: 'app', brief: '   ', adapter: 'codex', timeout: 60 })).toBe(false)
    expect(draftValid({ project: 'app', brief: 'x', adapter: 'codex', timeout: 0 })).toBe(false)
  })
})
