/**
 * The one honest git check: `git --version` on the *augmented* PATH.
 *
 * The gate lints a change with `git worktree` and checks that no protected
 * path was touched; without git on PATH those two features cannot run. The app
 * is otherwise fully usable, so a missing git is a *notice*, never a gate: this
 * probe only answers a yes/no and never blocks startup. It is run with the same
 * augmented PATH the child gets, because a Finder-launched app inherits
 * launchd's minimal PATH -- the exact case where git would look "missing" even
 * though a terminal finds it.
 */
import { spawn } from 'child_process'

const GIT_TIMEOUT_MS = 5_000

/** Whether `git --version` succeeds, using `env` (which carries the PATH). */
export function runGitVersion(env: Record<string, string>): Promise<boolean> {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn('git', ['--version'], {
        stdio: ['ignore', 'ignore', 'ignore'],
        env: { ...process.env, ...env }
      })
    } catch {
      resolve(false)
      return
    }

    let settled = false
    const finish = (value: boolean): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(value)
    }
    const timer = setTimeout(() => {
      child.kill()
      finish(false)
    }, GIT_TIMEOUT_MS)

    child.once('error', () => finish(false))
    child.once('exit', (code) => finish(code === 0))
  })
}

/** Memoised verdict, so a boot-time probe is reused instead of re-spawned. */
let cached: Promise<boolean> | undefined

/** Probe once per process; later callers share the first result. */
export function gitAvailable(env: Record<string, string>): Promise<boolean> {
  cached ??= runGitVersion(env)
  return cached
}

/** Test-only: drop the memo so a case can drive its own probe. */
export function resetGitCache(): void {
  cached = undefined
}
