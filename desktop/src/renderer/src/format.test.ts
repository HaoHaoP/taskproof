/**
 * The drawer's timeline depends on these two, and both have a failure mode that
 * is invisible until it is on screen: a long payload burying the event it
 * belongs to, and a verification that never ran being painted as a failure.
 */
import { describe, expect, it } from 'vitest'
import { eventSummary, isBadEvent, payloadLine } from './format'

describe('eventSummary', () => {
  it('projects the fields that answer "what happened"', () => {
    expect(eventSummary('started', { adapter: 'codex', group: 'taskproof' })).toBe(
      'codex · taskproof'
    )
    expect(eventSummary('adapter', { exit_code: 0, degraded: false })).toBe('exit 0')
    expect(eventSummary('verify', { status: 'PASSED', exit_code: 0 })).toBe('PASSED · exit 0')
    expect(eventSummary('done', { verify: 'PASSED', files_changed: 5 })).toBe('PASSED · 5')
  })

  it('does not paste a whole summary into the timeline', () => {
    // The real `adapter` payload carries the worker's full report -- thousands
    // of characters. It must not reach the timeline.
    const huge = 'x'.repeat(4000)
    const line = eventSummary('adapter', { exit_code: 0, summary: huge })
    expect(line).toBe('exit 0')
    expect(line.length).toBeLessThan(200)
  })

  it('caps an unknown payload instead of printing all of it', () => {
    const line = eventSummary('something-new', { note: 'y'.repeat(500) })
    expect(line.length).toBeLessThanOrEqual(161) // 160 + the ellipsis
    expect(line.endsWith('…')).toBe(true)
  })

  it('keeps an unrecognised event readable rather than dropping it', () => {
    expect(eventSummary('brand_new', { a: 1, b: 'two' })).toBe('a 1 · b two')
  })

  it('names the protected paths a forbidden event reports', () => {
    expect(eventSummary('forbidden', { paths: ['dist/', '.git/'] })).toBe('dist/, .git/')
  })
})

describe('isBadEvent', () => {
  it('flags the failure events', () => {
    for (const name of ['failed', 'forbidden', 'blocked', 'timeout', 'cancelled']) {
      expect(isBadEvent(name, {})).toBe(true)
    }
  })

  it('treats a skipped verification as "did not run", not as a failure', () => {
    expect(isBadEvent('verify', { status: 'SKIPPED' })).toBe(false)
    expect(isBadEvent('verify', { status: 'PASSED' })).toBe(false)
    expect(isBadEvent('verify', { status: 'FAILED' })).toBe(true)
  })

  it('reads the adapter exit code', () => {
    expect(isBadEvent('adapter', { exit_code: 0 })).toBe(false)
    expect(isBadEvent('adapter', { exit_code: 71 })).toBe(true)
  })

  it('does not call an ordinary event bad', () => {
    expect(isBadEvent('started', { adapter: 'codex' })).toBe(false)
    expect(isBadEvent('done', { verify: 'PASSED' })).toBe(false)
  })
})

describe('payloadLine', () => {
  it('still shows a field it has never heard of', () => {
    // How a new Python-side field becomes visible instead of silently ignored.
    expect(payloadLine({ brand_new_field: 'value' })).toBe('brand_new_field value')
  })
})
