/**
 * The argv for the local API child, derived from the desktop settings.
 *
 * The launcher used to hard-code `--port 0` and `--allow-write`, so the
 * `portMode` / `port` / `launch` switches were persisted but never consulted.
 * This module is the one place that turns those settings into a command line,
 * which is what makes the switches true behaviour instead of decoration.
 */
import type { DesktopSettings } from '../preload/types'

/** The settings that shape the child's command line. */
export type LaunchSettings = Pick<
  DesktopSettings,
  'taskproofPath' | 'workspace' | 'portMode' | 'port'
>

/**
 * Split the `taskproofPath` setting into an executable and its leading arguments
 * ("python3 -m taskproof" must not be treated as one file name).
 */
export function commandParts(taskproofPath: string | undefined): string[] {
  return (taskproofPath || 'taskproof').trim().split(/\s+/)
}

/**
 * The argv that follows the executable.
 *
 *  - the global `--workspace` flag precedes the subcommand;
 *  - `--allow-write` belongs to `api` and opens the token-protected write
 *    surface;
 *  - `portMode: 'auto'` asks for `--port 0` (the OS picks a free port);
 *    `'fixed'` passes the user's port through unchanged, so an occupied port
 *    fails loudly instead of silently switching.
 */
export function launchArgs(current: LaunchSettings): string[] {
  const parts = commandParts(current.taskproofPath)
  const port = current.portMode === 'fixed' ? String(current.port) : '0'
  return [
    ...parts.slice(1),
    '--workspace',
    current.workspace,
    'api',
    '--allow-write',
    '--port',
    port
  ]
}

/**
 * Whether the app spawns the child on open. `'auto'` spawns at boot; `'manual'`
 * stays down until the user asks for it (the "retry / start" affordance).
 */
export function spawnOnBoot(launch: DesktopSettings['launch']): boolean {
  return launch === 'auto'
}
