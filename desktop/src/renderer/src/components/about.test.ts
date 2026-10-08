/**
 * The About sheet's worth-pinning logic, without a browser.
 *
 * Three things the card calls out are decided here: the CLI version cell falls
 * back to an em dash when there is no version (no hard dependency on the CLI),
 * the diagnostic text is a whitelist that can never carry the write token, and
 * the four data paths track the two real inputs (workspace + userData). The
 * sheet's own markup is pinned by reading the SFC, so a later edit cannot drop
 * the card-15 transition or the 500px sheet frame.
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  EM_DASH,
  aboutPaths,
  buildDiagnostics,
  cliVersionLabel,
  runtimeLabel,
  type DiagnosticsInput
} from './about'

describe('cliVersionLabel', () => {
  it('shows the parsed version when the CLI answered', () => {
    expect(cliVersionLabel('0.0.1')).toBe('0.0.1')
  })

  it('falls back to an em dash when the CLI is missing or unparsable', () => {
    // The card's rule: no CLI installed must not error, blank the cell, or
    // invent a number.
    expect(cliVersionLabel(null)).toBe(EM_DASH)
    expect(cliVersionLabel(undefined)).toBe(EM_DASH)
    expect(cliVersionLabel('')).toBe(EM_DASH)
  })
})

describe('aboutPaths', () => {
  it('derives the registry, store and this month\'s log from the workspace', () => {
    const paths = aboutPaths('/tmp/tp-ws', '/tmp/userData', new Date(2026, 9, 8))
    expect(paths).toEqual({
      userData: '/tmp/userData',
      registry: '/tmp/tp-ws/projects.toml',
      database: '/tmp/tp-ws/taskproof.db',
      events: '/tmp/tp-ws/events-2026-10.jsonl'
    })
  })

  it('trims a trailing slash so the join never doubles up', () => {
    expect(aboutPaths('/tmp/tp-ws/', '/tmp/userData', new Date(2026, 0, 1)).registry).toBe(
      '/tmp/tp-ws/projects.toml'
    )
  })

  it('shows an em dash when a path is unknown rather than fabricating one', () => {
    const paths = aboutPaths('', '')
    expect(paths.userData).toBe(EM_DASH)
    expect(paths.registry).toBe(EM_DASH)
    expect(paths.database).toBe(EM_DASH)
    expect(paths.events).toBe(EM_DASH)
  })
})

describe('runtimeLabel', () => {
  it('names all three bundled engines with their versions', () => {
    expect(runtimeLabel({ electron: '39.0.0', chrome: '142.0.0', node: '22.0.0' })).toBe(
      'Electron 39.0.0 · Chromium 142.0.0 · Node 22.0.0'
    )
  })
})

describe('buildDiagnostics', () => {
  const base: DiagnosticsInput = {
    version: '0.1.0',
    cliVersion: '0.0.1',
    runtime: { electron: '39.8.10', chrome: '142.0.0', node: '22.20.0' },
    workspace: '/tmp/tp-ws',
    service: { state: 'ready', port: 51234 },
    paths: {
      userData: '/tmp/userData',
      registry: '/tmp/tp-ws/projects.toml',
      database: '/tmp/tp-ws/taskproof.db',
      events: '/tmp/tp-ws/events-2026-10.jsonl'
    }
  }

  it('carries the version trio, the workspace, the service and all four paths', () => {
    const text = buildDiagnostics(base)
    expect(text).toContain('App: 0.1.0')
    expect(text).toContain('CLI: 0.0.1')
    expect(text).toContain('Electron 39.8.10 · Chromium 142.0.0 · Node 22.20.0')
    expect(text).toContain('workspace: /tmp/tp-ws')
    expect(text).toContain('service: ready :51234')
    expect(text).toContain('registry: /tmp/tp-ws/projects.toml')
    expect(text).toContain('database: /tmp/tp-ws/taskproof.db')
    expect(text).toContain('events: /tmp/tp-ws/events-2026-10.jsonl')
  })

  it('shows the CLI fallback, not a blank line, when there is no version', () => {
    expect(buildDiagnostics({ ...base, cliVersion: null })).toContain(`CLI: ${EM_DASH}`)
  })

  // The card's hard rule: a pasted bug report must never carry the write token.
  it('never emits a write token, even when one is present on the input', () => {
    const withSecret = {
      ...base,
      token: 'SUPER-SECRET-WRITE-TOKEN',
      writeToken: 'SUPER-SECRET-WRITE-TOKEN'
    } as DiagnosticsInput
    const text = buildDiagnostics(withSecret)
    expect(text).not.toContain('SUPER-SECRET-WRITE-TOKEN')
    expect(text.toLowerCase()).not.toContain('token')
  })
})

const dialog = readFileSync(new URL('./AboutDialog.vue', import.meta.url), 'utf-8')

describe('AboutDialog markup', () => {
  const dialogTag = dialog.match(/<el-dialog\b[^>]*>/)?.[0] ?? ''

  it('reuses the sheet frame at width 500 (card 15 transition, not a bypass)', () => {
    expect(dialogTag).toContain('class="sheet"')
    expect(dialogTag).toContain('width="500"')
    expect(dialogTag).toContain(':transition="SHEET_TRANSITION"')
  })

  it('renders the product title, the icon and the CLI copy path', () => {
    expect(dialog).toContain('Taskproof · 调度台')
    expect(dialog).toContain('build/icon.png')
    expect(dialog).toContain('copyText(')
    expect(dialog).toContain('buildDiagnostics(')
  })
})
