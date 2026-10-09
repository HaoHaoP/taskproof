/**
 * Turning desktop settings into the argv for the local API child.
 *
 * The launcher used to hard-code the command as the raw `taskproofPath`
 * setting, defaulting to `taskproof` -- which assumes the binary is reachable
 * on PATH. Two things make that assumption wrong for a *packaged* app:
 *
 *  - a GUI-launched app inherits launchd's minimal PATH
 *    (`/usr/bin:/bin:/usr/sbin:/sbin`), so `~/.local/bin/taskproof` (the pipx
 *    shim) is invisible even though a terminal would find it;
 *  - the installer ships a relocatable CPython, and "one install and it works"
 *    means the app must prefer that bundled runtime over anything on PATH.
 *
 * `resolveLaunchCommand` is the single place that decides, in a pinned
 * priority order:
 *   1. a non-empty `setting` (the user said exactly what to run);
 *   2. the bundled runtime under `<resourcesPath>/python`;
 *   3. `taskproof` on the (augmented) PATH;
 *   4. `python3 -m taskproof` as the last resort.
 * It also augments PATH with the directories a GUI-launched app is missing,
 * so a pipx install is found without the user editing anything.
 */
import { homedir } from 'os'
import { join } from 'path'
import type { DesktopSettings } from '../preload/types'

/** The settings that shape the child's command line. */
export type LaunchSettings = Pick<
  DesktopSettings,
  'taskproofPath' | 'workspace' | 'portMode' | 'port'
>

/** Where the resolved argv came from, in the pinned priority order. */
export type LaunchSource = 'setting' | 'bundled' | 'path' | 'python3'

/** Everything `resolveLaunchCommand` needs; all injectable so it stays pure. */
export interface ResolveLaunchInput {
  /** The `taskproofPath` setting; empty/whitespace falls through to the rest. */
  setting?: string
  /** `<resourcesPath>`: the app's `process.resourcesPath`, or a test override. */
  resourcesPath: string
  /** The current PATH (the un-augmented one). */
  pathEnv: string
  platform: NodeJS.Platform
  /** Injectable filesystem probe, so the branches need no real files. */
  exists(p: string): boolean
}

/** The resolved command plus the extra environment the child must inherit. */
export interface ResolvedLaunchCommand {
  /** The executable and its leading arguments, e.g. `['python3', '-m', 'taskproof']`. */
  argv: string[]
  source: LaunchSource
  /** Extra environment (at least an augmented `PATH`) for the child. */
  env: Record<string, string>
}

/**
 * Split the `taskproofPath` setting into an executable and its leading arguments
 * ("python3 -m taskproof" must not be treated as one file name).
 */
export function commandParts(taskproofPath: string | undefined): string[] {
  return (taskproofPath || 'taskproof').trim().split(/\s+/)
}

function pathDelimiter(platform: NodeJS.Platform): string {
  return platform === 'win32' ? ';' : ':'
}

/** The directories a GUI-launched app is missing from its inherited PATH. */
export function augmentedDirs(home: string): string[] {
  return [join(home, '.local', 'bin'), '/opt/homebrew/bin', '/usr/local/bin']
}

/**
 * Prepend the extra directories to `pathEnv`, dropping blanks and duplicates so
 * an already-present `/usr/local/bin` is not listed twice.
 */
export function augmentedPath(pathEnv: string, home: string, platform: NodeJS.Platform): string {
  const delim = pathDelimiter(platform)
  const seen = new Set<string>()
  const dirs: string[] = []
  for (const dir of [...augmentedDirs(home), ...pathEnv.split(delim)]) {
    if (!dir || seen.has(dir)) continue
    seen.add(dir)
    dirs.push(dir)
  }
  return dirs.join(delim)
}

/** The bundled interpreter for this platform, per the packaged layout. */
function bundledInterpreter(resourcesPath: string, platform: NodeJS.Platform): string {
  return platform === 'win32'
    ? join(resourcesPath, 'python', 'python.exe')
    : join(resourcesPath, 'python', 'bin', 'python3')
}

/** Is `name` on one of the PATH directories? (`exists` is the only probe.) */
function onPath(
  name: string,
  pathEnv: string,
  platform: NodeJS.Platform,
  exists: (p: string) => boolean
): boolean {
  const delim = pathDelimiter(platform)
  const names =
    platform === 'win32' ? [`${name}.exe`, `${name}.cmd`, `${name}.bat`, name] : [name]
  for (const dir of pathEnv.split(delim)) {
    if (!dir) continue
    for (const candidate of names) {
      if (exists(join(dir, candidate))) return true
    }
  }
  return false
}

/**
 * Resolve the child's argv, its source and the extra environment to hand it.
 *
 * The priority order (setting, bundled, PATH, python3) is a product decision
 * and must not be reordered: a user override always wins, the bundled runtime
 * always beats a stray PATH entry, and `python3` is only ever the fallback.
 */
export function resolveLaunchCommand(input: ResolveLaunchInput): ResolvedLaunchCommand {
  const augmented = augmentedPath(input.pathEnv, homedir(), input.platform)
  const env: Record<string, string> = { PATH: augmented }

  // 1. An explicit setting wins, split the existing way so
  //    "python3 -m taskproof" stays leading argv, not a single file name.
  const setting = input.setting?.trim()
  if (setting) {
    return { argv: commandParts(setting), source: 'setting', env }
  }

  // 2. The runtime that ships inside the app; PYTHONPATH points at the bundled
  //    `src` so `-m taskproof` resolves against the package next to the app.
  const interpreter = bundledInterpreter(input.resourcesPath, input.platform)
  if (input.exists(interpreter)) {
    env.PYTHONPATH = join(input.resourcesPath, 'src')
    return { argv: [interpreter, '-m', 'taskproof'], source: 'bundled', env }
  }

  // 3. A `taskproof` on the (augmented) PATH -- the pipx case this card fixes.
  if (onPath('taskproof', augmented, input.platform, input.exists)) {
    return { argv: ['taskproof'], source: 'path', env }
  }

  // 4. The last resort. It may still work if `python3` has taskproof installed.
  return { argv: ['python3', '-m', 'taskproof'], source: 'python3', env }
}

/**
 * The argv that follows the resolved command.
 *
 *  - the global `--workspace` flag precedes the subcommand;
 *  - `--allow-write` belongs to `api` and opens the token-protected write
 *    surface;
 *  - `portMode: 'auto'` asks for `--port 0` (the OS picks a free port);
 *    `'fixed'` passes the user's port through unchanged, so an occupied port
 *    fails loudly instead of silently switching.
 */
export function launchFlags(current: LaunchSettings): string[] {
  const port = current.portMode === 'fixed' ? String(current.port) : '0'
  return ['--workspace', current.workspace, 'api', '--allow-write', '--port', port]
}

/**
 * Whether the app spawns the child on open. `'auto'` spawns at boot; `'manual'`
 * stays down until the user asks for it (the "retry / start" affordance).
 */
export function spawnOnBoot(launch: DesktopSettings['launch']): boolean {
  return launch === 'auto'
}
