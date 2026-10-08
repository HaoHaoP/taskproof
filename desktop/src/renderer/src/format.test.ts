import { describe, expect, it } from 'vitest'
import { duration, payloadLine, shortTime } from './format'

describe('duration', () => {
  it('formats the way the prototype does', () => {
    expect(duration('2026-10-08T10:00:00+08:00', '2026-10-08T10:30:00+08:00')).toBe('30m00s')
    expect(duration('2026-10-08T10:26:00+08:00', '2026-10-08T10:26:48+08:00')).toBe('0m48s')
  })

  it('shows a dash rather than a wrong number when there is no start', () => {
    expect(duration(null, null)).toBe('—')
    expect(duration('not a date', '2026-10-08T10:00:00+08:00')).toBe('—')
  })
})

describe('shortTime', () => {
  it('takes the clock part out of an ISO timestamp', () => {
    expect(shortTime('2026-10-08T10:33:10+08:00')).toBe('10:33:10')
  })

  it('passes through what it cannot parse instead of hiding it', () => {
    expect(shortTime('whenever')).toBe('whenever')
    expect(shortTime(null)).toBe('—')
  })
})

describe('payloadLine', () => {
  it('renders an unrecognised payload key instead of dropping it', () => {
    // A new field arriving from the Python side must become visible, not vanish.
    expect(payloadLine({ exit: 75, group: 'svc' })).toBe('exit 75 · group svc')
    expect(payloadLine({ something_new: 'x' })).toContain('something_new')
  })

  it('summarises collections and objects', () => {
    expect(payloadLine({ files: ['a', 'b', 'c'] })).toBe('files 3')
    expect(payloadLine({ nested: { a: 1 } })).toBe('nested {...}')
  })

  it('is empty for nothing', () => {
    expect(payloadLine(null)).toBe('')
    expect(payloadLine({})).toBe('')
  })
})
