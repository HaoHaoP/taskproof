/**
 * The reasoning behind the desktop-integration switches -- tray, Dock badge and
 * notifications -- kept free of Electron so it can be unit-tested.
 *
 * The renderer is not the only thing that can read the local API: reads are not
 * token-gated, so the main process polls `/api/summary` and `/api/tasks` itself.
 * That keeps the write token on one side of the boundary and gives the switches
 * a single owner. The transport and the Electron objects live in `index.ts`;
 * what lives here is the arithmetic and the de-duplication, the part worth
 * pinning.
 */

/**
 * The terminal states that count as "not passed". `cancelled` is deliberately
 * absent: cancellation is an operator action, not a defect (card 21 split it
 * into its own column), so it must never light up the failure badge.
 */
export const NOT_PASSING: readonly string[] = ['failed', 'blocked', 'timeout']

/** The one status that reads as "the task finished". */
export const DONE: readonly string[] = ['done']

/**
 * `n` for `app.dock.setBadge(String(n))`: failed + blocked + timeout, and never
 * cancelled. A missing summary (the service is down) reads as 0.
 */
export function notPassingCount(summary: Record<string, number> | null | undefined): number {
  if (!summary) return 0
  let total = 0
  for (const status of NOT_PASSING) {
    const count = Number(summary[status])
    if (Number.isFinite(count) && count > 0) total += count
  }
  return total
}

/** The fields the notifier needs from a task row. */
export interface NotifiableTask {
  id: string
  status: string
  /** The project id, when the row carries one; used only in the body. */
  project?: string
}

/**
 * De-duplicates notifications by task id.
 *
 * Polling runs every couple of seconds, so the same failed (or done) row comes
 * back on every pass. The tracker hands back only the rows in the watched
 * states that it has not reported yet, and remembers them so a later poll stays
 * quiet. Each id is claimed once, whichever watched state it first surfaced in.
 */
export class NotificationTracker {
  private readonly seen = new Set<string>()

  /** Newly-seen rows whose status is in `statuses`; they are marked as seen. */
  claim(tasks: readonly NotifiableTask[], statuses: readonly string[]): NotifiableTask[] {
    const fresh: NotifiableTask[] = []
    for (const task of tasks) {
      const id = String(task.id ?? '')
      if (id === '' || !statuses.includes(task.status)) continue
      if (this.seen.has(id)) continue
      this.seen.add(id)
      fresh.push(task)
    }
    return fresh
  }
}

/** The notification body: `project · id`, or just the id. Never the token. */
export function notificationBody(task: NotifiableTask): string {
  return task.project ? `${task.project} · ${task.id}` : task.id
}
