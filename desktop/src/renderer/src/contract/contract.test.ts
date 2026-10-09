import { describe, expect, it } from 'vitest'
import {
  ABNORMAL,
  COLUMNS,
  STATUS_IDS,
  columnFor,
  columnLabelKey,
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
    // `abnormal` is the last column, and it holds only the failure-like
    // verdicts -- never `blocked`, which is a waiting room, not a defect.
    expect(COLUMNS[COLUMNS.length - 1].key).toBe('abnormal')
    expect([...COLUMNS[COLUMNS.length - 1].members].sort()).toEqual([...ABNORMAL].sort())
    expect(ABNORMAL).toEqual(['failed', 'timeout'])
    expect(ABNORMAL).not.toContain('blocked')
    // and nothing else hides in there
    expect(ABNORMAL).not.toContain('done')
    expect(ABNORMAL).not.toContain('queued')
    expect(ABNORMAL).not.toContain('running')
    expect(ABNORMAL).not.toContain('verifying')
  })

  it('has seven columns, with cancellation and blocked each split out', () => {
    // The board's column count and order are load-bearing: `.grid` hands the
    // same count to `grid-template-columns`, so a mismatch silently interleaves
    // every lane. Two terminal states are waiting rooms and get their own
    // column: cancellation (the operator stopped it) and blocked (a boundary
    // breach parked for a human to release). `abnormal` stays last.
    expect(COLUMNS).toHaveLength(7)
    expect(COLUMNS.map((column) => column.key)).toEqual([
      'queued',
      'running',
      'verifying',
      'done',
      'cancelled',
      'blocked',
      'abnormal'
    ])
    const cancelled = COLUMNS.find((column) => column.key === 'cancelled')
    expect(cancelled?.members).toEqual(['cancelled'])
    expect(ABNORMAL).not.toContain('cancelled')

    const blocked = COLUMNS.find((column) => column.key === 'blocked')
    expect(blocked?.members).toEqual(['blocked'])
    expect(ABNORMAL).not.toContain('blocked')
    // the failure column is still the last one
    expect(COLUMNS[COLUMNS.length - 1].key).toBe('abnormal')
  })

  it('labels the blocked lane with its own key, and the rest with the status word', () => {
    // The lane header names the operator's job ("Needs review"), not the status
    // word ("Blocked") -- two purposes, two keys. Every other column reuses the
    // status word.
    expect(columnLabelKey('blocked')).toBe('column.blocked')
    expect(columnLabelKey('queued')).toBe('status.queued')
    expect(columnLabelKey('abnormal')).toBe('status.abnormal')
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
