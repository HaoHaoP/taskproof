/**
 * The "验收已过 / Acceptance passed" badge is a claim about the *work*, not
 * about the release: a blocked card shows it only when its acceptance exit code
 * is exactly 0. These pin the truth table -- blocked + green shows; blocked with
 * a red exit, blocked with no verification, and any non-blocked card do not.
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { acceptancePassed, laneLabel } from './card'

const cardSfc = readFileSync(new URL('./components/TaskCard.vue', import.meta.url), 'utf-8')

describe('acceptancePassed — the badge never lies', () => {
  it('shows on a blocked card whose acceptance went green', () => {
    expect(acceptancePassed({ status: 'blocked', verify_exit: 0 })).toBe(true)
  })

  it('stays hidden on a blocked card with a red acceptance', () => {
    expect(acceptancePassed({ status: 'blocked', verify_exit: 1 })).toBe(false)
    expect(acceptancePassed({ status: 'blocked', verify_exit: 71 })).toBe(false)
  })

  it('stays hidden when the blocked card was never verified', () => {
    expect(acceptancePassed({ status: 'blocked', verify_exit: null })).toBe(false)
  })

  it('stays hidden on every non-blocked card, even with a green exit', () => {
    for (const status of ['running', 'verifying', 'done', 'failed', 'timeout', 'cancelled']) {
      expect(acceptancePassed({ status, verify_exit: 0 })).toBe(false)
    }
  })

  it('wires the badge into the card title row, gated on the one helper', () => {
    // The card sits the badge in its title row (`line-1`) and drives it from the
    // single `acceptancePassed` helper, so the truth table above is the only
    // place the condition is decided.
    expect(cardSfc).toMatch(/const passBadge = computed\(\(\) => acceptancePassed\(props\.task\)\)/)
    expect(cardSfc).toMatch(/v-if="passBadge" class="stamp good"/)
    expect(cardSfc).toMatch(/t\('card\.acceptancePassed'\)/)
  })
})

/**
 * TP-card64: a card drawn under a *project* row still has to name the lane its
 * task ran in. A task row's `project` column is that lane id; `laneLabel` is the
 * one pure rule for it, so the card body only wires the answer to markup.
 */
describe('laneLabel — the lane the card ran in', () => {
  it('is the task row\'s own project column (the lane id)', () => {
    expect(laneLabel({ project: 'alpha-core' })).toBe('alpha-core')
    // A single-lane project names itself -- the uncollected-registry compat.
    expect(laneLabel({ project: 'solo' })).toBe('solo')
  })

  it('marks the card with a small meta item, reusing the existing meta styling', () => {
    // A small text item (not a new badge), so the card's density and colours
    // are untouched -- it is one more span inside the existing `.meta` row.
    expect(cardSfc).toMatch(/const lane = computed\(\(\) => laneLabel\(props\.task\)\)/)
    expect(cardSfc).toMatch(/<span class="lane" :title="t\('card\.lane'\)">\{\{ lane \}\}<\/span>/)
    // No card-local lane CSS: it inherits `.meta`, so no colour is introduced.
    expect(cardSfc).not.toMatch(/\.lane\s*\{/)
  })
})
