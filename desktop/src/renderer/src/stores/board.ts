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
import { createClient, type BoardClient, type Project, type Summary, type Task } from '../api/client'
import { columnFor, unknownStatuses } from '../contract'
import type { PollChoice, ServiceStatus } from '../../../preload/types'

const DEFAULT_PORT = 8787
const POLL_MS = 2000

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
        client!.tasks({ limit: 200 }),
        client!.summary()
      ])
      projects.value = nextProjects
      tasks.value = nextTasks
      summary.value = nextSummary
      lastError.value = null
    } catch (cause) {
      // Keep the last good snapshot on screen; a dropped poll must not blank it.
      lastError.value = String(cause)
    }
  }

  async function openTask(id: string): Promise<void> {
    if (!client) return
    const body = await client.task(id)
    detail.value = { task: body.task, events: body.events }
  }

  function closeTask(): void {
    detail.value = null
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

  /** Re-attempt from scratch: the service may have come back on a new port. */
  function retry(): void {
    client = null
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
    closeTask,
    start,
    stop,
    setPoll,
    retry,
    dispose,
    watchService
  }
})
