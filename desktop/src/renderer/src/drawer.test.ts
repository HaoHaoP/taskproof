/**
 * The drawer's retry rule, pinned without a DOM.
 *
 * The real failure -- a mount that threw leaves the component alive but with no
 * element in the document, and nothing ever mounts it again -- cannot be
 * reproduced in the node test environment. What can be pinned is the decision:
 * retry exactly while the drawer is open, missing, and has attempts left.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import {
  DRAWER_MOUNT_RETRIES,
  drawerMountKey,
  mandateSummary,
  shouldRetryDrawerMount
} from './drawer'

const drawerSfc = readFileSync(new URL('./components/TaskDrawer.vue', import.meta.url), 'utf-8')

describe('shouldRetryDrawerMount', () => {
  it('does not retry while the drawer is closed', () => {
    expect(shouldRetryDrawerMount({ open: false, mounted: false, attempt: 0 })).toBe(false)
  })

  it('does not retry once the drawer is actually in the document', () => {
    expect(shouldRetryDrawerMount({ open: true, mounted: true, attempt: 0 })).toBe(false)
  })

  it('retries an open, unmounted drawer for the first three attempts', () => {
    for (const attempt of [0, 1, 2]) {
      expect(shouldRetryDrawerMount({ open: true, mounted: false, attempt })).toBe(true)
    }
  })

  it('stops retrying at the cap so a never-mounting drawer cannot spin forever', () => {
    expect(shouldRetryDrawerMount({ open: true, mounted: false, attempt: DRAWER_MOUNT_RETRIES })).toBe(
      false
    )
  })
})

describe('drawerMountKey', () => {
  it('names the key by attempt so only a retry changes it', () => {
    expect(drawerMountKey(0)).toBe('drawer-0')
    expect(drawerMountKey(1)).toBe('drawer-1')
    expect(drawerMountKey(2)).toMatch(/^drawer-\d+$/)
    expect(drawerMountKey(0)).not.toBe(drawerMountKey(1))
  })
})

describe('the dispatch mandate summary', () => {
  const raw = JSON.stringify({
    card_sha256: 'abc',
    lane: 'alpha-core',
    branch: 'feat/card-102',
    verify: 'npm test',
    verify_kind: 'check',
    forbidden_paths: ['dist/'],
    adapter: 'codex',
    model: null,
    reasoning: null,
    timeout: 600,
    idle_timeout: 0,
    issued_at: '2026-11-05T10:00:00+08:00'
  })

  it('renders nothing for tasks written before mandates existed', () => {
    expect(mandateSummary(undefined)).toBeNull()
    expect(mandateSummary(null)).toBeNull()
    expect(drawerSfc).toMatch(/<section v-if="mandate" class="sec mandate">/)
  })

  it('projects only lane, branch and acceptance from the mandate JSON', () => {
    expect(mandateSummary(raw, [{ event: 'started' }])).toEqual({
      lane: 'alpha-core',
      branch: 'feat/card-102',
      verify: 'npm test',
      drifted: false
    })
    expect(mandateSummary(raw, [], 'npm test')?.drifted).toBe(false)
    expect(mandateSummary(raw, [], 'npm run build')?.drifted).toBe(true)
    expect(drawerSfc).toContain("t('drawer.mandate.lane')")
    expect(drawerSfc).toContain("t('drawer.mandate.branch')")
    expect(drawerSfc).toContain("t('drawer.mandate.verify')")
    expect(drawerSfc).not.toMatch(/\{\{\s*task\.mandate\s*\}\}/)
  })

  it('shows the drift warning when the ledger recorded a mandate drift', () => {
    const summary = mandateSummary(raw, [
      { event: 'mandate_drift' },
      { event: 'done' }
    ])
    expect(summary?.drifted).toBe(true)
    expect(drawerSfc).toMatch(/v-if="mandate\.drifted" class="mandate-drift"/)
    expect(drawerSfc).toContain("t('drawer.mandate.driftedNotice')")
  })

  it('treats malformed legacy JSON as absent', () => {
    expect(mandateSummary('{not-json')).toBeNull()
    expect(mandateSummary('[]')).toBeNull()
  })
})
