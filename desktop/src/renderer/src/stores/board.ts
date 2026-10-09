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
  type Summary,
  type Task,
  type TaskEvent
} from '../api/client'
import { columnFor, unknownStatuses } from '../contract'
import {
  DEFAULT_RANGE,
  MAX_BUDGET,
  MIN_BUDGET,
  needsMoreBudget,
  type RangeChoice
} from '../matrix'
import type { PollChoice, ServiceStatus } from '../../../preload/types'

const DEFAULT_PORT = 8787
const POLL_MS = 2000
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
  const projects = ref<Project[]>([])
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

  /** Which projects the matrix shows. Absent means visible, so a project that
   *  appears in the registry shows up without needing an entry here first. */
  const visible = ref<Record<string, boolean>>({})
  /** Polling is a setting rather than a constant, because the toolbar reports
   *  its state: an indicator that cannot be off is decoration. */
  const poll = ref<PollChoice>('2s')
  const polling = ref(false)

  let client: BoardClient | null = null
  let timer: ReturnType<typeof setInterval> | undefined
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

  function isVisible(id: string): boolean {
    return visible.value[id] !== false
  }

  function toggleProject(id: string): void {
    visible.value = { ...visible.value, [id]: !isVisible(id) }
  }

  function selectAllProjects(on: boolean): void {
    const next: Record<string, boolean> = {}
    for (const project of projects.value) next[project.id] = on
    visible.value = next
  }

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
      const [nextProjects, nextTasks, nextSummary] = await Promise.all([
        client!.projects(),
        fetchTasks(),
        client!.summary()
      ])
      projects.value = nextProjects
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

  /**
   * Read one task + its event stream without opening the drawer.
   *
   * The console needs the events to seed a "run again" form (the timeout lives
   * only in the queued event), and it must not navigate the reader to the
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
      void refresh()
    } else {
      start()
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
    unsubscribe?.()
  }

  return {
    service,
    connected,
    lastError,
    tasks,
    projects,
    summary,
    total,
    range,
    fetchBudget,
    capped,
    detail,
    visible,
    poll,
    polling,
    unknownWords,
    tasksByColumn,
    abnormalCount,
    inFlightCount,
    isVisible,
    toggleProject,
    selectAllProjects,
    connect,
    refresh,
    openTask,
    fetchDetail,
    closeTask,
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
