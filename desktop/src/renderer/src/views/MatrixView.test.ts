/**
 * The matrix freezes its header row and its project lane with `position:
 * sticky`. A frozen cell only reads as frozen while its own background is
 * fully opaque -- a translucent one lets the rows scrolling underneath bleed
 * through it, which is the exact defect TP-card17 reported. These tests pin
 * the invariant that every sticky cell paints an opaque background, and that
 * the header/lane intersection (`.hd.corner`) is frozen on BOTH axes above
 * both of them.
 *
 * It reads the stylesheet text plus tokens.css rather than a live layout, so
 * it fails the moment a sticky rule loses its background or starts pointing at
 * a translucent token such as `--side`, with no browser in the loop.
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { compileTemplate, parse } from 'vue/compiler-sfc'
import { COLUMNS } from '../contract'

const view = readFileSync(new URL('./MatrixView.vue', import.meta.url), 'utf-8')
const tokens = readFileSync(new URL('../assets/tokens.css', import.meta.url), 'utf-8')

type Rule = { selector: string; body: string }
type Decls = Record<string, string>

function parseRules(css: string): Rule[] {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const rules: Rule[] = []
  const re = /([^{}]+)\{([^{}]*)\}/g
  let match: RegExpExecArray | null
  while ((match = re.exec(clean))) {
    const selector = match[1].trim().replace(/\s+/g, ' ')
    if (selector.startsWith('@')) continue
    rules.push({ selector, body: match[2] })
  }
  return rules
}

function declarations(body: string): Decls {
  const out: Decls = {}
  for (const part of body.split(';')) {
    const colon = part.indexOf(':')
    if (colon < 0) continue
    out[part.slice(0, colon).trim()] = part.slice(colon + 1).trim()
  }
  return out
}

/** Alpha channel of a colour, or null when the value cannot be resolved. */
function alpha(value: string, vars: Decls, seen = new Set<string>()): number | null {
  const text = value.trim()
  const variable = text.match(/^var\(\s*(--[\w-]+)\s*(?:,(.*))?\)$/s)
  if (variable) {
    const name = variable[1]
    if (vars[name] && !seen.has(name)) {
      return alpha(vars[name], vars, new Set([...seen, name]))
    }
    return variable[2] ? alpha(variable[2], vars, seen) : null
  }
  const lower = text.toLowerCase()
  if (lower === 'transparent') return 0
  if (lower.startsWith('#')) {
    const hex = lower.slice(1)
    if (hex.length === 3 || hex.length === 6) return 1
    if (hex.length === 4) return parseInt(hex[3] + hex[3], 16) / 255
    if (hex.length === 8) return parseInt(hex.slice(6), 16) / 255
    return null
  }
  const rgb = lower.match(
    /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/
  )
  if (rgb) {
    if (!rgb[4]) return 1
    return rgb[4].endsWith('%') ? parseFloat(rgb[4]) / 100 : parseFloat(rgb[4])
  }
  return null
}

const tokenRules = parseRules(tokens)
const themes: Array<[string, Decls]> = [
  ['dark', declarations(tokenRules.find((r) => r.selector === ':root')?.body ?? '')],
  ['light', declarations(tokenRules.find((r) => r.selector.startsWith("html[data-theme='light']"))?.body ?? '')]
]

const styleRules = parseRules(view.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1] ?? '')

function rule(selector: string): Decls {
  const found = styleRules.find((r) => r.selector === selector)
  expect(found, `no stylesheet rule for ${selector}`).toBeTruthy()
  return declarations(found?.body ?? '')
}

describe('matrix sticky cells', () => {
  const sticky = styleRules
    .map((r) => ({ selector: r.selector, decls: declarations(r.body) }))
    .filter((r) => r.decls['position'] === 'sticky')

  it('freezes the header row, the project lane and the corner', () => {
    const selectors = sticky.map((r) => r.selector)
    expect(selectors).toContain('.hd')
    expect(selectors).toContain('.lane')
    expect(selectors).toContain('.hd.corner')
  })

  it('gives every sticky cell an opaque background in both themes', () => {
    expect(sticky.length).toBeGreaterThanOrEqual(3)
    // The zebra rule paints the alternating sticky header cells too, so it has
    // to stay opaque as well even though it is not itself sticky.
    const cells = [...sticky, { selector: '.zcol', decls: rule('.zcol') }]
    for (const { selector, decls } of cells) {
      const background = decls['background'] ?? decls['background-color']
      expect(background, `${selector} paints no background`).toBeTruthy()
      for (const [theme, vars] of themes) {
        const value = alpha(background ?? '', vars)
        expect(value, `${selector} background "${background}" unresolved in ${theme}`).not.toBeNull()
        expect(value, `${selector} background "${background}" is not opaque in ${theme}`).toBe(1)
      }
    }
  })

  it('freezes the corner on both axes, above the header and the lane', () => {
    const corner = rule('.hd.corner')
    const header = rule('.hd')
    const lane = rule('.lane')

    expect(header['position']).toBe('sticky')
    expect(header['top']).toBe('0')
    expect(lane['position']).toBe('sticky')
    expect(lane['left']).toBe('0')

    expect(corner['position']).toBe('sticky')
    expect(corner['top']).toBe('0')
    expect(corner['left']).toBe('0')

    const z = (d: Decls): number => Number(d['z-index'])
    expect(z(corner)).toBeGreaterThan(z(header))
    expect(z(corner)).toBeGreaterThan(z(lane))
  })

  it('renders the frozen corner and the zebra column headers', () => {
    expect(view).toMatch(/class="hd corner"/)
    expect(view).toMatch(/zcol: index % 2 === 1/)
  })
})

describe('matrix grid columns', () => {
  it('writes the track count from the visible lanes, not a literal', () => {
    // The grid no longer pins a repeat count in CSS. It binds
    // grid-template-columns from `gridTracks(lanes.length)`, so the track count
    // rises and falls with the show/hide switches -- 列数 = 可见列数. A literal
    // that silently disagrees with the header/cell loop is the defect the old
    // comment warned about; the fix is to derive it, not to re-pin it.
    expect(view).toMatch(/:style="gridStyle"/)
    expect(view).toMatch(/gridTemplateColumns: gridTracks\(lanes\.value\.length\)/)
    expect(rule('.grid')['grid-template-columns']).toBeUndefined()
  })

  it('feeds the header row and every cell from the one visible-columns list', () => {
    // Both loops iterate `lanes` -- the same computed -- so header order and
    // member assignment cannot drift apart. This is the structural half of
    // "never cross a lane"; the numbers are checked in a real window.
    const loops = view.match(/v-for="\(column, index\) in [^"]+"/g) ?? []
    expect(loops).toHaveLength(2)
    for (const loop of loops) expect(loop).toContain('in lanes')
    expect(view).not.toMatch(/in COLUMNS/)
    expect(view).toMatch(/data-status="column\.key"/)
  })

  it('labels each header through columnLabelKey, so blocked reads "Needs review"', () => {
    // The blocked lane names the operator's job, not the status word. The header
    // (and its hide switch's name) read the label through `columnLabelKey`, and
    // the raw `status.<key>` template is gone.
    expect(view).toMatch(/t\(columnLabelKey\(column\.key\)\)/)
    expect(view).not.toMatch(/status\.\$\{column\.key\}/)
  })


  it('puts a hide switch in every column header, not in the board row', () => {
    // The switch lives in the header it hides: "which column" is the header
    // that was clicked, with no second menu and no second project control.
    expect(view).toMatch(/class="lane-hide"/)
    expect(view).toMatch(/@click="hideLane\(column\.key\)"/)
  })

  it('puts one cap chip and dropdown in every column header, including empty columns', () => {
    // The header loop is the same `lanes` loop as the cells; the chip and its
    // pure decisions are inside it with no `v-if`, so an empty column still
    // gets the same control. COLUMNS is six, so that is all six by default.
    expect(COLUMNS).toHaveLength(6)
    expect(view).not.toMatch(/laneColumn/)
    expect(view).not.toMatch(/gridColumn:/)
    const headerStart = view.indexOf('v-for="(column, index) in lanes"')
    const headerEnd = view.indexOf('<template v-for="group in projects"', headerStart)
    const headerMarkup = view.slice(headerStart, headerEnd)
    expect(headerMarkup).toContain('class="cap-chip"')
    expect(headerMarkup).toContain('capChips[column.key]')
    expect(headerMarkup).toContain('capMenus[column.key]')
    // 调用表达式会被 Vue 当内联语句编译、返回值丢弃；这里必须保留箭头函数转发。
    expect(headerMarkup).toContain('@command="(value) => onCapCommand(column.key, value)"')
    expect(view).toMatch(/:data-col="column\.key"/)
    expect(view).toMatch(/settings\.setColumnCap\(key, command\)/)
  })

  it('compiles the cap command handler to forward the event value', () => {
    // This is the layer that catches the TP-card71 trap: Vue compiles an event
    // call expression as an inline statement, so its return value is discarded.
    const { descriptor, errors: parseErrors } = parse(view, { filename: 'MatrixView.vue' })
    expect(parseErrors).toEqual([])
    expect(descriptor.template, 'MatrixView.vue has no template').not.toBeNull()

    const { code, errors } = compileTemplate({
      source: descriptor.template?.content ?? '',
      filename: 'MatrixView.vue',
      id: 'matrix-view-card71'
    })
    expect(errors).toEqual([])

    const commandBinding = code.match(/onCommand:\s*([^\n]+)/)?.[1]
    expect(commandBinding, 'compiled dropdown has no onCommand binding').toBeTruthy()
    expect(commandBinding).toContain('onCapCommand(column.key')
    expect(commandBinding).not.toMatch(/\bcapCommand\s*\(/)
  })

  it('removes the old fold bar, stepper/editor and first-row count', () => {
    // The chip replaces all three old UI shapes. The first row keeps only the
    // hide switch; no orphan count may compete with the chip's one number.
    expect(view).not.toMatch(/class="cap-step"/)
    expect(view).not.toMatch(/class="cap-val"/)
    expect(view).not.toMatch(/class="cap-input"/)
    expect(view).not.toMatch(/class="fold/)
    expect(view).not.toMatch(/class="n"/)
    expect(styleRules.some((entry) => entry.selector === '.hd .n')).toBe(false)
    expect(styleRules.some((entry) => entry.selector.startsWith('.fold'))).toBe(false)

    // The chip keeps pointer events (it is real), unlike the decorative label /
    // tally -- otherwise a click would fall through to the header.
    expect(rule('.hd .lb, .hd .rt')['pointer-events']).toBe('none')
    expect(rule('.cap-chip')['pointer-events']).toBeUndefined()
  })

  it('covers the seam under each header so nothing scrolls through it', () => {
    // A `top: 0` sticky header only covers its own box. The strip between its
    // lower edge and the first card used to show scrolling cards through it
    // (TP-card40's 穿透). The header now paints an opaque `::after` across
    // that seam, and the matrix's own top padding -- which a sticky header
    // does NOT cover -- is gone so the band pins flush at the scrollport top.
    const matrix = rule('.matrix')
    expect(matrix['padding-top']).toBeUndefined()
    expect(matrix['padding']).toMatch(/^0\b/)

    const hd = rule('.hd')
    expect(hd['position']).toBe('sticky')
    expect(hd['top']).toBe('0')
    // The 10px breathing room above the labels moved into the header itself,
    // under its opaque background.
    expect(Number.parseFloat(hd['padding'] ?? hd['padding-top'] ?? '0')).toBeGreaterThan(0)

    const seam = rule('.hd::after')
    expect(seam['position']).toBe('absolute')
    expect(seam['top']).toBe('100%')
    expect(Number.parseFloat(seam['height'] ?? '0')).toBeGreaterThan(0)
    expect(seam['background']).toBe('inherit')

    // The label/tally decoration must not intercept a hit, so a probe of the
    // band lands on `.hd` (or the chip), never the elements painting the seam.
    // The controls up here stay clickable.
    expect(rule('.hd .lb, .hd .rt')['pointer-events']).toBe('none')
    expect(rule('.hd .rt .lane-hide')['pointer-events']).toBe('auto')
  })
})

describe('matrix capped warning branches (card 45)', () => {
  // The capped warning renders while `store.capped` is true. Inside it the
  // "继续取回" button is keyed off the pure `canGrowBudget` rule: at the cap the
  // click would be a no-op, so the note states the limit and no button appears.

  it('gates the grow button on the shared canGrowBudget rule, not a second cap check', () => {
    expect(view).toMatch(
      /const canGrow = computed\(\(\) => canGrowBudget\(store\.fetchBudget\)\)/
    )
    expect(view).toMatch(/<button\s+v-if="canGrow"\s+type="button"\s+class="grow"/)
    expect(view).toMatch(/@click="store\.growBudget\(\)"/)
    // The view reads the pure rule; it never re-derives the ceiling itself.
    expect(view).not.toMatch(/MAX_BUDGET/)
  })

  it('keeps the reachable branch: the capped note and a live "继续取回"', () => {
    expect(view).toMatch(/v-if="store\.capped" class="cap"/)
    expect(view).toMatch(/t\('board\.capped', \{ n: store\.tasks\.length \}\)/)
    expect(view).toMatch(/t\('board\.continue'\)/)
  })

  it('keeps the at-cap branch: the 已到取回上限 note with no button to click', () => {
    expect(view).toMatch(/<span v-else class="cap-reached">\{\{ t\('board\.capReached'\) \}\}<\/span>/)
    // The fallback is a plain sentence, not a disabled affordance: there is no
    // `disabled` grow button the reader could mistake for a live one.
    expect(view).not.toMatch(/class="grow"[\s\S]{0,40}disabled/)
  })
})

/**
 * TP-card64: the left rail and the matrix rows are one row per *project* (the
 * D2 shape C two-layer model), with the lanes nested inside. An uncollected
 * registry -- every lane its own project, the live shape -- must keep the same
 * row count and names it has today.
 */
describe('the left rail draws one row per project (project granularity)', () => {
  it('reads the grouped view, whose row count is the project count', () => {
    expect(view).toContain('visibleProjects(store.projectGroups, filter.value)')
    expect(view).not.toContain('visibleProjects(store.projects, filter.value)')
    expect(view).toMatch(/v-for="group in projects" :key="group\.id"/)
    // The dropdown and the "all / none / selected N" arithmetic are project ids.
    expect(view).toContain('store.projectGroups.map((group) => group.id)')
    expect(view).toMatch(/v-for="group in store\.projectGroups"/)
  })

  it('shows each project name and its lane count, aliases on a tooltip', () => {
    expect(view).toMatch(/<div class="name" :title="aliasHint\(group\) \|\| undefined">\{\{ group\.id \}\}<\/div>/)
    expect(view).toMatch(/\{\{ laneCount\(group\) \}\} \{\{ t\('rail\.lanes'\) \}\}/)
  })

  it('files a card under its project by the registry lane -> project map', () => {
    expect(view).toMatch(/owningProject\(task, store\.laneProject\) === projectId/)
    expect(view).not.toMatch(/task\.project === projectId/)
    // The view never re-derives the mapping; the store holds it.
    expect(view).toMatch(/store\.laneProject/)
  })

  it('keeps the six-column grid sized by the visible count, not a literal', () => {
    // COLUMNS unchanged at six, and the grid still derives its track count --
    // writing a literal `repeat(6, ...)` would silently strand a wider contract.
    expect(COLUMNS.length).toBe(6)
    expect(view).toContain('gridTracks(lanes.value.length)')
    expect(view).not.toMatch(/repeat\(\s*\d/)
  })
})
