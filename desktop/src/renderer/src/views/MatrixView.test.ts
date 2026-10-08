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
  it('draws exactly as many status tracks as the contract declares', () => {
    // The comment above `.grid` warns that the track count must equal
    // COLUMNS.length. This is the assertion that keeps the two in step: one
    // fixed lane track plus one `repeat(n, ...)` block for the status columns.
    const tracks = rule('.grid')['grid-template-columns'] ?? ''
    const repeat = /repeat\(\s*(\d+)\s*,/.exec(tracks)
    expect(repeat, `grid-template-columns should use repeat(): "${tracks}"`).toBeTruthy()
    expect(Number(repeat?.[1])).toBe(COLUMNS.length)
  })
})
