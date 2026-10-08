/**
 * The toolbar's rules -- the reasoning the UI depends on.
 *
 * A project nobody has hidden must be visible, hiding must survive a refresh,
 * and switching polling off must actually stop the pump rather than merely
 * relabelling it (an indicator that cannot turn off is decoration).
 *
 * No sockets: the local API is stubbed to fail, which is also the state the app
 * has to survive on its own start-up.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { Project } from '../api/client'
import { useBoardStore } from './board'

const fakeProject = (id: string): Project => ({ id }) as unknown as Project

describe('matrix project filter', () => {
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

  it('shows a project that has no entry in the map', () => {
    // Absent means visible, so a project registered while the app is open shows
    // up without anything having to seed the map first.
    expect(useBoardStore().isVisible('anything')).toBe(true)
  })

  it('remembers a hidden project', () => {
    const store = useBoardStore()
    store.toggleProject('a')
    expect(store.isVisible('a')).toBe(false)
    expect(store.isVisible('b')).toBe(true)
    store.toggleProject('a')
    expect(store.isVisible('a')).toBe(true)
  })

  it('does not drop the previous state when toggling once', () => {
    // The map is replaced rather than mutated, so a toggle must carry the rest
    // of the entries over. Losing them would silently un-hide every other lane.
    const store = useBoardStore()
    store.toggleProject('a')
    store.toggleProject('b')
    expect(store.isVisible('a')).toBe(false)
    expect(store.isVisible('b')).toBe(false)
    store.toggleProject('b')
    expect(store.isVisible('b')).toBe(true)
    expect(store.isVisible('a')).toBe(false)
  })

  it('select all / none applies to the projects in the registry', () => {
    const store = useBoardStore()
    store.projects = [fakeProject('a'), fakeProject('b')]
    store.selectAllProjects(false)
    expect(store.isVisible('a')).toBe(false)
    expect(store.isVisible('b')).toBe(false)
    store.selectAllProjects(true)
    expect(store.isVisible('a')).toBe(true)
    expect(store.isVisible('b')).toBe(true)
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
