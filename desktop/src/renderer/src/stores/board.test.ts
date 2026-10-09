/**
 * The store's own rules -- the reasoning the UI depends on but that is not tied
 * to a particular view.
 *
 * The board's project selection lives in the address bar now (the matrix's
 * multi-select), so the store no longer keeps a visibility map; what is left
 * here is the pump: switching polling off must actually stop it rather than
 * merely relabelling it, and a launch that is merely slow must not be reported
 * as offline.
 *
 * No sockets: the local API is stubbed to fail, which is also the state the app
 * has to survive on its own start-up.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useBoardStore } from './board'

describe('polling and start-up', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    ;(globalThis as unknown as { window: unknown }).window = { tp: undefined }
    ;(globalThis as unknown as { location: unknown }).location = { search: '' }
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('no local service in this test')))
    )
    vi.useFakeTimers()
  })

  afterEach(() => {
    useBoardStore().stop()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('turning polling off stops the pump, and on restarts it', () => {
    const store = useBoardStore()
    store.setPoll('2s')
    expect(store.polling).toBe(true)
    store.setPoll('off')
    expect(store.polling).toBe(false)
    expect(store.poll).toBe('off')
    store.setPoll('2s')
    expect(store.polling).toBe(true)
  })

  it('the blank state is not shown while the service is merely starting', () => {
    // `connected` starts false; claiming "offline" before anything has failed
    // would flash a full-page error on every launch.
    const store = useBoardStore()
    expect(store.connected).toBe(false)
    expect(store.lastError).toBeNull()
  })
})
