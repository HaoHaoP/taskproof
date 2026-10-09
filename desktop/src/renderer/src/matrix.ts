/**
 * The matrix board's reasoning, pulled out of the view.
 *
 * Everything here is plain data in / data out, in the same spirit as
 * `shell.ts`: the board's *decisions* -- which ten finished cards survive the
 * window, how each column is ordered, whether a row belongs to the selected
 * time range, how big a fetch the range needs -- are worth pinning without a
 * DOM or a server. The SFCs then only wire these answers to markup.
 *
 * Two timestamps matter and they are deliberately different:
 *  - the finished column is ordered by `finished_at` (falling back to
 *    `created_at`) because "recently finished" is what that column means,
 *  - the time-range filter is bounded by `created_at`, the server's canonical
 *    ordering key, so the fetch-coverage check and the filter agree on what
 *    "older" means.
 */
import type { Project, Task } from './api/client'
import { COLUMNS, columnFor } from './contract'

/** How many cards a windowed terminal column (done, cancelled) shows before the
 *  fold bar. v1 constant, not a setting: the fold bar exists precisely so this
 *  need not be one. */
export const DONE_WINDOW = 10

/** The fetch budget's floor and ceiling, in rows. */
export const MIN_BUDGET = 200
export const MAX_BUDGET = 2000

export type RangeChoice = 'today' | '7d' | '30d' | 'all'

export const RANGES: RangeChoice[] = ['today', '7d', '30d', 'all']
export const DEFAULT_RANGE: RangeChoice = 'all'

/** The one value `?done=` accepts; anything else (or absent) means collapsed. */
export const DONE_EXPANDED = 'expanded'

export interface BoardFilter {
  range: RangeChoice
  /**
   * The selected project ids, in the order the multi-select handed them over.
   * `null` is the default and means "every project"; an array -- even an empty
   * one -- is an explicit narrowing, so toggling a project off is not the same
   * as never having chosen. One set drives both the lanes the board draws
   * (`visibleProjects`) and the cards it keeps (`filterBoard`).
   */
  projects: string[] | null
  /** Whether the finished column has been unfolded past its window. */
  expanded: boolean
}

export const DEFAULT_FILTER: BoardFilter = {
  range: DEFAULT_RANGE,
  projects: null,
  expanded: false
}

export function isRange(value: unknown): value is RangeChoice {
  return typeof value === 'string' && (RANGES as string[]).includes(value)
}

/**
 * Read the board's filter out of a URL query. Absent / malformed pieces fall
 * back to the defaults, so a hand-edited or stale URL still lands on a real
 * board ("no query string" is the same thing as "every default").
 */
export type QueryLike =
  | string
  | URLSearchParams
  | Record<string, unknown>
  | null
  | undefined

/** One query value, from a string, a URLSearchParams, or vue-router's parsed
 *  query object. A repeated key takes its first value. */
function readParam(query: QueryLike, key: string): string | null {
  if (query instanceof URLSearchParams) return query.get(key)
  if (typeof query === 'string') return new URLSearchParams(query).get(key)
  if (query && typeof query === 'object') {
    const value = (query as Record<string, unknown>)[key]
    if (Array.isArray(value)) return value.length ? String(value[0]) : null
    return value == null ? null : String(value)
  }
  return null
}

/**
 * The selected projects, from the one canonical `?projects=` key. The comma is
 * the separator; the value is percent-encoded by `URLSearchParams` on the way
 * out, so an id containing a comma would be ambiguous -- project ids are slugs,
 * so this is the documented syntax rather than a hidden one.
 *
 * An absent key means "every project" (`null`), which is also the default and
 * therefore the state that writes no query at all. A present-but-empty key
 * (`?projects=`) is an explicit "none", which is different.
 *
 * Legacy `?project=<id>` (the single-select this board used to carry) is still
 * read as a one-element narrowing so an old bookmark lands on a real board; it
 * is never written again -- the multi-select always writes `?projects=`.
 */
function readProjects(query: QueryLike): string[] | null {
  const multi = readParam(query, 'projects')
  if (multi !== null) {
    if (multi.trim() === '') return []
    return multi
      .split(',')
      .map((id) => id.trim())
      .filter((id) => id.length > 0)
  }
  const single = readParam(query, 'project')
  return single ? [single] : null
}

export function parseBoardFilter(query: QueryLike): BoardFilter {
  const rawRange = readParam(query, 'range')
  return {
    range: isRange(rawRange) ? rawRange : DEFAULT_RANGE,
    projects: readProjects(query),
    expanded: readParam(query, 'done') === DONE_EXPANDED
  }
}

/**
 * The query string for a filter, with every default left out -- so a default
 * board is addressable as `/matrix` with no query at all, and only a real
 * narrowing shows up in the address bar (and in history).
 */
export function boardQuery(filter: BoardFilter): string {
  const params = new URLSearchParams()
  if (filter.range !== DEFAULT_RANGE) params.set('range', filter.range)
  if (filter.projects !== null) params.set('projects', filter.projects.join(','))
  if (filter.expanded) params.set('done', DONE_EXPANDED)
  // URLSearchParams percent-encodes the comma; a plain comma is the documented
  // separator and keeps the address bar readable.
  return params.toString().replace(/%2C/g, ',')
}

/** Epoch milliseconds, or null when the value is missing or unparseable. */
function stamp(value: string | null | undefined): number | null {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

/** Descending by time, but a null key always sinks to the bottom rather than
 *  pretending to be the newest or the oldest. */
function newestFirst(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0
  if (a === null) return 1
  if (b === null) return -1
  return b - a
}

/** Ascending by time; a null key likewise sinks to the bottom. */
function oldestFirst(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0
  if (a === null) return 1
  if (b === null) return -1
  return a - b
}

/** A terminal card's sort key: `finished_at`, falling back to `created_at`. */
export function finishedKey(task: Task): string | null {
  return task.finished_at ?? task.created_at
}

/**
 * Order the queue. Since card 22 the queue order is the explicit `queue_seq`,
 * not creation time: the operator edits it, and equal numbers are one wave.
 * Rows without a seq sink below the numbered ones, then tie on creation time so
 * an untouched queue still reads oldest-first.
 */
function queueOrder(a: Task, b: Task): number {
  const sa = a.queue_seq
  const sb = b.queue_seq
  if (sa === null || sa === undefined) {
    if (sb === null || sb === undefined) return oldestFirst(stamp(a.created_at), stamp(b.created_at))
    return 1
  }
  if (sb === null || sb === undefined) return -1
  if (sa !== sb) return sa - sb
  return oldestFirst(stamp(a.created_at), stamp(b.created_at))
}

/**
 * Order one column's tasks. Queued is the only column where order is meaning --
 * the head of the queue is the next task, and the order is the editable
 * `queue_seq`. Every other column runs newest first; the two terminal columns
 * (done and cancelled) measure "newest" by their finish time, because that is
 * the head their window shows.
 */
export function sortColumn(key: string, tasks: Task[]): Task[] {
  const copy = [...tasks]
  if (key === 'queued') {
    copy.sort(queueOrder)
  } else if (key === 'done' || key === 'cancelled') {
    copy.sort((a, b) => newestFirst(stamp(finishedKey(a)), stamp(finishedKey(b))))
  } else {
    copy.sort((a, b) => newestFirst(stamp(a.created_at), stamp(b.created_at)))
  }
  return copy
}

/** Group tasks into their columns and order each one. */
export function groupColumns(tasks: Task[]): Record<string, Task[]> {
  const grouped: Record<string, Task[]> = {}
  for (const column of COLUMNS) grouped[column.key] = []
  for (const task of tasks) grouped[columnFor(task.status).key].push(task)
  for (const column of COLUMNS) grouped[column.key] = sortColumn(column.key, grouped[column.key])
  return grouped
}

export interface DoneWindow {
  /** The cards to render, already ordered. */
  visible: Task[]
  /** `total - visible.length`: the "还有 N 张" number, 0 when everything fits. */
  hidden: number
  /** Every card in hand, before the window. */
  total: number
}

/**
 * Apply a terminal column's window. Not expanded, only the first `size` cards
 * survive and the rest are counted; expanded, the whole list passes through.
 * The window is applied *after* filtering, so it is "the ten most recent in the
 * current scope". Shared verbatim by the done and cancelled columns.
 */
export function doneWindow(cards: Task[], expanded: boolean, size = DONE_WINDOW): DoneWindow {
  const visible = expanded ? cards : cards.slice(0, size)
  return { visible, hidden: cards.length - visible.length, total: cards.length }
}

/** Millisecond boundary for a range. `all` has no boundary. */
export function rangeStart(range: RangeChoice, now: number): number {
  switch (range) {
    case 'today': {
      const start = new Date(now)
      start.setHours(0, 0, 0, 0)
      return start.getTime()
    }
    case '7d':
      return now - 7 * 24 * 60 * 60 * 1000
    case '30d':
      return now - 30 * 24 * 60 * 60 * 1000
    case 'all':
      return Number.NEGATIVE_INFINITY
  }
}

/**
 * Does a task fall inside the selected range? Bounded by `created_at`: a task
 * with no parseable timestamp is kept rather than silently dropped.
 */
export function inRange(task: Task, range: RangeChoice, now: number): boolean {
  if (range === 'all') return true
  const created = stamp(task.created_at)
  if (created === null) return true
  return created >= rangeStart(range, now)
}

/** The whole board's filter, applied together: range, then project set. */
export function filterBoard(tasks: Task[], filter: BoardFilter, now: number): Task[] {
  return tasks.filter(
    (task) =>
      inRange(task, filter.range, now) &&
      (filter.projects === null || filter.projects.includes(task.project))
  )
}

/**
 * The projects whose lane the board draws. This reads the *same* `filter.projects`
 * set `filterBoard` uses to keep cards, so a lane can never disagree with the
 * cards inside it -- the defect card 38 exists to fix, where a lane could be
 * hidden while its cards stayed behind in another lane. `null` (the default)
 * draws every project, in registry order.
 */
export function visibleProjects(projects: Project[], filter: BoardFilter): Project[] {
  if (filter.projects === null) return [...projects]
  const chosen = new Set(filter.projects)
  return projects.filter((project) => chosen.has(project.id))
}

/**
 * Should the fetch budget grow before it can cover the range? The service
 * returns newest-created first, so the last row is the oldest one in hand:
 * when its `created_at` is still newer than the range boundary, older in-range
 * rows exist that the budget cut off.
 *
 *  - a short page means the server had nothing more -> covered,
 *  - `all` always wants more, up to the cap,
 *  - a page that is exactly full, with its oldest row still inside the range,
 *    means "grow".
 */
export function needsMoreBudget(
  range: RangeChoice,
  rows: Task[],
  budget: number,
  now: number
): boolean {
  if (budget >= MAX_BUDGET) return false
  if (rows.length < budget) return false
  if (range === 'all') return true
  if (rows.length === 0) return false
  const oldest = stamp(rows[rows.length - 1].created_at)
  if (oldest === null) return false
  return oldest > rangeStart(range, now)
}
