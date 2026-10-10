import { describe, expect, it } from 'vitest'
import type { Project, Task } from './api/client'
import { COLUMNS, type Column } from './contract'
import {
  DEFAULT_FILTER,
  DONE_WINDOW,
  MAX_BUDGET,
  MIN_BUDGET,
  boardQuery,
  canGrowBudget,
  doneWindow,
  filterBoard,
  gridTracks,
  groupColumns,
  hiddenTally,
  inRange,
  needsMoreBudget,
  parseBoardFilter,
  sortColumn,
  visibleColumns,
  visibleProjects
} from './matrix'

/** A task with only the fields these rules read; the rest are inert. */
function task(id: string, fields: Partial<Task> = {}): Task {
  return {
    id,
    project: 'p',
    status: 'running',
    brief: '',
    adapter: null,
    model: null,
    attempt: null,
    group_name: null,
    pid: null,
    pgid: null,
    workdir: null,
    reasoning: null,
    result_path: null,
    exit_code: null,
    verify_cmd: null,
    verify_exit: null,
    files_changed: null,
    files_changed_live: null,
    created_at: null,
    started_at: null,
    finished_at: null,
    ...fields
  }
}

const NOW = Date.parse('2026-10-08T12:00:00+08:00')
const DAY = 24 * 60 * 60 * 1000

describe('finished-column window', () => {
  const done = Array.from({ length: 11 }, (_, i) =>
    task(`d${i}`, { status: 'done', created_at: new Date(NOW - i * 1000).toISOString() })
  )

  it('renders only the ten most recent by default', () => {
    const window = doneWindow(done, false)
    expect(window.visible).toHaveLength(DONE_WINDOW)
    expect(window.hidden).toBe(1)
    expect(window.total).toBe(11)
    // the folded-out card is the oldest of the eleven
    expect(window.visible.map((t) => t.id)).not.toContain('d10')
  })

  it('unfolds to every card', () => {
    const window = doneWindow(done, true)
    expect(window.visible).toHaveLength(11)
    expect(window.hidden).toBe(0)
  })

  it('shows no bar at 0 or 1 cards', () => {
    expect(doneWindow([], false).hidden).toBe(0)
    expect(doneWindow([done[0]], false).hidden).toBe(0)
  })

  it('counts the hidden remainder as total minus the window', () => {
    const many = Array.from({ length: 25 }, (_, i) =>
      task(`d${i}`, { status: 'done', created_at: new Date(NOW - i * 1000).toISOString() })
    )
    expect(doneWindow(many, false).hidden).toBe(15)
  })
})

describe('column ordering', () => {
  it('orders finished by finished_at, newest first, null falling back to created_at', () => {
    const tasks = [
      // finished long ago
      task('old', { status: 'done', created_at: '2026-01-01T00:00:00+08:00', finished_at: '2026-01-02T00:00:00+08:00' }),
      // created long ago, finished just now -- the card the window must surface
      task('reborn', { status: 'done', created_at: '2026-01-01T00:00:00+08:00', finished_at: '2026-10-08T11:59:00+08:00' }),
      // no finished_at: falls back to created_at
      task('unfinished', { status: 'done', created_at: '2026-10-08T11:00:00+08:00', finished_at: null })
    ]
    expect(sortColumn('done', tasks).map((t) => t.id)).toEqual(['reborn', 'unfinished', 'old'])
  })

  it('orders cancelled by finished_at too, newest first, falling back to created_at', () => {
    // Cancellation is a terminal column with the same window as done, so it
    // uses the same sort key.
    const rows = [
      task('old', { status: 'cancelled', created_at: '2026-01-01T00:00:00+08:00', finished_at: '2026-01-02T00:00:00+08:00' }),
      task('recent', { status: 'cancelled', created_at: '2026-01-01T00:00:00+08:00', finished_at: '2026-10-08T11:59:00+08:00' }),
      task('unfinished', { status: 'cancelled', created_at: '2026-10-08T11:00:00+08:00', finished_at: null })
    ]
    expect(sortColumn('cancelled', rows).map((t) => t.id)).toEqual(['recent', 'unfinished', 'old'])
  })

  it('orders the remaining columns newest-first by created_at', () => {
    for (const status of ['running', 'verifying', 'failed']) {
      const rows = [
        task('a', { status, created_at: '2026-10-08T09:00:00+08:00' }),
        task('b', { status, created_at: '2026-10-08T11:00:00+08:00' }),
        task('c', { status, created_at: '2026-10-08T10:00:00+08:00' })
      ]
      expect(sortColumn(status, rows).map((t) => t.id)).toEqual(['b', 'c', 'a'])
    }
  })

  it('does not mutate the input', () => {
    const rows = [task('a', { status: 'done', created_at: '2026-10-08T09:00:00+08:00' })]
    sortColumn('done', rows)
    expect(rows).toHaveLength(1)
  })
})

describe('time range', () => {
  const today = task('today', { created_at: new Date(NOW - 60 * 1000).toISOString() })
  const fiveDays = task('five', { created_at: new Date(NOW - 5 * DAY).toISOString() })
  const twentyDays = task('twenty', { created_at: new Date(NOW - 20 * DAY).toISOString() })
  const longAgo = task('old', { created_at: '2020-01-01T00:00:00+08:00' })

  it('matches today / 7d / 30d / all', () => {
    expect(inRange(today, 'today', NOW)).toBe(true)
    expect(inRange(fiveDays, 'today', NOW)).toBe(false)
    expect(inRange(fiveDays, '7d', NOW)).toBe(true)
    expect(inRange(twentyDays, '7d', NOW)).toBe(false)
    expect(inRange(twentyDays, '30d', NOW)).toBe(true)
    expect(inRange(longAgo, '30d', NOW)).toBe(false)
    for (const range of ['today', '7d', '30d', 'all'] as const) {
      expect(inRange(longAgo, range, NOW)).toBe(range === 'all')
    }
  })

  it('keeps a task whose created_at is absent rather than hiding it', () => {
    expect(inRange(task('x', { created_at: null }), 'today', NOW)).toBe(true)
  })

  it('narrows the whole board by range and project together', () => {
    const rows = [
      task('a', { project: 'one', created_at: new Date(NOW - 60 * 1000).toISOString() }),
      task('b', { project: 'two', created_at: new Date(NOW - 60 * 1000).toISOString() }),
      task('c', { project: 'two', created_at: new Date(NOW - 20 * DAY).toISOString() })
    ]
    const filtered = filterBoard(
      rows,
      { ...DEFAULT_FILTER, range: 'today', projects: ['two'] },
      NOW
    )
    expect(filtered.map((t) => t.id)).toEqual(['b'])
  })
})

describe('fetch budget coverage', () => {
  const rows = (n: number, newestAt: number, stepMs: number): Task[] =>
    Array.from({ length: n }, (_, i) =>
      task(`r${i}`, { created_at: new Date(newestAt - i * stepMs).toISOString() })
    )

  it('is covered when the server returns a short page', () => {
    expect(needsMoreBudget('7d', rows(3, NOW, 1000), 200, NOW)).toBe(false)
  })

  it('grows a full page whose oldest row is still inside the range', () => {
    expect(needsMoreBudget('7d', rows(200, NOW, 60 * 1000), 200, NOW)).toBe(true)
  })

  it('stops when the oldest row has reached past the range boundary', () => {
    // 200 rows spanning back well past 7 days
    expect(needsMoreBudget('7d', rows(200, NOW, DAY), 200, NOW)).toBe(false)
  })

  it('a full page of anything keeps growing for "all"', () => {
    expect(needsMoreBudget('all', rows(200, NOW, 1000), 200, NOW)).toBe(true)
  })

  it('never asks to grow past the cap', () => {
    expect(needsMoreBudget('all', rows(2000, NOW, 1000), 2000, NOW)).toBe(false)
  })
})

describe('canGrowBudget', () => {
  it('says yes at the floor, no at the cap', () => {
    expect(canGrowBudget(MIN_BUDGET)).toBe(true)
    expect(canGrowBudget(MAX_BUDGET)).toBe(false)
  })

  it('flips exactly at the cap, one row either side', () => {
    // The boundary is the whole point: one below the cap can still be raised,
    // the cap itself cannot. This is the single comparison the warning block
    // and the fetch both read.
    expect(canGrowBudget(MAX_BUDGET - 1)).toBe(true)
    expect(canGrowBudget(MAX_BUDGET + 1)).toBe(false)
  })
})

describe('address-bar filter', () => {
  it('reads a full query, projects comma-separated', () => {
    expect(parseBoardFilter('range=7d&projects=core,web&done=expanded&hide=done')).toEqual({
      range: '7d',
      projects: ['core', 'web'],
      expanded: true,
      hidden: ['done']
    })
  })

  it('reads the empty query as the defaults (all projects)', () => {
    expect(parseBoardFilter('')).toEqual(DEFAULT_FILTER)
    expect(parseBoardFilter(undefined)).toEqual(DEFAULT_FILTER)
    expect(parseBoardFilter('').projects).toBeNull()
  })

  it('reads an explicit empty selection as "none", not "all"', () => {
    expect(parseBoardFilter('projects=').projects).toEqual([])
  })

  it('ignores a range it does not know', () => {
    expect(parseBoardFilter('range=forever').range).toBe('all')
  })

  it('still reads the legacy single ?project= as a one-element set', () => {
    // Old bookmarks keep working; the board never writes `project` again.
    expect(parseBoardFilter('project=core').projects).toEqual(['core'])
    // The new key wins when both are present.
    expect(parseBoardFilter('projects=web&project=core').projects).toEqual(['web'])
  })

  it('writes only the non-default pieces, never the legacy key', () => {
    expect(boardQuery(DEFAULT_FILTER)).toBe('')
    expect(
      boardQuery({ range: '7d', projects: ['core', 'web'], expanded: true, hidden: ['done'] })
    ).toBe('range=7d&projects=core,web&done=expanded&hide=done')
    // All-selected is the default and writes nothing.
    expect(boardQuery({ range: 'all', projects: null, expanded: false, hidden: [] })).toBe('')
    // None-selected is a real (non-default) narrowing, so it is written.
    expect(boardQuery({ range: 'all', projects: [], expanded: false, hidden: [] })).toBe('projects=')
  })

  it('round-trips the project set', () => {
    const filter = {
      range: '30d' as const,
      projects: ['x y', 'web'],
      expanded: true,
      hidden: ['done']
    }
    expect(parseBoardFilter(boardQuery(filter))).toEqual(filter)
  })
})

/** A project row with only the field these rules read. */
function project(id: string): Project {
  return { id } as unknown as Project
}

describe('rows and cards read one set', () => {
  const projects = [project('one'), project('two'), project('three')]
  const rows = [
    task('a', { project: 'one' }),
    task('b', { project: 'two' }),
    task('c', { project: 'two' }),
    task('d', { project: 'three' })
  ]

  it('draws every lane when the set is the default (null)', () => {
    expect(visibleProjects(projects, DEFAULT_FILTER).map((p) => p.id)).toEqual([
      'one',
      'two',
      'three'
    ])
  })

  it('keeps exactly the selected lanes, in registry order', () => {
    const filter = { ...DEFAULT_FILTER, projects: ['three', 'one'] }
    expect(visibleProjects(projects, filter).map((p) => p.id)).toEqual(['one', 'three'])
  })

  it('a lane dropped from the set has no cards left anywhere', () => {
    // The defect card 38 fixes: hiding a lane used to leave its cards behind in
    // another row. Now one set feeds both, so the two can never disagree.
    const filter = { ...DEFAULT_FILTER, projects: ['one', 'three'] }
    const lanes = visibleProjects(projects, filter).map((p) => p.id)
    const kept = filterBoard(rows, filter, NOW)
    for (const hidden of ['two']) {
      expect(lanes).not.toContain(hidden)
      expect(kept.some((t) => t.project === hidden)).toBe(false)
    }
    expect(kept.map((t) => t.id)).toEqual(['a', 'd'])
  })

  it('an empty set draws no lanes and keeps no cards', () => {
    const filter = { ...DEFAULT_FILTER, projects: [] }
    expect(visibleProjects(projects, filter)).toEqual([])
    expect(filterBoard(rows, filter, NOW)).toEqual([])
  })
})

describe('grouping', () => {
  it('puts cancelled in its own column, not among the failures', () => {
    const grouped = groupColumns([
      task('c1', { status: 'cancelled', created_at: '2026-10-08T09:00:00+08:00' }),
      task('f1', { status: 'failed', created_at: '2026-10-08T10:00:00+08:00' }),
      task('t1', { status: 'timeout', created_at: '2026-10-08T11:00:00+08:00' })
    ])
    expect(grouped.cancelled.map((t) => t.id)).toEqual(['c1'])
    expect(grouped.abnormal.map((t) => t.id)).toEqual(['t1', 'f1'])
  })

  it('puts blocked in its own column, and keeps failed / timeout out of it', () => {
    // A boundary breach is a waiting room, not a verdict: blocked gets its own
    // column and does NOT land in `abnormal` with the failure-like states.
    const grouped = groupColumns([
      task('b1', { status: 'blocked', created_at: '2026-10-08T09:00:00+08:00' }),
      task('f1', { status: 'failed', created_at: '2026-10-08T10:00:00+08:00' }),
      task('t1', { status: 'timeout', created_at: '2026-10-08T11:00:00+08:00' })
    ])
    expect(grouped.blocked.map((t) => t.id)).toEqual(['b1'])
    expect(grouped.abnormal.map((t) => t.id)).toEqual(['t1', 'f1'])
    // blocked is nowhere near the failure column
    expect(grouped.abnormal.some((t) => t.status === 'blocked')).toBe(false)
    expect(grouped.blocked.some((t) => t.status === 'failed')).toBe(false)
  })

  it('places abnormal terminal states in the last column and orders each', () => {
    const grouped = groupColumns([
      task('f1', { status: 'failed', created_at: '2026-10-08T09:00:00+08:00' }),
      task('t1', { status: 'timeout', created_at: '2026-10-08T11:00:00+08:00' }),
      task('r1', { status: 'running', created_at: '2026-10-08T10:00:00+08:00' })
    ])
    expect(grouped.abnormal.map((t) => t.id)).toEqual(['t1', 'f1'])
    expect(grouped.running.map((t) => t.id)).toEqual(['r1'])
    expect(grouped.done).toEqual([])
  })
})

describe('visible status columns (泳道 显隐)', () => {
  it('defaults to every contract column when nothing is hidden', () => {
    expect(visibleColumns(DEFAULT_FILTER).map((c) => c.key)).toEqual(COLUMNS.map((c) => c.key))
  })

  it('drops exactly the hidden keys, keeping contract order', () => {
    // Toggled in one order, rendered in contract order -- the header row never
    // reshuffles just because a column was hidden before another.
    const filter = { ...DEFAULT_FILTER, hidden: ['done'] }
    expect(visibleColumns(filter).map((c) => c.key)).toEqual([
      'running',
      'verifying',
      'cancelled',
      'blocked',
      'abnormal'
    ])
  })

  it('reads ?hide= as a set, dropping unknown and duplicate keys', () => {
    expect(parseBoardFilter('hide=done').hidden).toEqual(['done'])
    expect(parseBoardFilter('hide=done,cancelled').hidden).toEqual(['done', 'cancelled'])
    // duplicates collapse, and a key the contract does not declare is ignored
    expect(parseBoardFilter('hide=done,done,nope').hidden).toEqual(['done'])
    // absent -> the default, which shows every column
    expect(parseBoardFilter('').hidden).toEqual([])
    expect(parseBoardFilter(undefined).hidden).toEqual([])
  })

  it('writes ?hide= in contract order and leaves the default empty', () => {
    expect(
      boardQuery({ range: 'all', projects: null, expanded: false, hidden: ['cancelled', 'done'] })
    ).toBe('hide=done,cancelled')
    // A default board (nothing hidden) writes no query at all.
    expect(boardQuery(DEFAULT_FILTER)).toBe('')
  })

  it('counts hidden columns and the cards in hand inside them', () => {
    const groups = groupColumns([
      task('r', { status: 'running' }),
      task('d1', { status: 'done' }),
      task('d2', { status: 'done' }),
      task('f', { status: 'failed' })
    ])
    expect(hiddenTally({ ...DEFAULT_FILTER, hidden: ['done'] }, groups)).toEqual({
      count: 1,
      cards: 2
    })
    expect(hiddenTally(DEFAULT_FILTER, groups)).toEqual({ count: 0, cards: 0 })
    // A hidden column with no cards still counts as a hidden column.
    expect(hiddenTally({ ...DEFAULT_FILTER, hidden: ['cancelled'] }, groups)).toEqual({
      count: 1,
      cards: 0
    })
  })

  it('derives the grid track list from the visible count, never a literal', () => {
    expect(gridTracks(6)).toBe('var(--lane) repeat(6, minmax(var(--col), 1fr))')
    expect(gridTracks(5)).toBe('var(--lane) repeat(5, minmax(var(--col), 1fr))')
    // All hidden: `repeat(0, ...)` is an invalid track list, so keep the lane.
    expect(gridTracks(0)).toBe('var(--lane)')
  })
})

describe('a wider contract does not cross the lanes', () => {
  // The card's real worry: a 7th (or 8th) column arrives and the track count,
  // the header order and the member assignment drift apart -- pushing a
  // project's cells into a neighbour's column, silently. These pin order +
  // membership against an injected list, so the invariant is checked without a
  // browser (the real-window numbers live in the delivery notes).
  const seven: Column[] = [
    { key: 'parked', members: ['parked'] },
    { key: 'running', members: ['running'] },
    { key: 'verifying', members: ['verifying'] },
    { key: 'blocked', members: ['blocked'] },
    { key: 'done', members: ['done'] },
    { key: 'cancelled', members: ['cancelled'] },
    { key: 'abnormal', members: ['failed', 'timeout'] }
  ]
  const eight: Column[] = [
    { key: 'shelved', members: ['shelved'] },
    { key: 'running', members: ['running'] },
    { key: 'verifying', members: ['verifying'] },
    { key: 'blocked', members: ['blocked'] },
    { key: 'parked', members: ['parked'] },
    { key: 'done', members: ['done'] },
    { key: 'cancelled', members: ['cancelled'] },
    { key: 'abnormal', members: ['failed', 'timeout'] }
  ]

  /** One card per column, parked in that column's own status. */
  function onePerColumn(columns: Column[]): Task[] {
    return columns.map((column, i) => task(`t${i}`, { status: column.members[0] }))
  }

  it('keeps the visible-column order of a 7-column contract', () => {
    const keys = visibleColumns(DEFAULT_FILTER, seven).map((column) => column.key)
    expect(keys).toEqual(seven.map((column) => column.key))
    // and the grid asks for exactly lane + 7 tracks
    expect(gridTracks(keys.length)).toBe('var(--lane) repeat(7, minmax(var(--col), 1fr))')
  })

  it('assigns each card to its own column of a 7-column contract', () => {
    const grouped = groupColumns(onePerColumn(seven), seven)
    seven.forEach((column, i) => {
      // exactly the card whose status lives in this column -- nothing bled over
      expect(grouped[column.key].map((t) => t.id)).toEqual([`t${i}`])
    })
  })

  it('hiding one of eight leaves the other seven in order, no track for it', () => {
    const filter = { ...DEFAULT_FILTER, hidden: ['blocked'] }
    const keys = visibleColumns(filter, eight).map((column) => column.key)
    expect(keys).toEqual(['shelved', 'running', 'verifying', 'parked', 'done', 'cancelled', 'abnormal'])
    expect(gridTracks(keys.length)).toBe('var(--lane) repeat(7, minmax(var(--col), 1fr))')
    // membership is unchanged by hiding: each card is still in its own column.
    const grouped = groupColumns(onePerColumn(eight), eight)
    eight.forEach((column, i) => {
      expect(grouped[column.key].map((t) => t.id)).toEqual([`t${i}`])
    })
  })
})
