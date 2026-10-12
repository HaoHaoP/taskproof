/**
 * The drawer's retry rule, pinned without a DOM.
 *
 * The real failure -- a mount that threw leaves the component alive but with no
 * element in the document, and nothing ever mounts it again -- cannot be
 * reproduced in the node test environment. What can be pinned is the decision:
 * retry exactly while the drawer is open, missing, and has attempts left.
 */
import { describe, expect, it } from 'vitest'
import { DRAWER_MOUNT_RETRIES, drawerMountKey, shouldRetryDrawerMount } from './drawer'

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
