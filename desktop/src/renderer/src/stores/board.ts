/**
 * The one place that talks to the local service.
 *
 * Two rules from the design review:
 *  - presentational components never fetch and never touch this store; a route
 *    component is the container that owns data,
 *  - polling lives here, so there is exactly one poller instead of one per view.
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createClient,
  type BoardClient,
  type Project,
  type ProjectGroup,
  type Summary,
  type Task,
  type TaskEvent
} from '../api/client'
import { columnFor, unknownStatuses } from '../contract'
import { capToLastLines } from '../logview'
import {
  DEFAULT_RANGE,
  MAX_BUDGET,
  MIN_BUDGET,
  laneProjectMap,
  needsMoreBudget,
  type RangeChoice
} from '../matrix'
import type { PollChoice, ServiceStatus } from '../../../preload/types'

const DEFAULT_PORT = 8787
const POLL_MS = 2000
/** The log tab tails its file once a second -- faster than the board pump,
 *  because a reader watching a running task expects the tail to keep up. */
const LOG_POLL_MS = 1000
/** Once the loaded log passes this many lines only the tail survives, with a
 *  notice -- never a silent drop. */
export const LOG_MAX_LINES = 5000
/** The adaptive fetch never loops more than this many times per refresh. */
const MAX_GROW_STEPS = 8

function initialService(): ServiceStatus {
  return { state: 'starting', port: null, workspace: '', detail: '' }
}

/** Renderer-only fallback so the UI can also be opened in a plain browser. */
async function resolveBaseUrl(): Promise<string> {
  const tp = window.tp
  if (tp) {
    const status = await tp.service.status()
    if (status.port) return `http://127.0.0.1:${status.port}`
    throw new Error(status.detail || 'the local service is not up yet')
  }
  const override = new URLSearchParams(location.search).get('port')
  return `http://127.0.0.1:${override ?? DEFAULT_PORT}`
}

export const useBoardStore = defineStore('board', () => {
  const service = ref<ServiceStatus>(initialService())
  const connected = ref(false)
  const lastError = ref<string | null>(null)

  const tasks = ref<Task[]>([])
  /** The flat, one-row-per-lane registry overview. The projects page and the
   *  empty-state banner still read it; the board draws its project rows from
   *  `projectGroups` instead. */
  const projects = ref<Project[]>([])
  /** The grouped (D2 shape C) view: one row per project with its lanes nested.
   *  This is the board's row source. */
  const projectGroups = ref<ProjectGroup[]>([])
  /** Lifecycle tallies by status word, as the API reports them. The mast and
   *  the tasks page's "taken M of N" read the same object. */
  const summary = ref<Summary>({})
  /** The board's time range; the view mirrors it from the address bar. It
   *  drives the *fetch budget*, not the filtering (which the view does). */
  const range = ref<RangeChoice>(DEFAULT_RANGE)
  /** How many rows the client currently asks for. Raised by the range needing
   *  older data (up to the cap) and by the tasks page's "take more". */
  const fetchBudget = ref(MIN_BUDGET)
  /** True when the last fetch filled the budget right up to the cap -- there
   *  may be older rows we could not reach, so the UI must say so. */
  const capped = ref(false)
  const detail = ref<{ task: Task; events: { ts: string; event: string; payload: unknown }[] } | null>(
    null
  )

  /**
   * The log tab's own state. `logText` keeps the *raw* bytes (ANSI and all) --
   * the panel strips them for display and the copy button hands the raw text
   * over. The rest is the continuation cursor and the notices the panel shows.
   */
  const logTaskId = ref<string | null>(null)
  const logText = ref('')
  const logNext = ref<number | null>(null)
  const logEof = ref(false)
  const logSize = ref(0)
  const logOmitted = ref(0)
  const logTruncated = ref(false)
  const logError = ref<string | null>(null)
  /** Whether the log tab is actually open; the pump runs only then. */
  const logActive = ref(false)

  /** Polling is a setting rather than a constant, because the mast reports
   *  its state: an indicator that cannot be off is decoration. */
  const poll = ref<PollChoice>('2s')
  const polling = ref(false)

  let client: BoardClient | null = null
  let timer: ReturnType<typeof setInterval> | undefined
  let logTimer: ReturnType<typeof setInterval> | undefined
  let unsubscribe: (() => void) | undefined

  /** Status words the API reported that this build does not know about. */
  const unknownWords = computed(() => unknownStatuses(tasks.value.map((task) => task.status)))

  /** Tasks grouped by column. The header counts and the mast tally both read
   *  this, so they cannot disagree. */
  const tasksByColumn = computed<Record<string, Task[]>>(() => {
    const grouped: Record<string, Task[]> = {}
    for (const task of tasks.value) {
      const column = columnFor(task.status)
      ;(grouped[column.key] ??= []).push(task)
    }
    return grouped
  })

  const abnormalCount = computed(() => tasksByColumn.value.abnormal?.length ?? 0)
  const inFlightCount = computed(() =>
    tasks.value.filter((task) => task.status === 'running' || task.status === 'verifying').length
  )

  /** Every task the service knows about, summed from the by-status summary --
   *  the denominator the "taken M of N" readouts compare against. */
  const total = computed(() =>
    Object.values(summary.value).reduce((sum, count) => sum + (count || 0), 0)
  )

  /**
   * Lane (taskgroup) id -> owning project id, rebuilt from every group's nested
   * `taskgroups`. A task row's `project` column is a *lane* id, so the board
   * needs this map to file the card under the right project row. Holding it
   * here means the view never re-derives the mapping, and it comes from the
   * grouped view alone -- no extra lane-list request.
   */
  const laneProject = computed(() => laneProjectMap(projectGroups.value))

  async function connect(): Promise<void> {
    const baseUrl = await resolveBaseUrl()
    client = createClient(baseUrl)
    const health = await client.health()
    service.value = {
      state: 'ready',
      port: Number(new URL(baseUrl).port),
      workspace: service.value.workspace,
      detail: `api ${health.version}`
    }
    connected.value = true
  }

  /**
   * Pull the task list, growing the budget while the current range still needs
   * older rows and the budget has room to grow. The service returns
   * newest-created first, so we compare the oldest row in hand against the
   * range boundary; `all` keeps growing to the cap by design.
   */
  async function fetchTasks(): Promise<Task[]> {
    let budget = fetchBudget.value
    let rows = await client!.tasks({ limit: budget })
    for (let step = 0; step < MAX_GROW_STEPS; step += 1) {
      if (!needsMoreBudget(range.value, rows, budget, Date.now())) break
      budget = Math.min(budget * 2, MAX_BUDGET)
      rows = await client!.tasks({ limit: budget })
    }
    fetchBudget.value = budget
    capped.value = rows.length >= MAX_BUDGET && budget >= MAX_BUDGET
    return rows
  }

  async function refresh(): Promise<void> {
    if (!client) {
      try {
        await connect()
      } catch (cause) {
        lastError.value = String(cause)
        return
      }
    }
    try {
      const [nextProjects, nextGroups, nextTasks, nextSummary] = await Promise.all([
        client!.projects(),
        client!.projectGroups(),
        fetchTasks(),
        client!.summary()
      ])
      projects.value = nextProjects
      projectGroups.value = nextGroups
      tasks.value = nextTasks
      summary.value = nextSummary
      lastError.value = null
      // An open drawer is part of the screen too, so it gets the same treatment
      // as the list: a running task's timeline has to keep growing, otherwise
      // the "live" indicator next to it would be a lie.
      const openId = detail.value?.task.id
      if (openId) await openTask(openId)
    } catch (cause) {
      // Keep the last good snapshot on screen; a dropped poll must not blank it.
      lastError.value = String(cause)
    }
  }

  /** Follow the address bar's range. A change resets the budget to the floor so
   *  a narrower range cannot inherit the wider fetch a previous range grew to. */
  function setRange(next: RangeChoice): void {
    if (next === range.value) return
    range.value = next
    fetchBudget.value = MIN_BUDGET
    capped.value = false
    void refresh()
  }

  /** The tasks page's "take more": raise the budget one step, up to the cap. */
  function growBudget(): void {
    if (fetchBudget.value >= MAX_BUDGET) return
    fetchBudget.value = Math.min(fetchBudget.value * 2, MAX_BUDGET)
    void refresh()
  }

  async function openTask(id: string): Promise<void> {
    if (!client) return
    try {
      const body = await client.task(id)
      detail.value = { task: body.task, events: body.events }
    } catch {
      // A task that vanished while its drawer is open: keep what is on screen
      // rather than blanking the panel under the reader.
    }
  }

  function closeTask(): void {
    detail.value = null
  }

  function stopLogTimer(): void {
    if (logTimer) clearInterval(logTimer)
    logTimer = undefined
  }

  /**
   * Read one page of the open task's log.
   *
   * The first page (no cursor) is the file's tail and carries `omitted`; every
   * later page continues from `next` and its text is appended. A page that
   * arrives after the cursor moved on -- a manual refresh racing the timer, or
   * a task switch -- is dropped: appending it would splice the wrong bytes in.
   * A failure is recorded as a readable line and never clears what is loaded.
   */
  async function readLog(): Promise<void> {
    const id = logTaskId.value
    if (!id) return
    if (!client) {
      try {
        await connect()
      } catch (cause) {
        logError.value = cause instanceof Error ? cause.message : String(cause)
        return
      }
    }
    const cursor = logNext.value
    try {
      const page = await client!.log(id, cursor)
      if (logTaskId.value !== id || logNext.value !== cursor) return
      if (cursor == null) logOmitted.value = page.omitted
      if (page.text) logText.value += page.text
      logNext.value = page.next
      logEof.value = page.eof
      logSize.value = page.size
      const capped = capToLastLines(logText.value, LOG_MAX_LINES)
      if (capped.truncated) {
        logText.value = capped.text
        logTruncated.value = true
      }
      logError.value = null
    } catch (cause) {
      if (logTaskId.value !== id || logNext.value !== cursor) return
      logError.value = cause instanceof Error ? cause.message : String(cause)
    }
  }

  /**
   * Open the log tab on `id`: load its tail first (with the `omitted` count),
   * then tail it once a second -- but only while the global pump is on. With
   * polling off the first page still loads; the rest waits for the manual
   * refresh button, because an off switch that still polled would be a lie.
   */
  function startLog(id: string): void {
    if (logTaskId.value !== id) {
      logTaskId.value = id
      logText.value = ''
      logNext.value = null
      logEof.value = false
      logSize.value = 0
      logOmitted.value = 0
      logTruncated.value = false
      logError.value = null
    }
    logActive.value = true
    stopLogTimer()
    void readLog()
    if (poll.value !== 'off') {
      logTimer = setInterval(() => void readLog(), LOG_POLL_MS)
    }
  }

  /** The log tab closed / switched back to overview: stop the tail. The text
   *  and cursor stay, so returning to the tab resumes where it left off. */
  function stopLog(): void {
    logActive.value = false
    stopLogTimer()
  }

  /** The manual refresh: one more page on demand, whether or not the pump runs. */
  function refreshLog(): void {
    void readLog()
  }

  /**
   * Read one task + its event stream without opening the drawer.
   *
   * The console needs the events to seed a "run again" form (the timeout lives
   * only in the `queued` event), and it must not navigate the reader to the
   * drawer as a side effect. Returns null on any failure -- the caller shows a
   * plain "could not read the original" rather than a half-filled form.
   */
  async function fetchDetail(id: string): Promise<{ task: Task; events: TaskEvent[] } | null> {
    if (!client) {
      try {
        await connect()
      } catch {
        return null
      }
    }
    try {
      return await client!.task(id)
    } catch {
      return null
    }
  }

  function start(intervalMs = POLL_MS): void {
    stop()
    void refresh()
    timer = setInterval(() => void refresh(), intervalMs)
    polling.value = true
  }

  function stop(): void {
    if (timer) clearInterval(timer)
    timer = undefined
    polling.value = false
  }

  /** Switch the pump. Turning it off still does one last read, so the snapshot
   *  left on screen is current rather than merely recent. */
  function setPoll(choice: PollChoice): void {
    poll.value = choice
    if (choice === 'off') {
      stop()
      // The log tail is part of the same pump: off stops it too. The first page
      // already loaded stays on screen; the manual refresh remains the way to
      // pull more without turning polling back on.
      stopLogTimer()
      void refresh()
    } else {
      start()
      // The log tab may still be open from before polling was switched off --
      // resume its tail now that the pump is live again.
      if (logActive.value && logTaskId.value) startLog(logTaskId.value)
    }
  }

  /**
   * Re-attempt from scratch. With `launch: 'manual'` the app deliberately does
   * not spawn the child on open, so the offline banner's "retry" is the user's
   * "start it now" gesture: ask the main process to (re)spawn the service, then
   * rebuild the client against whatever port comes back. With the service
   * already up this simply restarts it on the current argv.
   */
  async function retry(): Promise<void> {
    client = null
    try {
      await window.tp?.service.restart()
    } catch {
      // A refused spawn (a fixed port already taken) surfaces through the
      // status channel; the reconnect below then reports it readably.
    }
    start()
  }

  async function watchService(): Promise<void> {
    const tp = window.tp
    if (!tp) return
    service.value = await tp.service.status()
    unsubscribe = tp.service.onStatus((status) => {
      service.value = status
      if (status.state !== 'ready') connected.value = false
    })
  }

  function dispose(): void {
    stop()
    stopLogTimer()
    unsubscribe?.()
  }

  return {
    service,
    connected,
    lastError,
    tasks,
    projects,
    projectGroups,
    laneProject,
    summary,
    total,
    range,
    fetchBudget,
    capped,
    detail,
    logTaskId,
    logText,
    logNext,
    logEof,
    logSize,
    logOmitted,
    logTruncated,
    logError,
    poll,
    polling,
    unknownWords,
    tasksByColumn,
    abnormalCount,
    inFlightCount,
    connect,
    refresh,
    openTask,
    fetchDetail,
    closeTask,
    startLog,
    stopLog,
    refreshLog,
    start,
    stop,
    setPoll,
    setRange,
    growBudget,
    retry,
    dispose,
    watchService
  }
})
