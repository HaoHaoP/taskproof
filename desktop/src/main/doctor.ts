/**
 * `taskproof doctor --json`, run on demand for the settings page's About group.
 *
 * The frozen REST API has no adapter endpoint, so the only honest source for
 * "which adapters are installed" is the CLI's own self-check. It is run with
 * the same command and workspace the service uses, and its JSON is parsed
 * defensively: a build that cannot answer, or answers something unexpected,
 * yields null so the UI can show a dash instead of a fabricated verdict.
 */
import { spawn } from 'child_process'
import type { AdapterStatus } from '../preload/types'

export interface DoctorSpec {
  /** The executable, e.g. `taskproof` or `python3`. */
  command: string
  /** Arguments that precede the global flags, e.g. `['-m', 'taskproof']`. */
  prefixArgs: string[]
  workspace: string
  /** Extra environment for the child (the augmented PATH), merged over `process.env`. */
  env: Record<string, string>
}

const DOCTOR_TIMEOUT_MS = 15_000

/** Pull the adapter list out of a `doctor --json` document, or null if it is
 *  not the shape we expect (a missing command, a crash, plain text). */
export function parseAdapters(raw: string): AdapterStatus[] | null {
  let report: unknown
  try {
    report = JSON.parse(raw)
  } catch {
    return null
  }
  if (report === null || typeof report !== 'object') return null
  const adapters = (report as { adapters?: unknown }).adapters
  if (!Array.isArray(adapters)) return null
  const out: AdapterStatus[] = []
  for (const item of adapters) {
    if (item === null || typeof item !== 'object') continue
    const record = item as Record<string, unknown>
    if (typeof record.name !== 'string' || !record.name) continue
    out.push({
      name: record.name,
      installed: record.installed === true,
      detail: typeof record.detail === 'string' ? record.detail : ''
    })
  }
  return out
}

/** Run the self-check; resolve with its adapters, or null when it cannot run. */
export function runDoctor(spec: DoctorSpec): Promise<AdapterStatus[] | null> {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(
        spec.command,
        [...spec.prefixArgs, '--workspace', spec.workspace, '--json', 'doctor'],
        { stdio: ['ignore', 'pipe', 'ignore'], env: { ...process.env, ...spec.env } }
      )
    } catch {
      resolve(null)
      return
    }

    let out = ''
    let settled = false
    const finish = (value: AdapterStatus[] | null): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(value)
    }
    const timer = setTimeout(() => {
      child.kill()
      finish(null)
    }, DOCTOR_TIMEOUT_MS)

    child.stdout?.setEncoding('utf8')
    child.stdout?.on('data', (chunk: string) => {
      // Cap the buffer: doctor is chatty, but we only need its JSON document.
      out = (out + chunk).slice(-1_000_000)
    })
    child.once('error', () => finish(null))
    child.once('exit', () => finish(parseAdapters(out)))
  })
}
