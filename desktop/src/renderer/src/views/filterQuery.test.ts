/**
 * Source-structure pins for card 54's filter-loss fixes plus the immediate file
 * count. These are markup/script invariants that a pure function cannot state,
 * so -- following MatrixView.test.ts's house pattern -- they read the `.vue`
 * text and assert the shape directly, with no DOM.
 *
 * They pin the three ways a filter used to be lost: a bare-path `push` that
 * dropped the query, an `applyFilter` that rebuilt the query from scratch (and
 * so dropped keys it did not own), and the missing dropdown affordances.
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const matrix = readFileSync(new URL('./MatrixView.vue', import.meta.url), 'utf-8')
const tasks = readFileSync(new URL('./TasksView.vue', import.meta.url), 'utf-8')
const drawer = readFileSync(new URL('../components/TaskDrawer.vue', import.meta.url), 'utf-8')
const card = readFileSync(new URL('../components/TaskCard.vue', import.meta.url), 'utf-8')

describe('opening / closing a detail keeps the filter (card 54)', () => {
  it('pushes the matrix detail as a named route carrying the current query', () => {
    expect(matrix).toContain(
      "router.push({ name: 'matrix', params: { taskId: id }, query: route.query })"
    )
    // The old bare path is the defect itself: it cleared the address bar.
    expect(matrix).not.toMatch(/router\.push\(`\/matrix\//)
  })

  it('pushes the tasks detail the same way', () => {
    expect(tasks).toContain(
      "router.push({ name: 'tasks', params: { taskId: id }, query: route.query })"
    )
    expect(tasks).not.toMatch(/router\.push\(`\/tasks\//)
  })

  it('closes the drawer by dropping the taskId while keeping the query', () => {
    // `name` with no `params.taskId` is what closes it; the query (the filter
    // and the tab) rides along untouched.
    expect(drawer).toContain('router.push({ name, query: route.query })')
  })
})

describe('applyFilter keeps query keys it does not own (card 54)', () => {
  it('names the board-owned keys, so `tab` is provably not among them', () => {
    expect(matrix).toContain(
      "const BOARD_KEYS = new Set(['range', 'projects', 'project', 'done', 'open', HIDE_KEY])"
    )
  })

  it('carries non-board keys over, then merges the produced board query', () => {
    expect(matrix).toContain('if (!BOARD_KEYS.has(key) && value !== undefined) query[key] = value')
    expect(matrix).toContain('Object.assign(query, produced)')
    // The old rebuild-from-boardQuery is gone: that is what dropped `tab`.
    expect(matrix).not.toContain(
      'query: Object.fromEntries(new URLSearchParams(boardQuery(next)))'
    )
  })
})

describe('the project dropdown gains all / clear / search (card 54)', () => {
  const start = matrix.indexOf('class="sel sel-projects"')
  const projectSelect = matrix.slice(start, matrix.indexOf('</el-select>', start))

  it('is a filterable multi-select', () => {
    expect(start).toBeGreaterThanOrEqual(0)
    expect(projectSelect).toContain('filterable')
  })

  it('puts an all/none header inside the dropdown, reusing rail.all / rail.none', () => {
    expect(projectSelect).toContain('<template #header>')
    expect(projectSelect).toContain("t('rail.all')")
    expect(projectSelect).toContain("t('rail.none')")
  })

  it('stops both clicks so the dropdown stays open, and disables a no-op', () => {
    expect(projectSelect).toContain('@click.stop.prevent="selectAllProjects"')
    expect(projectSelect).toContain('@click.stop.prevent="clearProjects"')
    expect(projectSelect).toContain(':disabled="allProjectsSelected"')
    expect(projectSelect).toContain(':disabled="noProjectsSelected"')
  })

  it('means "all" = null (default) and "clear" = explicit empty', () => {
    expect(matrix).toMatch(
      /function selectAllProjects\(\): void \{\s*applyFilter\(\{ projects: null \}\)/
    )
    expect(matrix).toMatch(/function clearProjects\(\): void \{\s*applyFilter\(\{ projects: \[\] \}\)/)
    expect(matrix).toContain('const allProjectsSelected = computed(() => filter.value.projects === null)')
    expect(matrix).toContain('filter.value.projects !== null && filter.value.projects.length === 0')
  })

  it('styles the teleported popper under its own class', () => {
    expect(matrix).toContain('.sel-projects-popper .sel-head')
  })
})

describe('the immediate file count (card 54)', () => {
  it('prefers files_changed_live on the card, falling back to the final count', () => {
    expect(card).toContain('task.files_changed_live ?? task.files_changed ?? 0')
  })

  it('prefers files_changed_live in the drawer evidence too', () => {
    expect(drawer).toContain('task.files_changed_live ?? task.files_changed ?? 0')
  })
})

describe('the drawer log tab lives in the URL (card 54)', () => {
  it('selects the log only for exactly `?tab=log`, defaulting to overview', () => {
    expect(drawer).toContain("route.query.tab === 'log' ? 'log' : 'overview'")
  })

  it('is a real tablist of keyboard-operable buttons', () => {
    expect(drawer).toContain('role="tablist"')
    expect(drawer).toContain('role="tab"')
    expect(drawer).toContain("@keydown.enter.prevent=\"go('log')\"")
    expect(drawer).toContain("@keydown.space.prevent=\"go('log')\"")
    expect(drawer).toContain("@keydown.enter.prevent=\"go('overview')\"")
    expect(drawer).toContain("@keydown.space.prevent=\"go('overview')\"")
  })

  it('switches tabs by pushing the new `tab` onto the same task', () => {
    expect(drawer).toContain("query.tab = 'log'")
    expect(drawer).toContain('delete query.tab')
    expect(drawer).toContain('router.push({ name, params: { taskId: id }, query })')
  })
})
