/**
 * The empty-state regression: an app with nothing registered must still let the
 * user reach the page that registers the first project.
 *
 * The old shell was a full-page `v-if="blank"` with the nav in a `v-else`, so an
 * empty registry removed the nav and the projects page along with the matrix
 * body -- a dead loop, because registering a project is the only way out and
 * that lives behind the projects page. These tests pin the two halves of the
 * fix: the decision logic (only the matrix body ever gives way) and the shell
 * markup (the nav is not gated by the placeholder).
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { shellPlaceholder } from './shell'

const base = { connected: true, projectCount: 0, lastError: null, routeName: 'matrix' }

describe('shellPlaceholder', () => {
  it('shows the empty copy on the matrix when nothing is registered', () => {
    expect(shellPlaceholder(base)).toBe('empty')
  })

  it('leaves the matrix alone once a project exists', () => {
    expect(shellPlaceholder({ ...base, projectCount: 1 })).toBeNull()
  })

  it('shows the offline placeholder on the matrix when the service is unreachable', () => {
    expect(shellPlaceholder({ ...base, connected: false, lastError: 'boom' })).toBe('offline')
  })

  it('does not claim offline while the service is merely still starting', () => {
    // No error yet: a slow launch is not a failure, so the matrix shows nothing.
    expect(shellPlaceholder({ ...base, connected: false, lastError: null })).toBeNull()
  })

  // The dead loop itself: an empty (or offline) registry must never cover a view
  // that is reachable from the nav, or there is no way out.
  for (const routeName of ['projects', 'tasks', 'settings']) {
    it(`never covers the ${routeName} page, empty or offline`, () => {
      expect(shellPlaceholder({ ...base, routeName })).toBeNull()
      expect(shellPlaceholder({ ...base, connected: false, lastError: 'boom', routeName })).toBeNull()
    })
  }
})

const app = readFileSync(new URL('./App.vue', import.meta.url), 'utf-8')

describe('App shell markup', () => {
  it('renders the nav outside the placeholder gate', () => {
    // The regression was `<div v-else class="shell">`: the placeholder removed
    // the shell, and with it the nav. The shell must not be conditional.
    expect(app).not.toMatch(/v-else[^>]*class="shell"/)
    expect(app).not.toMatch(/v-if="blank"[^>]*class="shell"/)

    const navTag = app.match(/<nav\b[^>]*>/)?.[0] ?? ''
    expect(navTag).toContain('class="nav"')
    // Only the rail may hide the nav; the placeholder must not gate it.
    expect(navTag).not.toContain('v-if')
  })

  it('nests the placeholder inside the content area, not around the shell', () => {
    const mainStart = app.indexOf('<main class="content">')
    const blankStart = app.indexOf('class="blank"')
    const mainEnd = app.indexOf('</main>')
    expect(mainStart).toBeGreaterThan(-1)
    expect(mainEnd).toBeGreaterThan(mainStart)
    expect(blankStart).toBeGreaterThan(mainStart)
    expect(blankStart).toBeLessThan(mainEnd)
  })
})
