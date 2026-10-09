/**
 * The launch-resolution contract, pinned.
 *
 * Two regressions this file is here to catch:
 *
 *  - the app used to run the raw `taskproofPath` setting, which for a
 *    GUI-launched app means "not on launchd's minimal PATH" -- the child never
 *    came up. So *all four* resolution branches and the PATH augmentation are
 *    pinned, one case each;
 *  - the priority order (setting > bundled > PATH > python3) is a product
 *    decision, so a case proves a lower branch never shadows a higher one.
 *
 * Everything is injected (resourcesPath, pathEnv, platform, exists), so the
 * branches are exercised without touching the real filesystem.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { join } from 'path'
import {
  augmentedPath,
  commandParts,
  launchFlags,
  resolveLaunchCommand,
  spawnOnBoot,
  type LaunchSettings,
  type ResolveLaunchInput
} from './launch'

const RES = '/opt/Taskproof.app/Contents/Resources'

/** A `exists` probe backed by a fixed set of paths. */
function fsOf(paths: string[]): (p: string) => boolean {
  const set = new Set(paths)
  return (p) => set.has(p)
}

function input(overrides: Partial<ResolveLaunchInput> = {}): ResolveLaunchInput {
  return {
    setting: '',
    resourcesPath: RES,
    pathEnv: '/usr/bin:/bin',
    platform: 'darwin',
    exists: () => false,
    ...overrides
  }
}

describe('resolveLaunchCommand -- the four branches', () => {
  it('1. a non-empty setting wins and keeps its leading argv', () => {
    const out = resolveLaunchCommand(input({ setting: 'python3 -m taskproof' }))
    expect(out.source).toBe('setting')
    expect(out.argv).toEqual(['python3', '-m', 'taskproof'])
  })

  it('1. an explicit setting beats the bundled runtime even when it exists', () => {
    const out = resolveLaunchCommand(
      input({
        setting: '/custom/taskproof',
        exists: fsOf([join(RES, 'python', 'bin', 'python3')])
      })
    )
    expect(out.source).toBe('setting')
    expect(out.argv).toEqual(['/custom/taskproof'])
  })

  it('2. the bundled runtime is preferred, with PYTHONPATH pointing at bundled src', () => {
    const interpreter = join(RES, 'python', 'bin', 'python3')
    const out = resolveLaunchCommand(input({ exists: fsOf([interpreter]) }))
    expect(out.source).toBe('bundled')
    expect(out.argv).toEqual([interpreter, '-m', 'taskproof'])
    expect(out.env.PYTHONPATH).toBe(join(RES, 'src'))
  })

  it('2. bundled beats a `taskproof` on the original PATH', () => {
    const interpreter = join(RES, 'python', 'bin', 'python3')
    const out = resolveLaunchCommand(
      input({
        pathEnv: '/custom/bin:/usr/bin',
        exists: fsOf([interpreter, '/custom/bin/taskproof'])
      })
    )
    expect(out.source).toBe('bundled')
  })

  it('3. a `taskproof` on PATH is used as a bare command name', () => {
    const out = resolveLaunchCommand(input({ exists: fsOf(['/usr/local/bin/taskproof']) }))
    expect(out.source).toBe('path')
    expect(out.argv).toEqual(['taskproof'])
  })

  it('4. otherwise it falls back to `python3 -m taskproof`', () => {
    const out = resolveLaunchCommand(input())
    expect(out.source).toBe('python3')
    expect(out.argv).toEqual(['python3', '-m', 'taskproof'])
  })
})

describe('resolveLaunchCommand -- PATH augmentation (hard defect 1)', () => {
  let prevHome: string | undefined

  beforeEach(() => {
    prevHome = process.env.HOME
    process.env.HOME = '/Users/tester'
  })
  afterEach(() => {
    if (prevHome === undefined) delete process.env.HOME
    else process.env.HOME = prevHome
  })

  it('finds a pipx `taskproof` in ~/.local/bin even with a launchd-minimal PATH', () => {
    // The bug: PATH is stripped to the launchd default, so the pipx shim is
    // invisible -- unless the app prepends ~/.local/bin itself. This asserts
    // exactly that, through the real resolver.
    const pipx = join('/Users/tester', '.local', 'bin', 'taskproof')
    const out = resolveLaunchCommand(
      input({ pathEnv: '/usr/bin:/bin', exists: fsOf([pipx]) })
    )
    expect(out.source).toBe('path')
    expect(out.argv).toEqual(['taskproof'])
  })

  it('prepends the extra dirs, in order, before the original PATH', () => {
    expect(augmentedPath('/usr/bin:/bin', '/Users/tester', 'darwin')).toBe(
      ['/Users/tester/.local/bin', '/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin'].join(':')
    )
  })

  it('drops a duplicate dir rather than listing it twice', () => {
    expect(augmentedPath('/usr/local/bin:/bin', '/Users/tester', 'darwin')).toBe(
      ['/Users/tester/.local/bin', '/opt/homebrew/bin', '/usr/local/bin', '/bin'].join(':')
    )
  })

  it('hands every branch the augmented PATH', () => {
    for (const setting of ['', undefined]) {
      const out = resolveLaunchCommand(input({ setting }))
      expect(out.env.PATH).toContain(join('/Users/tester', '.local', 'bin'))
      expect(out.env.PATH).toContain('/opt/homebrew/bin')
      expect(out.env.PATH).toContain('/usr/local/bin')
      expect(out.env.PATH).toContain('/usr/bin')
    }
  })
})

describe('resolveLaunchCommand -- win32 layout + delimiter', () => {
  it('looks for python/python.exe, not python/bin/python3', () => {
    const interpreter = join(RES, 'python', 'python.exe')
    const out = resolveLaunchCommand(
      input({ platform: 'win32', resourcesPath: RES, exists: fsOf([interpreter]) })
    )
    expect(out.source).toBe('bundled')
    expect(out.argv).toEqual([interpreter, '-m', 'taskproof'])
    expect(out.env.PYTHONPATH).toBe(join(RES, 'src'))
  })

  it('splits PATH on `;` on win32 and still augments it', () => {
    const joined = augmentedPath('C:\\Windows', 'C:\\Users\\tester', 'win32')
    const parts = joined.split(';')
    expect(parts[0]).toBe(join('C:\\Users\\tester', '.local', 'bin'))
    expect(parts).toContain('C:\\Windows')
  })
})

describe('commandParts', () => {
  it('defaults to `taskproof` and collapses whitespace', () => {
    expect(commandParts(undefined)).toEqual(['taskproof'])
    expect(commandParts('  python3   -m taskproof ')).toEqual(['python3', '-m', 'taskproof'])
  })
})

/** The value that follows `--port`, which is what the child actually binds. */
function portArg(args: string[]): string | undefined {
  return args[args.indexOf('--port') + 1]
}

function base(overrides: Partial<LaunchSettings> = {}): LaunchSettings {
  return {
    taskproofPath: 'taskproof',
    workspace: '/tmp/ws',
    portMode: 'auto',
    port: 8899,
    ...overrides
  }
}

describe('launchFlags', () => {
  it("maps portMode 'auto' to `--port 0`, ignoring the stored port", () => {
    expect(portArg(launchFlags(base({ portMode: 'auto', port: 8899 })))).toBe('0')
  })

  it("maps portMode 'fixed' to the user's port, unchanged", () => {
    expect(portArg(launchFlags(base({ portMode: 'fixed', port: 8123 })))).toBe('8123')
  })

  it('puts the global --workspace flag before the api subcommand', () => {
    const args = launchFlags(base())
    expect(args.indexOf('--workspace')).toBeLessThan(args.indexOf('api'))
    expect(args[args.indexOf('--workspace') + 1]).toBe('/tmp/ws')
    expect(args).toContain('--allow-write')
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
