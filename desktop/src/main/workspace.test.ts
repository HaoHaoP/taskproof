/**
 * First-boot workspace bootstrap, pinned.
 *
 * The card's rules that a checklist cannot see:
 *   - a brand-new install gets a real workspace (`projects.toml` included), so
 *     the app is usable the moment it is installed;
 *   - that file is *minimal and honest*: `[defaults]` only, plus a **commented**
 *     `[[project]]` example -- never a seeded project, never sample task data;
 *   - bootstrap is create-only: a hand-edited registry is never clobbered.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { ensureWorkspace, minimalProjectsToml, registryPath } from './workspace'

const tmp = (): string => mkdtempSync(join(tmpdir(), 'tp-ws-'))

describe('minimalProjectsToml', () => {
  it('carries a [defaults] table with a timeout, and leaves concurrency unpinned', () => {
    const toml = minimalProjectsToml()
    expect(toml).toContain('[defaults]')
    expect(toml).toMatch(/^timeout\s*=\s*\d+/m)
    // Pinning concurrency here would defeat the machine-derived default (card42:
    // the value is derived per machine unless the registry says otherwise), so the
    // template only *mentions* the knob.
    expect(toml).toMatch(/^#\s*concurrency/m)
    expect(toml).not.toMatch(/^concurrency\s*=/m)
  })

  it('parses to zero projects: the only [[project]] is commented out', () => {
    const toml = minimalProjectsToml()
    // Every `[[project]]` line is behind a `#`.
    const tableLines = toml.split('\n').filter((l) => l.includes('[[project]]'))
    expect(tableLines.length).toBeGreaterThan(0)
    for (const line of tableLines) expect(line.trimStart().startsWith('#')).toBe(true)
    // No sample *data*: no real project id assignment (the example one is
    // commented), no task table.
    expect(toml).not.toMatch(/^\s*id\s*=/m)
    expect(toml).not.toContain('[[task')
  })
})

describe('ensureWorkspace', () => {
  let dir: string | undefined
  afterEach(() => {
    if (dir) rmSync(dir, { recursive: true, force: true })
    dir = undefined
  })

  it('creates the directory and the registry on first boot', () => {
    dir = tmp()
    const ws = join(dir, 'fresh')
    const result = ensureWorkspace(ws)

    expect(result.createdDir).toBe(true)
    expect(result.wroteRegistry).toBe(true)
    expect(readFileSync(registryPath(ws), 'utf8')).toBe(minimalProjectsToml())
  })

  it('is idempotent and never overwrites an existing registry', () => {
    dir = tmp()
    const ws = join(dir, 'exists')
    ensureWorkspace(ws)
    // A user edits their registry...
    const edited = '# mine\n[defaults]\ntimeout = 60\n'
    writeFileSync(registryPath(ws), edited, 'utf8')
    // ...and a later boot must leave it byte-identical.
    const result = ensureWorkspace(ws)
    expect(result.createdDir).toBe(false)
    expect(result.wroteRegistry).toBe(false)
    expect(readFileSync(registryPath(ws), 'utf8')).toBe(edited)
  })

  it('does not touch tasks or any file other than projects.toml', () => {
    dir = tmp()
    const ws = join(dir, 'only-registry')
    ensureWorkspace(ws)
    expect(readdirSync(ws)).toEqual(['projects.toml'])
  })

  it('drives the injected deps so the branches need no real files', () => {
    const made: string[] = []
    const written: Array<[string, string]> = []
    const result = ensureWorkspace('/virtual/ws', {
      exists: () => false,
      mkdir: (p) => made.push(p),
      write: (p, data) => written.push([p, data])
    })
    expect(result).toEqual({ createdDir: true, wroteRegistry: true })
    expect(made).toEqual(['/virtual/ws'])
    expect(written).toEqual([[registryPath('/virtual/ws'), minimalProjectsToml()]])
  })
})
