/**
 * The card menu is a function of status, and nothing else. These pin the
 * matrix: which actions a card offers in each state, that delete is present
 * but greyed while a row is live, and that an unknown status offers nothing
 * rather than a wrong verb.
 *
 * `waveSlot` is the other half: the wave chip's colour must come from the
 * card's own `queue_seq`, so equal seqs share a slot, the slot never depends on
 * which cards are visible, and it wraps into a fixed palette instead of leaking
 * a second number onto the card.
 */
import { describe, expect, it } from 'vitest'
import { WAVE_SLOTS, menuFor, waveSlot } from './taskmenu'

const TERMINAL = ['done', 'failed', 'timeout', 'cancelled']
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

describe('waveSlot — colour reads the card, not the visible set', () => {
  it('gives equal seqs the same slot', () => {
    expect(waveSlot(5)).toBe(waveSlot(5))
    expect(waveSlot(7)).toBe(waveSlot(7))
  })

  it('is a pure function of the seq alone — a hidden neighbour cannot shift it', () => {
    // The old `queueWaves` numbered distinct seqs by their rank among the
    // visible cards, so filtering the board re-coloured the survivors. The slot
    // now depends on nothing but the seq, so the same card keeps its colour
    // whether or not its neighbours are on the board.
    expect(waveSlot(5)).toBe(5)
    expect(waveSlot(9)).toBe(3)
  })

  it('wraps the raw seq into a fixed palette, so the numbers can grow but the colours cannot', () => {
    expect(waveSlot(WAVE_SLOTS)).toBe(0)
    expect(waveSlot(WAVE_SLOTS + 2)).toBe(2)
    expect(waveSlot(-1)).toBe(WAVE_SLOTS - 1)
    expect(waveSlot(null)).toBe(0)
    expect(waveSlot(undefined)).toBe(0)
  })
})
