/**
 * The argv the switches produce, pinned.
 *
 * The launcher used to hard-code `--port 0`, so `portMode` / `port` / `launch`
 * were stored but never obeyed. These cases are the contract the settings page
 * now promises: `auto` means "let the OS pick", `fixed` passes the user's port
 * through unchanged (an occupied port must fail loudly, not silently switch),
 * and `manual` means the app must not spawn the child on open.
 */
import { describe, expect, it } from 'vitest'
import { commandParts, launchArgs, spawnOnBoot, type LaunchSettings } from './launch'

function base(overrides: Partial<LaunchSettings> = {}): LaunchSettings {
  return {
    taskproofPath: 'taskproof',
    workspace: '/tmp/ws',
    portMode: 'auto',
    port: 8899,
    ...overrides
  }
}

/** The value that follows `--port`, which is what the child actually binds. */
function portArg(args: string[]): string | undefined {
  return args[args.indexOf('--port') + 1]
}

describe('launchArgs', () => {
  it("maps portMode 'auto' to `--port 0`, ignoring the stored port", () => {
    expect(portArg(launchArgs(base({ portMode: 'auto', port: 8899 })))).toBe('0')
  })

  it("maps portMode 'fixed' to the user's port, unchanged", () => {
    expect(portArg(launchArgs(base({ portMode: 'fixed', port: 8123 })))).toBe('8123')
  })

  it('puts the global --workspace flag before the api subcommand', () => {
    const args = launchArgs(base())
    expect(args.indexOf('--workspace')).toBeLessThan(args.indexOf('api'))
    expect(args[args.indexOf('--workspace') + 1]).toBe('/tmp/ws')
    expect(args).toContain('--allow-write')
  })

  it('keeps a "python3 -m taskproof" prefix as leading argv, not a file name', () => {
    const args = launchArgs(base({ taskproofPath: 'python3 -m taskproof' }))
    // `command` (the executable) is split off elsewhere; the rest leads argv.
    expect(args.slice(0, 2)).toEqual(['-m', 'taskproof'])
  })
})

describe('spawnOnBoot', () => {
  it("spawns for 'auto'", () => {
    expect(spawnOnBoot('auto')).toBe(true)
  })

  it("stays down for 'manual'", () => {
    expect(spawnOnBoot('manual')).toBe(false)
  })
})

describe('commandParts', () => {
  it('defaults to `taskproof` and collapses whitespace', () => {
    expect(commandParts(undefined)).toEqual(['taskproof'])
    expect(commandParts('  python3   -m taskproof ')).toEqual(['python3', '-m', 'taskproof'])
  })
})
