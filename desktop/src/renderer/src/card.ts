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
