/**
 * The frozen REST boundary: read-only, loopback, always JSON.
 *
 * Field names are the ones the API actually returns -- they differ from the
 * prototype's mock data (`files_changed`, `group_name`, and events carrying
 * `event` + `payload`). Nothing here is guessed; the shapes were read off a
 * running server.
 */

export interface Task {
  id: string
  project: string
  status: string
  brief: string
  adapter: string | null
  model: string | null
  attempt: number | null
  group_name: string | null
  pid: number | null
  pgid: number | null
  workdir: string | null
  reasoning: string | null
  result_path: string | null
  exit_code: number | null
  verify_cmd: string | null
  verify_exit: number | null
  files_changed: number | null
  /** Live diff count while a task is running/verifying; null otherwise. */
  files_changed_live: number | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface TaskEvent {
  id: number
  task_id: string
  ts: string
  event: string
  payload: Record<string, unknown> | null
}

/** One page of a task's log file. `offset` is where this page starts,
 *  `next` is the cursor for the following page, and `omitted` is how many
 *  bytes before `offset` the first (tail) read left behind. */
export interface TaskLog {
  task_id: string
  offset: number
  next: number
  text: string
  eof: boolean
  size: number
  omitted: number
}

export interface Project {
  id: string
  path: string
  group: string
  aliases: string[]
  verify: string | null
  verify_kind: string
  forbidden_paths: string[]
  result_schema: string
  auto_registered: boolean
  /** Acceptance-probe verdict; null when a verify command was declared but
   *  never run. The API returns it on `/api/projects` (see `project_record`). */
  probe: 'passed' | 'failed' | 'none' | null
  probe_exit: number | null
  tasks: number
  in_progress: number
  failed: number
  last_activity: string | null
}

/** Keyed by status word. Every declared status is present, even at zero. */
export type Summary = Record<string, number>

/**
 * One lane (taskgroup) nested inside a grouped project row. The record is the
 * historical `Project` shape -- the same fields `/api/projects` returns -- minus
 * the per-lane stats (the group sums them into `summary`) and plus the owning
 * `project` id, so the lane knows which project row it belongs to.
 */
export type ProjectTaskgroup = Omit<
  Project,
  'tasks' | 'in_progress' | 'failed' | 'last_activity'
> & { project: string }

/**
 * `GET /api/projects?by=project` -- the D2 shape-C grouped view: one row per
 * owning project, its lanes nested in `taskgroups`, and the lifecycle statuses
 * summed across those lanes in `summary`. The flat `/api/projects` view (one
 * row per lane) is untouched and still what the projects page reads.
 */
export interface ProjectGroup {
  id: string
  path: string
  aliases: string[]
  taskgroups: ProjectTaskgroup[]
  summary: Summary
}

export interface ApiError extends Error {
  status: number
}

function apiError(status: number, message: string): ApiError {
  const error = new Error(message) as ApiError
  error.status = status
  return error
}

export interface BoardClient {
  health(): Promise<{ ok: boolean; version: string }>
  summary(): Promise<Summary>
  projects(): Promise<Project[]>
  /** The grouped (shape C) view: one row per project, its lanes nested. */
  projectGroups(): Promise<ProjectGroup[]>
  tasks(params?: { limit?: number; status?: string; project?: string }): Promise<Task[]>
  task(id: string): Promise<{ task: Task; events: TaskEvent[] }>
  events(id: string): Promise<TaskEvent[]>
  log(id: string, offset?: number | null): Promise<TaskLog>
}

export function createClient(baseUrl: string): BoardClient {
  async function get<T>(path: string): Promise<T> {
    let response: Response
    try {
      response = await fetch(baseUrl + path, { headers: { accept: 'application/json' } })
    } catch (cause) {
      // The service not being up yet is a normal state at launch, not a crash.
      throw apiError(0, `cannot reach the local service: ${String(cause)}`)
    }
    if (!response.ok) {
      throw apiError(response.status, `${path} answered ${response.status}`)
    }
    return (await response.json()) as T
  }

  return {
    health: () => get('/api/health'),
    summary: async () => (await get<{ summary: Summary }>('/api/summary')).summary,
    projects: async () => (await get<{ projects: Project[] }>('/api/projects')).projects,
    projectGroups: async () =>
      (await get<{ projects: ProjectGroup[] }>('/api/projects?by=project')).projects,
    tasks: async (params = {}) => {
      const query = new URLSearchParams()
      if (params.limit !== undefined) query.set('limit', String(params.limit))
      if (params.status) query.set('status', params.status)
      if (params.project) query.set('project', params.project)
      const suffix = query.toString() ? `?${query}` : ''
      return (await get<{ tasks: Task[] }>(`/api/tasks${suffix}`)).tasks
    },
    task: async (id) => {
      const body = await get<{ task: Task; events: TaskEvent[] }>(`/api/tasks/${encodeURIComponent(id)}`)
      return { task: body.task, events: body.events ?? [] }
    },
    events: async (id) =>
      (await get<{ events: TaskEvent[] }>(`/api/tasks/${encodeURIComponent(id)}/events`)).events,
    log: async (id, offset) => {
      const suffix = offset == null ? '' : `?offset=${offset}`
      return get<TaskLog>(`/api/tasks/${encodeURIComponent(id)}/log${suffix}`)
    }
  }
}
