/**
 * The card menu is a function of status, and nothing else. These pin the
 * matrix: which actions a card offers in each state, that delete is present
 * but greyed while a row is live, and that an unknown status offers nothing
 * rather than a wrong verb.
 *
 * `queueWaves` is the other half: equal `queue_seq` must resolve to the same
 * index (one colour, one wave), distinct ones to ascending indices, and rows
 * with no seq to a trailing bucket.
 */
import { describe, expect, it } from 'vitest'
import { menuFor, queueWaves } from './taskmenu'
import type { Task } from './api/client'

const TERMINAL = ['done', 'failed', 'blocked', 'timeout', 'cancelled']
const LIVE = ['running', 'verifying']

function actions(status: string): string[] {
  return menuFor(status).map((item) => item.action)
}

describe('menuFor — items follow the status', () => {
  it('offers dispatch-now for a queued card, with delete greyed', () => {
    expect(actions('queued')).toEqual(['advance', 'delete'])
    expect(menuFor('queued').find((i) => i.action === 'delete')?.disabled).toBe(true)
  })

  it('offers stop while a card is live, with delete greyed', () => {
    for (const status of LIVE) {
      expect(actions(status)).toEqual(['stop', 'delete'])
      expect(menuFor(status).find((i) => i.action === 'delete')?.disabled).toBe(true)
    }
  })

  it('offers run-again and a live delete for every terminal status', () => {
    for (const status of TERMINAL) {
      expect(actions(status)).toEqual(['rerun', 'delete'])
      const del = menuFor(status).find((i) => i.action === 'delete')
      expect(del?.disabled).toBeFalsy()
      expect(del?.danger).toBe(true)
    }
  })

  it('offers nothing for a status it does not know', () => {
    expect(menuFor('warped')).toEqual([])
  })
})

/** A task with only what the wave rules read. */
function task(id: string, queue_seq: number | null): Task {
  return { id, queue_seq } as Task
}

describe('queueWaves — equal seq, one wave', () => {
  it('numbers distinct seqs ascending and shares the index for equal ones', () => {
    const waves = queueWaves([
      task('a', 5),
      task('b', 1),
      task('c', 1),
      task('d', 3)
    ])
    expect(waves.get('b')).toBe(0)
    expect(waves.get('c')).toBe(0) // equal seq -> same wave
    expect(waves.get('d')).toBe(1)
    expect(waves.get('a')).toBe(2)
  })

  it('collects rows with no seq in a trailing bucket', () => {
    const waves = queueWaves([task('a', 1), task('b', null), task('c', 2)])
    expect(waves.get('a')).toBe(0)
    expect(waves.get('c')).toBe(1)
    expect(waves.get('b')).toBe(2)
  })
})
