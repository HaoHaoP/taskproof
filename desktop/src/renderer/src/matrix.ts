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
import type { ProjectGroup, Task } from './api/client'
import { COLUMNS, type Column } from './contract'
import { CAP_MAX, CAP_MIN, DEFAULT_COLUMN_CAPS } from '../../preload/types'

/** The column-window caps, one per contract column. `0` means "do not fold --
 *  show every card"; a positive cap windows that column to its N most recent.
 *
 *  Every column can carry its own cap now, so this is the code default table
 *  rather than a single constant: `done` and `cancelled` keep today's ten, and
 *  the four live columns start unfolded (`0`), so a fresh board looks exactly
 *  as it did before. The user's own table lives in App settings. */
export const DEFAULT_CAPS: Record<string, number> = DEFAULT_COLUMN_CAPS

/** The historical `done` window size, kept as the done/cancelled code default.
 *  It is just `DEFAULT_CAPS.done` under a name the fold-bar tests still read. */
export const DONE_WINDOW = DEFAULT_CAPS.done

/** The address-bar key carrying the per-column unfolded set: `?open=done,...`. */
export const OPEN_KEY = 'open'

export { CAP_MAX, CAP_MIN }

/** The fetch budget's floor and ceiling, in rows. */
export const MIN_BUDGET = 200
export const MAX_BUDGET = 2000

export type RangeChoice = 'today' | '7d' | '30d' | 'all'

export const RANGES: RangeChoice[] = ['today', '7d', '30d', 'all']
export const DEFAULT_RANGE: RangeChoice = 'all'

/** The one value the legacy `?done=` key accepts. It is READ ONLY -- an old
 *  bookmark that says "the finished columns were unfolded" is translated into
 *  the new per-column `?open=` set and never written back. */
export const DONE_EXPANDED = 'expanded'

/** The canonical key for the hidden status columns. Absent means "none hidden". */
export const HIDE_KEY = 'hide'

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
  /**
   * The columns the reader has unfolded past their window, by column key. `[]`
   * is the default (every windowed column stays folded); each terminal--or,
   * once a cap is set, each live--column carries its own state, so expanding
   * `done` leaves `cancelled` folded. Normalised to contract order.
   */
  open: string[]
  /**
   * The hidden status columns (泳道), by column key. `[]` is the default and
   * means every column is shown -- hiding is *explicit*, so a column the
   * contract grows in a later release starts visible rather than disappearing
   * the moment nobody names it. One set drives the header row, every project's
   * cells and the grid's track count, so a hidden column can never leak its
   * cards into a neighbour.
   */
  hidden: string[]
}

export const DEFAULT_FILTER: BoardFilter = {
  range: DEFAULT_RANGE,
  projects: null,
  open: [],
  hidden: []
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

/**
 * The hidden status columns, from the one canonical `?hide=` key. The comma is
 * the separator, the same documented shape as `?projects=`. An absent key means
 * "nothing hidden" -- the default -- so a stale or hand-edited URL still shows
 * the whole board rather than silently swallowing a column. A key the contract
 * does not declare is dropped: an old bookmark must not hide a column this
 * build now uses for something else. Duplicates collapse; order is preserved
 * here and normalised to contract order on the way back out.
 */
function readHidden(query: QueryLike): string[] {
  const raw = readParam(query, HIDE_KEY)
  if (raw === null) return []
  const known = new Set(COLUMNS.map((column) => column.key))
  const seen = new Set<string>()
  const out: string[] = []
  for (const piece of raw.split(',')) {
    const key = piece.trim()
    if (key && known.has(key) && !seen.has(key)) {
      seen.add(key)
      out.push(key)
    }
  }
  return out
}

/**
 * The unfolded columns, from the canonical `?open=` key. The comma is the
 * separator, the same documented shape as `?projects=` / `?hide=`. A key the
 * contract does not declare is dropped and duplicates collapse, so a stale URL
 * cannot name a column this build has repurposed.
 *
 * The legacy `?done=expanded` key (one flag that used to unfold the finished
 * *and* cancelled columns together) is still read as exactly that pair, so an
 * old bookmark lands on a real board. It is never written again: `boardQuery`
 * writes only `?open=`, and `?open=` wins when both are present.
 */
function readOpen(query: QueryLike): string[] {
  const raw = readParam(query, OPEN_KEY)
  if (raw === null) {
    return readParam(query, 'done') === DONE_EXPANDED ? ['done', 'cancelled'] : []
  }
  const declared = new Set(COLUMNS.map((column) => column.key))
  const named = new Set(
    raw
      .split(',')
      .map((piece) => piece.trim())
      .filter((key) => key.length > 0 && declared.has(key))
  )
  return COLUMNS.filter((column) => named.has(column.key)).map((column) => column.key)
}

export function parseBoardFilter(query: QueryLike): BoardFilter {
  const rawRange = readParam(query, 'range')
  return {
    range: isRange(rawRange) ? rawRange : DEFAULT_RANGE,
    projects: readProjects(query),
    open: readOpen(query),
    hidden: readHidden(query)
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
  if (filter.open.length) {
    // Contract order and no duplicates, so the address bar reads the same no
    // matter which order the columns were unfolded; the legacy `?done=expanded`
    // key is never written again.
    const open = new Set(filter.open)
    const keys = COLUMNS.filter((column) => open.has(column.key)).map((column) => column.key)
    if (keys.length) params.set(OPEN_KEY, keys.join(','))
  }
  if (filter.hidden.length) {
    // Contract order and no duplicates, so the address bar reads the same no
    // matter which order the switches were flipped. Keys the contract does not
    // declare are dropped on the way out, matching `readHidden`.
    const hidden = new Set(filter.hidden)
    const keys = COLUMNS.filter((column) => hidden.has(column.key)).map((column) => column.key)
    if (keys.length) params.set(HIDE_KEY, keys.join(','))
  }
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

/** A terminal card's sort key: `finished_at`, falling back to `created_at`. */
export function finishedKey(task: Task): string | null {
  return task.finished_at ?? task.created_at
}

/**
 * Order one column's tasks. Everything runs newest first by creation time; the
 * two terminal columns (done and cancelled) measure "newest" by their finish
 * time instead, because that is the head their window shows.
 */
export function sortColumn(key: string, tasks: Task[]): Task[] {
  const copy = [...tasks]
  if (key === 'done' || key === 'cancelled') {
    copy.sort((a, b) => newestFirst(stamp(finishedKey(a)), stamp(finishedKey(b))))
  } else {
    copy.sort((a, b) => newestFirst(stamp(a.created_at), stamp(b.created_at)))
  }
  return copy
}

/**
 * Group tasks into their columns and order each one.
 *
 * The column list is a parameter so a test can inject a wider contract (a
 * seven- or eight-column board) and prove the header order and the member
 * assignment still agree -- the "never cross a lane" invariant, checked without
 * a browser. It defaults to the real `COLUMNS`, so production reads the same
 * list the grid draws.
 *
 * A status no column claims lands in the last column, exactly like
 * `columnFor`, so an unknown word is never dropped.
 */
export function groupColumns(tasks: Task[], columns: Column[] = COLUMNS): Record<string, Task[]> {
  const grouped: Record<string, Task[]> = {}
  for (const column of columns) grouped[column.key] = []
  const fallback = columns[columns.length - 1]
  for (const task of tasks) {
    const column = columns.find((entry) => entry.members.includes(task.status)) ?? fallback
    if (column) grouped[column.key].push(task)
  }
  for (const column of columns) grouped[column.key] = sortColumn(column.key, grouped[column.key])
  return grouped
}

export interface ColumnWindow {
  /** The cards to render, already ordered. */
  visible: Task[]
  /** `total - visible.length`: the "还有 N 张" number, 0 when everything fits. */
  hidden: number
  /** Every card in hand, before the window. */
  total: number
}

/**
 * Apply a column's window. A positive `cap` keeps only that many cards unless
 * the column is unfolded; `cap === 0` means "do not fold" and lets every card
 * through. The window is applied *after* filtering and sorting, so it is "the
 * N most recent in the current scope". One function serves every column -- the
 * done/cancelled defaults are just `DEFAULT_CAPS`, not a second code path.
 */
export function columnWindow(cards: Task[], expanded: boolean, cap: number): ColumnWindow {
  const visible = expanded || cap === 0 ? cards : cards.slice(0, cap)
  return { visible, hidden: cards.length - visible.length, total: cards.length }
}

/** A translated label decision: the i18n leaf key and its interpolation data. */
export interface MatrixLabel {
  key: string
  params: Record<string, number>
}

/**
 * The chip's one-line summary of the current column window. The five branches
 * are deliberately ordered: an empty column never claims a count; `cap === 0`
 * and a cap that is not exceeded both mean every card is already visible; an
 * unfolded cap keeps the limit in the sentence so "show all" cannot be mistaken
 * for having removed that limit.
 */
export function capChipLabel(window: ColumnWindow, cap: number, expanded: boolean): MatrixLabel {
  if (window.total === 0) return { key: 'board.capChip.empty', params: {} }
  if (cap === 0 || window.total <= cap) {
    return { key: 'board.capChip.all', params: { total: window.total } }
  }
  if (expanded) {
    return { key: 'board.capChip.expanded', params: { total: window.total, cap } }
  }
  return { key: 'board.capChip.capped', params: { cap, total: window.total } }
}

/** The fixed display-cap choices, in menu order. `0` is the "all" choice. */
export const CAP_CHOICES = [5, 10, 20, 50, 0] as const

export interface CapMenuOption {
  value: number
  label: MatrixLabel
  checked: boolean
}

export interface CapMenuAction {
  kind: 'expand' | 'collapse'
  label: MatrixLabel
}

export interface CapMenu {
  options: CapMenuOption[]
  /** Zero or one state-dependent fold / unfold action. */
  actions: CapMenuAction[]
}

/**
 * The fixed cap choices plus the one state-dependent action the chip's dropdown
 * may offer. This is pure so the menu cannot invent a collapse action for a
 * column already at its cap, or an expand action when nothing is hidden.
 */
export function capMenuFor(window: ColumnWindow, cap: number, expanded: boolean): CapMenu {
  const options = CAP_CHOICES.map((value): CapMenuOption => {
    const label: MatrixLabel = value === 0
      ? { key: 'board.capMenu.all', params: {} }
      : { key: 'board.capMenu.option', params: { n: value } }
    return { value, label, checked: value === cap }
  })

  const actions: CapMenuAction[] = []
  if (window.hidden > 0) {
    actions.push({
      kind: 'expand',
      label: { key: 'board.capMenu.expand', params: { hidden: window.hidden } }
    })
  } else if (expanded && cap > 0 && window.total > cap) {
    actions.push({
      kind: 'collapse',
      label: { key: 'board.capMenu.collapse', params: { cap } }
    })
  }

  return { options, actions }
}

/** Converge a user-entered cap into the control's domain: a whole number in
 *  `0..200` (`0` = no fold). Non-finite input reads as the floor, so the caller
 *  can commit unconditionally without a second validation. */
export function clampCap(value: number): number {
  if (!Number.isFinite(value)) return CAP_MIN
  return Math.min(CAP_MAX, Math.max(CAP_MIN, Math.trunc(value)))
}

/**
 * Add or remove one column from the unfolded set, returning a fresh set in
 * contract order. Kept here (not in the SFC) so "which columns are open" is a
 * pure list operation the tests can pin directly.
 */
export function withColumnOpen(open: string[], key: string, unfolded: boolean): string[] {
  const next = new Set(open)
  if (unfolded) next.add(key)
  else next.delete(key)
  return COLUMNS.filter((column) => next.has(column.key)).map((column) => column.key)
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

/**
 * The lane (taskgroup) -> owning project map the board needs to file a task
 * under the right project row. A task row's `project` column stores the *lane*
 * id, not the owning project id; the registry's grouped view is the only place
 * that knows the ownership, because every nested lane record carries its own
 * `project` back-pointer. Built here so the store, the view and the tests all
 * read one mapping. Registry order, later entries winning a duplicate.
 */
export function laneProjectMap(groups: ProjectGroup[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const group of groups) {
    for (const lane of group.taskgroups) map[lane.id] = group.id
  }
  return map
}

/** The project a task's lane belongs to, falling back to the lane id itself.
 *  The fallback is the uncollected-registry compat path: a project that has not
 *  been folded into a taskgroup yet has lane id == project id, so identity is
 *  the right answer there. A lane the grouped view no longer lists (a removed
 *  taskgroup with old rows left behind) keeps its lane id, which draws under no
 *  project row -- the same as today, where such a lane had no row either. */
export function owningProject(task: Task, laneProject: Record<string, string>): string {
  return laneProject[task.project] ?? task.project
}

/**
 * The whole board's filter, applied together: range, then the *project* set.
 * A task survives when the project its lane belongs to is selected, so the one
 * `filter.projects` set drives both the project rows (`visibleProjects`) and
 * the cards filed under them -- the board never shows a row without its cards
 * or cards without their row. `laneProject` is the lane -> project map; a task
 * whose lane is missing from it falls back to its own lane id (see
 * `owningProject`).
 */
export function filterBoard(
  tasks: Task[],
  filter: BoardFilter,
  now: number,
  laneProject: Record<string, string>
): Task[] {
  return tasks.filter(
    (task) =>
      inRange(task, filter.range, now) &&
      (filter.projects === null || filter.projects.includes(owningProject(task, laneProject)))
  )
}

/**
 * The project rows the board draws a lane for. This reads the *same*
 * `filter.projects` set `filterBoard` keeps cards by, so a project the
 * multi-select drops loses its row and its cards together, never one without
 * the other -- the defect card 38 exists to fix, where a row could be hidden
 * while its cards stayed behind in another. `null` (the default) draws every
 * project, in registry order. Generic over `{id}` so it reads grouped project
 * rows and the historical lane records alike.
 */
export function visibleProjects<T extends { id: string }>(projects: T[], filter: BoardFilter): T[] {
  if (filter.projects === null) return [...projects]
  const chosen = new Set(filter.projects)
  return projects.filter((project) => chosen.has(project.id))
}

/**
 * The status columns (泳道) the board actually draws: every contract column the
 * filter has not hidden, in contract order. ONE list feeds the header row,
 * every project's cells and the grid's track count -- that is the whole
 * guarantee that a hidden column cannot show up in a neighbour. The list is
 * injectable so a wider contract can be exercised in a test.
 */
export function visibleColumns(filter: BoardFilter, columns: Column[] = COLUMNS): Column[] {
  const hidden = new Set(filter.hidden)
  return columns.filter((column) => !hidden.has(column.key))
}

/** What the "已隐藏 N 列" hint reports: how many columns are gone and how many
 *  cards (in hand, after filtering) went with them. Counted from the fetched
 *  cards, never from a summary that would pretend to know rows we have not
 *  received. */
export interface HiddenTally {
  count: number
  cards: number
}

export function hiddenTally(
  filter: BoardFilter,
  groups: Record<string, Task[]>,
  columns: Column[] = COLUMNS
): HiddenTally {
  const hidden = new Set(filter.hidden)
  let count = 0
  let cards = 0
  for (const column of columns) {
    if (!hidden.has(column.key)) continue
    count += 1
    cards += (groups[column.key] ?? []).length
  }
  return { count, cards }
}

/**
 * The grid's track list: one lane track (the project-name column) followed by
 * one track per *visible* status column. The count is the visible count -- not
 * a fixed six -- so hiding a column widens the rest instead of leaving a gap,
 * and a hidden column claims no track at all.
 *
 * `repeat(0, ...)` is an invalid track list, so an all-hidden board (the
 * degenerate state) keeps only the lane track rather than blanking the grid.
 */
export function gridTracks(visible: number): string {
  if (visible <= 0) return 'var(--lane)'
  return `var(--lane) repeat(${visible}, minmax(var(--col), 1fr))`
}

/**
 * Can this budget still be raised? One place, and one place only, compares a
 * budget against `MAX_BUDGET`, so the button the UI offers and the growth the
 * fetch performs can never disagree. Above (or at) the cap the budget is
 * pinned: `growBudget()` would return without touching it, so a caller that
 * still read "can grow" here would be offering a dead button.
 */
export function canGrowBudget(budget: number): boolean {
  return budget < MAX_BUDGET
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
  if (!canGrowBudget(budget)) return false
  if (rows.length < budget) return false
  if (range === 'all') return true
  if (rows.length === 0) return false
  const oldest = stamp(rows[rows.length - 1].created_at)
  if (oldest === null) return false
  return oldest > rangeStart(range, now)
}
