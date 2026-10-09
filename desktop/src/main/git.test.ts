/**
 * The git probe, pinned.
 *
 * The card's rule: a missing git is a *notice* on the settings page, never a
 * gate. So `runGitVersion` must answer a clean boolean for every outcome --
 * "found", "ran but failed", and "could not even spawn" -- and never throw.
 * The probe is driven through a fake `git` on an injected PATH, so it needs no
 * real git and never touches the developer's machine.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { gitAvailable, resetGitCache, runGitVersion } from './git'

let dir: string
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'tp-git-'))
  resetGitCache()
})
afterEach(() => {
  rmSync(dir, { recursive: true, force: true })
})

/** Put a fake `git` on a fresh bin dir and return the PATH that finds it. */
function fakeGit(script: string): string {
  const bin = mkdtempSync(join(dir, 'bin-'))
  const file = join(bin, 'git')
  writeFileSync(file, `#!/bin/sh\n${script}\n`, { mode: 0o755 })
  chmodSync(file, 0o755)
  return bin
}

describe('runGitVersion', () => {
  it('is true when `git --version` exits 0', async () => {
    const path = fakeGit('echo git version 2.43.0; exit 0')
    expect(await runGitVersion({ PATH: path })).toBe(true)
  })

  it('is false when the command runs but fails', async () => {
    const path = fakeGit('exit 1')
    expect(await runGitVersion({ PATH: path })).toBe(false)
  })

  it('is false (never throws) when git cannot be spawned at all', async () => {
    const empty = mkdtempSync(join(dir, 'empty-'))
    expect(await runGitVersion({ PATH: empty })).toBe(false)
  })
})

describe('gitAvailable', () => {
  it('memoises the first verdict', async () => {
    const path = fakeGit('exit 0')
    expect(await gitAvailable({ PATH: path })).toBe(true)
    // A broken second PATH is ignored: the memo holds the boot-time answer.
    expect(await gitAvailable({ PATH: '/definitely/not/here' })).toBe(true)
  })

  it('resetGitCache lets a case drive its own probe', async () => {
    const ok = fakeGit('exit 0')
    expect(await gitAvailable({ PATH: ok })).toBe(true)
    resetGitCache()
    const empty = mkdtempSync(join(dir, 'empty2-'))
    expect(await gitAvailable({ PATH: empty })).toBe(false)
  })
})
