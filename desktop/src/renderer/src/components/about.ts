/**
 * The About sheet's data, kept as plain functions so the parts worth pinning --
 * the CLI-version fallback, the four data paths, and the diagnostic text -- can
 * be unit-tested with no DOM and no browser in the loop.
 *
 * The open flag lives here too: the sheet is mounted once at the app root (so
 * the native menu can reach it from any page) while the settings row only needs
 * to raise a flag, and a module-level ref is the smallest thing both can share.
 */
import { ref } from 'vue'
import type { RuntimeVersions } from '../../../preload/types'

/** Shown wherever a version or path could not be read -- never a made-up value. */
export const EM_DASH = '—'

/** Whether the About sheet is open. Read by the sheet; flipped by the row / menu. */
export const aboutOpen = ref(false)

/** Open the About sheet (the settings row and the app menu both call this). */
export function openAbout(): void {
  aboutOpen.value = true
}

/** The CLI version cell: the parsed version, or an em dash when there is none. */
export function cliVersionLabel(version: string | null | undefined): string {
  return version ? version : EM_DASH
}

/** The four data locations the sheet lists. All derive from two real inputs. */
export interface AboutPaths {
  userData: string
  registry: string
  database: string
  events: string
}

/**
 * The four data paths. `userData` comes straight from the main process; the
 * other three live under the workspace. `now` is injectable so the monthly
 * event-log name is deterministic under test.
 */
export function aboutPaths(workspace: string, userData: string, now: Date = new Date()): AboutPaths {
  const ws = String(workspace ?? '').replace(/\/+$/, '')
  const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  return {
    userData: userData || EM_DASH,
    registry: ws ? `${ws}/projects.toml` : EM_DASH,
    database: ws ? `${ws}/taskproof.db` : EM_DASH,
    events: ws ? `${ws}/events-${month}.jsonl` : EM_DASH
  }
}

/** "Electron 39 · Chromium 142 · Node 22", with a dash for any missing piece. */
export function runtimeLabel(runtime: RuntimeVersions): string {
  const electron = runtime.electron || EM_DASH
  const chrome = runtime.chrome || EM_DASH
  const node = runtime.node || EM_DASH
  return `Electron ${electron} · Chromium ${chrome} · Node ${node}`
}

/** Everything `buildDiagnostics` reads. Note the deliberate absence of a token. */
export interface DiagnosticsInput {
  version: string | null
  cliVersion: string | null
  runtime: RuntimeVersions
  workspace: string
  service: { state: string; port: number | null }
  paths: AboutPaths
}

/**
 * The text behind "copy diagnostics". It is a **whitelist** of the fields below
 * and nothing else: the workspace, the service state and port, the version trio
 * and the four paths. The write token is not an input here, so there is no code
 * path by which it could leak into a bug report the user pastes in a public
 * issue; an unexpected extra field on the input is ignored, not spread.
 */
export function buildDiagnostics(input: DiagnosticsInput): string {
  const service = input.service.port
    ? `${input.service.state} :${input.service.port}`
    : input.service.state
  return [
    'Taskproof · 诊断信息 / diagnostics',
    `App: ${input.version || EM_DASH}`,
    `CLI: ${cliVersionLabel(input.cliVersion)}`,
    `Runtime: ${runtimeLabel(input.runtime)}`,
    `workspace: ${input.workspace || EM_DASH}`,
    `service: ${service || EM_DASH}`,
    `userData: ${input.paths.userData}`,
    `registry: ${input.paths.registry}`,
    `database: ${input.paths.database}`,
    `events: ${input.paths.events}`
  ].join('\n')
}
