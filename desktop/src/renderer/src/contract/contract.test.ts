import { describe, expect, it } from 'vitest'
import {
  ABNORMAL,
  COLUMNS,
  STATUS_IDS,
  columnFor,
  isKnownStatus,
  metaFor,
  unknownStatuses
} from './index'

describe('the status contract', () => {
  it('covers every status the generated contract declares', () => {
    // 8 lifecycle states in Python; if the contract gains one, this fails until
    // the presentation catches up.
    expect(STATUS_IDS).toEqual([
      'queued',
      'running',
      'verifying',
      'done',
      'failed',
      'blocked',
      'timeout',
      'cancelled'
    ])
  })

  it('gives every declared status its own mark', () => {
    const glyphs = STATUS_IDS.map((id) => metaFor(id).glyph)
    expect(new Set(glyphs).size).toBe(glyphs.length)
    expect(glyphs).not.toContain('?')
  })

  it('places every declared status in exactly one column', () => {
    for (const id of STATUS_IDS) {
      const hits = COLUMNS.filter((column) => column.members.includes(id))
      expect(hits.length, `${id} must sit in exactly one column`).toBe(1)
    }
  })

  it('collects exactly the abnormal terminal states in the last column', () => {
    expect(COLUMNS[COLUMNS.length - 1].key).toBe('abnormal')
    expect([...COLUMNS[COLUMNS.length - 1].members].sort()).toEqual([...ABNORMAL].sort())
    // and nothing else hides in there
    expect(ABNORMAL).not.toContain('done')
    expect(ABNORMAL).not.toContain('queued')
    expect(ABNORMAL).not.toContain('running')
    expect(ABNORMAL).not.toContain('verifying')
  })

  it('has six columns, with cancellation split out of the failure column', () => {
    // The board's column count and order are load-bearing: `.grid` hands the
    // same count to `grid-template-columns`, so a mismatch silently interleaves
    // every lane. Cancellation is an operator action, not a defect, so it sits
    // in its own column between done and abnormal.
    expect(COLUMNS).toHaveLength(6)
    expect(COLUMNS.map((column) => column.key)).toEqual([
      'queued',
      'running',
      'verifying',
      'done',
      'cancelled',
      'abnormal'
    ])
    const cancelled = COLUMNS.find((column) => column.key === 'cancelled')
    expect(cancelled?.members).toEqual(['cancelled'])
    expect(ABNORMAL).not.toContain('cancelled')
  })
})

describe('never hide a status', () => {
  it('renders a status the contract does not declare', () => {
    // The failure this guards against: a new Python lifecycle state that the
    // frontend silently drops, so a task vanishes from the board.
    const meta = metaFor('reticulating')
    expect(meta.id).toBe('reticulating')
    expect(meta.glyph).toBe('?')
    expect(meta.tone).toBe('unknown')
  })

  it('still gives an unknown status a column to live in', () => {
    expect(columnFor('reticulating').key).toBe('abnormal')
  })

  it('flags unknown words so the drift can be surfaced', () => {
    expect(unknownStatuses(['done', 'reticulating', 'done', 'splines'])).toEqual([
      'reticulating',
      'splines'
    ])
    expect(isKnownStatus('done')).toBe(true)
    expect(isKnownStatus('reticulating')).toBe(false)
  })
})
