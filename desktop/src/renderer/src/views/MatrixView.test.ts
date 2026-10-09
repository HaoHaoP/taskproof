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

  it('puts a hide switch in every column header, not in the board row', () => {
    // The switch lives in the header it hides: "which column" is the header
    // that was clicked, with no second menu and no second project control.
    expect(view).toMatch(/class="lane-hide"/)
    expect(view).toMatch(/@click="hideLane\(column\.key\)"/)
  })

  it('rides each fold bar inside its own column header, not a trailing row', () => {
    // The bar used to be a trailing grid row with a hand-written `grid-column`.
    // It now lives in the header it belongs to, so the sticky band carries it
    // and no `grid-column` arithmetic is needed. Both terminal columns still
    // drive the ONE `?done=expanded` toggle -- one flag, no second state.
    expect(view).not.toMatch(/laneColumn/)
    expect(view).not.toMatch(/gridColumn:/)
    expect(view).toMatch(/v-if="foldFor\(column\.key\)\?\.mode === 'expand'"/)
    expect(view).toMatch(/v-else-if="foldFor\(column\.key\)\?\.mode === 'collapse'"/)
    expect(view).toMatch(/@click="applyFilter\(\{ expanded: true \}\)"/)
    expect(view).toMatch(/@click="applyFilter\(\{ expanded: false \}\)"/)
    expect(view).toMatch(/:data-col="column\.key"/)
    expect(rule('.fold')['grid-column']).toBeUndefined()
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
    // band lands on `.hd` (or `.fold`), never the elements painting the seam.
    // The one control up here stays clickable.
    expect(rule('.hd .lb, .hd .rt')['pointer-events']).toBe('none')
    expect(rule('.hd .rt .lane-hide')['pointer-events']).toBe('auto')
  })
})
