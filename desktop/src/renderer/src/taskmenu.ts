/**
 * The card menu, as data.
 *
 * A card's actions are a function of its status, and nothing else:
 *  - running / verifying: stop (delete disabled -- stop it first),
 *  - blocked: accept (the human's one-word release of a boundary breach) first,
 *    then the usual terminal pair -- run again + delete,
 *  - every other terminal: run again + delete.
 *
 * Keeping this a pure function means "which items does this card offer" is
 * testable without a DOM, and the SFC only maps it to markup.
 */
import { isTerminal } from './contract'

/** The console actions a card can offer. */
export type TaskAction = 'stop' | 'accept' | 'delete' | 'rerun'

export interface TaskMenuItem {
  action: TaskAction
  /** i18n key for the label. */
  label: string
  /** Rendered in the danger tone (delete). */
  danger?: boolean
  /** Present but greyed; the action is not legal for this status. */
  disabled?: boolean
}

export function menuFor(status: string): TaskMenuItem[] {
  if (status === 'running' || status === 'verifying') {
    return [
      { action: 'stop', label: 'task.stop' },
      { action: 'delete', label: 'task.delete', danger: true, disabled: true }
    ]
  }
  if (status === 'blocked') {
    // A blocked card is terminal, but its signature action is `accept` -- the
    // human's release of the boundary breach (green acceptance -> done, red ->
    // failed). Run again and delete still apply, as on any terminal card.
    return [
      { action: 'accept', label: 'task.accept' },
      { action: 'rerun', label: 'task.rerun' },
      { action: 'delete', label: 'task.delete', danger: true }
    ]
  }
  if (isTerminal(status)) {
    return [
      { action: 'rerun', label: 'task.rerun' },
      { action: 'delete', label: 'task.delete', danger: true }
    ]
  }
  // An unknown status: offer nothing rather than a wrong action. Drift is
  // surfaced elsewhere; a menu is not the place to guess.
  return []
}
