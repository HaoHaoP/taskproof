/**
 * The projects page draws one row per project with a nested row per lane. The
 * join between the grouped roster and the flat per-lane detail is the whole
 * point of `projects.ts`, so these tests pin it without a DOM: row counts,
 * child counts, the newest-activity and probe sums, and the two compatibility
 * shapes the registry still produces (a single uncollected lane, and a lane the
 * roster names that has no detail record).
 */
import { describe, expect, it } from 'vitest'
import type { Project, ProjectGroup, ProjectTaskgroup } from './api/client'
import { projectRows } from './projects'

/** A flat per-lane record, with defaults for every field the model ignores. */
function lane(over: Partial<Project> & { id: string }): Project {
  return {
    path: `/w/${over.id}`,
    group: over.id,
    aliases: [],
    verify: null,
    verify_kind: 'none',
    forbidden_paths: [],
    result_schema: 'default',
    auto_registered: false,
    probe: 'none',
    probe_exit: null,
    tasks: 0,
    in_progress: 0,
    failed: 0,
    last_activity: null,
    ...over
  } as Project
}

/** A lane as nested in the grouped view (config only, no task stats). */
function taskgroup(
  id: string,
  project: string,
  over: Partial<ProjectTaskgroup> = {}
): ProjectTaskgroup {
  return {
    id,
    project,
    path: `/w/${id}`,
    group: id,
    aliases: [],
    verify: null,
    verify_kind: 'none',
    forbidden_paths: [],
    result_schema: 'default',
    auto_registered: false,
    probe: 'none',
    probe_exit: null,
    ...over
  } as ProjectTaskgroup
}

function group(id: string, over: Partial<ProjectGroup> = {}): ProjectGroup {
  return { id, path: `/w/${id}`, aliases: [], taskgroups: [], summary: {}, ...over } as ProjectGroup
}

describe('projectRows', () => {
  it('renders one project row with a child per lane (multiple lanes)', () => {
    const groups = [
      group('alpha', {
        taskgroups: [taskgroup('alpha-core', 'alpha'), taskgroup('alpha-web', 'alpha')],
        summary: { running: 1, verifying: 0, done: 2, failed: 1, blocked: 0, timeout: 0, cancelled: 0 }
      })
    ]
    const details = [
      lane({ id: 'alpha-core', tasks: 2, failed: 0, last_activity: '2026-10-01T00:00:00Z' }),
      lane({ id: 'alpha-web', tasks: 2, failed: 1, last_activity: '2026-10-03T00:00:00Z' })
    ]

    const rows = projectRows(groups, details)

    expect(rows).toHaveLength(1)
    expect(rows[0].lanes).toHaveLength(2)
    expect(rows[0].lanes.map((l) => l.id)).toEqual(['alpha-core', 'alpha-web'])
    // Counts come from the grouped summary: 1 + 0 + 2 + 1.
    expect(rows[0].tasks).toBe(4)
    expect(rows[0].inProgress).toBe(1)
    expect(rows[0].failed).toBe(1)
  })

  it('still renders the single uncollected lane, id == project (compat shape)', () => {
    const groups = [
      group('solo', {
        // The old one-block-per-project shape: the lane doubles as the project
        // and names no lock of its own.
        taskgroups: [taskgroup('solo', 'solo', { group: '' })],
        summary: { done: 1 }
      })
    ]
    const details = [lane({ id: 'solo', tasks: 1, last_activity: '2026-10-02T00:00:00Z' })]

    const rows = projectRows(groups, details)

    expect(rows).toHaveLength(1)
    expect(rows[0].lanes).toHaveLength(1)
    expect(rows[0].lanes[0].id).toBe('solo')
  })

  it('shows a missing concurrency lock as the lane itself, never blank', () => {
    const groups = [
      group('solo', {
        taskgroups: [taskgroup('solo', 'solo', { group: '' })],
        summary: {}
      })
    ]

    const rows = projectRows(groups, [])

    expect(rows[0].lanes[0].group).toBe('solo')
  })

  it('keeps a lane the roster names even when its detail record is gone (orphan)', () => {
    const groups = [
      group('gamma', {
        taskgroups: [taskgroup('gamma-core', 'gamma'), taskgroup('gamma-ghost', 'gamma')],
        summary: { done: 1 }
      })
    ]
    // `gamma-ghost` has no detail row: an old task left the id behind.
    const details = [lane({ id: 'gamma-core', tasks: 1 })]

    const rows = projectRows(groups, details)

    expect(rows).toHaveLength(1)
    expect(rows[0].lanes).toHaveLength(2)
    const ghost = rows[0].lanes.find((l) => l.id === 'gamma-ghost')
    expect(ghost).toBeTruthy()
    // It falls back to the roster's own config, with no invented counts.
    expect(ghost?.path).toBe('/w/gamma-ghost')
    expect(ghost?.group).toBe('gamma-ghost')
    expect(ghost?.tasks).toBe(0)
    expect(ghost?.lastActivity).toBeNull()
  })

  it("takes the project's newest activity from its latest lane", () => {
    const groups = [
      group('alpha', {
        taskgroups: [taskgroup('a1', 'alpha'), taskgroup('a2', 'alpha')],
        summary: {}
      })
    ]
    const details = [
      lane({ id: 'a1', last_activity: '2026-10-05T00:00:00Z' }),
      lane({ id: 'a2', last_activity: '2026-10-02T00:00:00Z' })
    ]

    const rows = projectRows(groups, details)

    expect(rows[0].lastActivity).toBe('2026-10-05T00:00:00Z')
  })

  it('marks the project probe failed when any lane failed, else passed when any passed', () => {
    const groups = [
      group('alpha', {
        taskgroups: [
          taskgroup('a1', 'alpha', { probe: 'passed' }),
          taskgroup('a2', 'alpha', { probe: 'failed' }),
          taskgroup('a3', 'alpha', { probe: 'none' })
        ],
        summary: {}
      }),
      group('beta', {
        taskgroups: [
          taskgroup('b1', 'beta', { probe: 'passed' }),
          taskgroup('b2', 'beta', { probe: 'none' })
        ],
        summary: {}
      })
    ]

    const rows = projectRows(groups, [])

    expect(rows[0].probe).toBe('failed')
    expect(rows[1].probe).toBe('passed')
  })
})
