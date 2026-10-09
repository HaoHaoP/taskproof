/**
 * The arithmetic and the de-duplication behind the desktop switches, pinned.
 *
 * Two rules that a checklist cannot see but the user can:
 *
 *  - the Dock badge counts failed + blocked + timeout, and never cancelled
 *    (card 21 split cancellation into its own column; it is an operator action,
 *    not a defect);
 *  - a notification fires once per task, on the poll where the row first
 *    appears -- the renderer polls every couple of seconds, so "notify on every
 *    poll" would be a storm.
 */
import { describe, expect, it } from 'vitest'
import {
  DONE,
  NOT_PASSING,
  NotificationTracker,
  notificationBody,
  notPassingCount
} from './desktop'

describe('notPassingCount', () => {
  it('counts failed + blocked + timeout and never cancelled', () => {
    // The card's own example: 2 failed + 1 cancelled -> 2, not 3.
    expect(notPassingCount({ failed: 2, cancelled: 1 })).toBe(2)
    expect(notPassingCount({ blocked: 1, timeout: 2 })).toBe(3)
    expect(notPassingCount({ failed: 2, blocked: 1, timeout: 1, cancelled: 9 })).toBe(4)
  })

  it('reads 0 when there is nothing to pass or the summary is absent', () => {
    expect(notPassingCount({})).toBe(0)
    expect(notPassingCount({ done: 5, running: 3, queued: 1 })).toBe(0)
    expect(notPassingCount(null)).toBe(0)
    expect(notPassingCount(undefined)).toBe(0)
  })

  it('exposes the watched statuses the count and the notifier share', () => {
    expect([...NOT_PASSING]).toEqual(['failed', 'blocked', 'timeout'])
    expect([...DONE]).toEqual(['done'])
  })
})

describe('NotificationTracker', () => {
  it('claims a newly-failed task once, then stays quiet across polls', () => {
    const tracker = new NotificationTracker()
    const failing = [{ id: 't1', status: 'failed' }]

    expect(tracker.claim(failing, NOT_PASSING).map((t) => t.id)).toEqual(['t1'])
    // The same row comes back on the next poll -- no second notification.
    expect(tracker.claim(failing, NOT_PASSING)).toEqual([])
    expect(tracker.claim(failing, NOT_PASSING)).toEqual([])
  })

  it('ignores rows whose status is outside the watched set', () => {
    const tracker = new NotificationTracker()
    expect(tracker.claim([{ id: 'c1', status: 'cancelled' }], NOT_PASSING)).toEqual([])
    // A later done-poll still sees it as unseen because it was never watched.
    expect(tracker.claim([{ id: 'c1', status: 'cancelled' }], DONE)).toEqual([])
  })

  it('tracks fail and done watches together, once per id', () => {
    const tracker = new NotificationTracker()
    const tasks = [
      { id: 'a', status: 'failed' },
      { id: 'b', status: 'done' }
    ]
    expect(tracker.claim(tasks, NOT_PASSING).map((t) => t.id)).toEqual(['a'])
    expect(tracker.claim(tasks, DONE).map((t) => t.id)).toEqual(['b'])
    // Both are now seen; a re-poll notifies nothing.
    expect(tracker.claim(tasks, [...NOT_PASSING, ...DONE])).toEqual([])
  })

  it('skips rows without an id', () => {
    const tracker = new NotificationTracker()
    expect(tracker.claim([{ id: '', status: 'failed' }], NOT_PASSING)).toEqual([])
  })
})

describe('notificationBody', () => {
  it('reads `project · id`, or just the id, and never carries a token', () => {
    expect(notificationBody({ id: 't1', status: 'failed', project: 'proj' })).toBe('proj · t1')
    expect(notificationBody({ id: 't1', status: 'failed' })).toBe('t1')
  })
})
