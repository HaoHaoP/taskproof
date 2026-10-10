/**
 * The dispatch form's reasoning, kept out of the component.
 *
 * Three questions live here so they can be pinned without a DOM or a server:
 *  - what a "run again" prefill is (the original four fields, recovered from
 *    the task + its event stream -- the timeout is only ever carried in events,
 *    never on the row),
 *  - what the consequence summary shows (project, its *real* path, adapter, the
 *    longest duration, and the effective protected paths -- an empty list is
 *    shown explicitly, never as a blank),
 *  - the fixed vocabulary of the form (adapters, the timeout default).
 *
 * The form is deliberately four fields. Protection paths and worktree are
 * registry concerns; putting them here would make the console a second, weaker
 * editor of the registry.
 */
import type { Project, Task, TaskEvent } from './api/client'

/** The adapters the console offers. A closed list, not free text. */
export const ADAPTERS = ['codex', 'claude', 'gemini', 'opencode'] as const

/** The run's hard cap when nothing says otherwise, in seconds. */
export const DEFAULT_TIMEOUT = 1800

export interface TaskDraft {
  project: string
  brief: string
  adapter: string
  /** Seconds; the run's hard cap. */
  timeout: number
}

export function emptyDraft(project = ''): TaskDraft {
  return { project, brief: '', adapter: ADAPTERS[0], timeout: DEFAULT_TIMEOUT }
}

/**
 * The latest numeric `timeout` any event carried, or null.
 *
 * The `queued` event is where the timeout actually persists (the `tasks` table
 * has no such column), so this is how "run again" recovers the original value
 * rather than inventing the default.
 */
export function timeoutFromEvents(events: readonly TaskEvent[]): number | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const payload = events[i]?.payload
    const value = payload ? (payload as Record<string, unknown>).timeout : undefined
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return null
}

/**
 * The "run again" prefill: a *new* form seeded with the original's four fields,
 * not a blind replay. There is deliberately no source-task field -- v1 keeps
 * the ledger flat, two rows side by side.
 */
export function draftFromTask(
  task: Task,
  events: readonly TaskEvent[] = [],
  fallback = DEFAULT_TIMEOUT
): TaskDraft {
  return {
    project: task.project,
    brief: task.brief,
    adapter: task.adapter ?? ADAPTERS[0],
    timeout: timeoutFromEvents(events) ?? fallback
  }
}

/**
 * What the confirmation step renders. `forbiddenPaths` is kept as the raw list;
 * the view decides how to show "none", so an empty list stays distinguishable
 * from a list that failed to load.
 */
export interface ConsequenceSummary {
  project: string
  path: string
  adapter: string
  timeout: number
  forbiddenPaths: string[]
}

/**
 * Assemble the consequence summary from the draft and the selected project's
 * registry record. The path is the project's real `path`, never its id -- the
 * whole point of the confirmation is to say where the agent will actually run.
 */
export function consequenceSummary(
  draft: TaskDraft,
  project: Project | null | undefined
): ConsequenceSummary {
  return {
    project: draft.project,
    path: project?.path ?? '',
    adapter: draft.adapter,
    timeout: draft.timeout,
    forbiddenPaths: project?.forbidden_paths ?? []
  }
}

/** Is the draft dispatchable? A project and a non-empty brief and a positive
 *  timeout are the minimum; the summary step is where the rest is confirmed. */
export function draftValid(draft: TaskDraft): boolean {
  return (
    draft.project.trim() !== '' &&
    draft.brief.trim() !== '' &&
    Number.isFinite(draft.timeout) &&
    draft.timeout > 0
  )
}
