/**
 * Card presentation rules that are worth pinning without a DOM.
 *
 * The one rule here is the "验收已过 / Acceptance passed" badge. A card that
 * breached a protected path is parked as `blocked` and waits for a human to
 * release it -- but the *work itself* may have passed acceptance, in which case
 * the breach is the only thing wrong. The badge says exactly that, and the card
 * must never claim it falsely: it shows only when the card is blocked AND its
 * acceptance exit code is exactly 0. A red exit, or a verification that never
 * ran (`verify_exit == null`), shows no badge.
 */
import type { Task } from './api/client'

export function acceptancePassed(task: Pick<Task, 'status' | 'verify_exit'>): boolean {
  return task.status === 'blocked' && task.verify_exit === 0
}

/**
 * The lane (taskgroup) a card's task ran in. A task row's `project` column
 * stores the *lane* id, not the owning project id -- the registry maps lane ->
 * project for the row a card is drawn under. The card annotates this so a card
 * that sits under a project row can still name the lane it came from, without
 * adding a column or a fetch: it is the one field the row already carries.
 */
export function laneLabel(task: Pick<Task, 'project'>): string {
  return task.project
}
