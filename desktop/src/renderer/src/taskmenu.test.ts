/**
 * The card menu is a function of status, and nothing else. These pin the
 * matrix: which actions a card offers in each state, that delete is present
 * but greyed while a row is live, and that an unknown status offers nothing
 * rather than a wrong verb.
 */
import { describe, expect, it } from 'vitest'
import { menuFor } from './taskmenu'

const TERMINAL = ['done', 'failed', 'timeout', 'cancelled']
const LIVE = ['running', 'verifying']

function actions(status: string): string[] {
  return menuFor(status).map((item) => item.action)
}

describe('menuFor — items follow the status', () => {
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

  it('offers accept first on a blocked card, then the usual terminal pair', () => {
    // A blocked card is waiting for a human: `accept` is its signature action.
    // It is still terminal, so run again and delete remain available.
    expect(actions('blocked')).toEqual(['accept', 'rerun', 'delete'])
    const accept = menuFor('blocked').find((i) => i.action === 'accept')
    expect(accept?.label).toBe('task.accept')
    expect(accept?.disabled).toBeFalsy()
    expect(accept?.danger).toBeFalsy()
    const del = menuFor('blocked').find((i) => i.action === 'delete')
    expect(del?.danger).toBe(true)
  })

  it('offers nothing for a status it does not know', () => {
    expect(menuFor('warped')).toEqual([])
  })
})
