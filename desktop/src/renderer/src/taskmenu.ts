/**
 * The card menu, as data.
 *
 * A card's actions are a function of its status, and nothing else:
 *  - queued: dispatch now (the manual entry that jumps one card out of its
 *    wave) + delete (disabled -- delete is terminal-only),
 *  - running / verifying: stop (delete disabled -- stop it first),
 *  - terminal: run again + delete.
 *
 * Keeping this a pure function means "which items does this card offer" is
 * testable without a DOM, and the SFC only maps it to markup.
 */
import type { Task } from './api/client'
import { isTerminal } from './contract'

/** The four console actions a card can offer. */
export type TaskAction = 'advance' | 'stop' | 'delete' | 'rerun'

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
  if (status === 'queued') {
    return [
      { action: 'advance', label: 'task.advance' },
      // The backend refuses a non-terminal delete (409); show it, but grey it
      // so the menu still names the action without promising it.
      { action: 'delete', label: 'task.delete', danger: true, disabled: true }
    ]
  }
  if (status === 'running' || status === 'verifying') {
    return [
      { action: 'stop', label: 'task.stop' },
      { action: 'delete', label: 'task.delete', danger: true, disabled: true }
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

/**
 * Assign each queued task a wave index, so equal `queue_seq` reads as one wave.
 *
 * Distinct seqs are numbered in ascending order (wave 0 is the head); every
 * task with the same seq shares that number, and rows with no seq collect in a
 * final bucket. The index -- not the raw seq -- is what the card colours by, so
 * the palette stays small no matter how large the numbers get.
 */
export function queueWaves(tasks: readonly Task[]): Map<string, number> {
  const seqs = [...new Set(tasks.map((task) => task.queue_seq).filter((s): s is number => s != null))]
  seqs.sort((a, b) => a - b)
  const bySeq = new Map<number, number>()
  seqs.forEach((seq, index) => bySeq.set(seq, index))
  const noSeq = seqs.length
  const waves = new Map<string, number>()
  for (const task of tasks) {
    waves.set(task.id, task.queue_seq == null ? noSeq : (bySeq.get(task.queue_seq) ?? noSeq))
  }
  return waves
}
