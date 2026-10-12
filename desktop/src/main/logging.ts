/**
 * Renderer diagnostics, appended from the main process.
 *
 * The renderer this app ships is a production Vue build: a component that
 * throws during patch only prints to `console.error` and the renderer has no
 * write channel of its own (see the preload header). So the one place a
 * renderer failure can be turned into a file on disk -- the main process -- has
 * to do it, and it has to be bullet-proof: a logging path that throws would
 * take the whole app down while trying to describe a failure. Everything here
 * is plain `fs`/`path`, no `electron`, so it is a pure unit under test.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname } from 'path'

/** The record file is capped so a renderer erroring in a loop cannot fill the disk. */
export const RECORD_LIMIT_BYTES = 1_000_000

/** Past this, a single record's text is truncated: enough for a stack, not a novel. */
const MAX_TEXT_CHARS = 4000

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

/**
 * Local ISO 8601 with the numeric UTC offset (`2026-10-12T10:00:00+08:00`).
 * `toISOString` would force UTC, which is useless for eyeballing "when did this
 * happen" against the machine's own clock.
 */
function localIso(at: Date): string {
  const offset = -at.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const hours = pad2(Math.floor(Math.abs(offset) / 60))
  const minutes = pad2(Math.abs(offset) % 60)
  return (
    `${at.getFullYear()}-${pad2(at.getMonth() + 1)}-${pad2(at.getDate())}` +
    `T${pad2(at.getHours())}:${pad2(at.getMinutes())}:${pad2(at.getSeconds())}` +
    `${sign}${hours}:${minutes}`
  )
}

/**
 * One record, one line: `<local ISO> <kind> <text>`. Real newlines are folded to
 * a literal `\n` so a multi-line stack trace still reads as a single record --
 * the file is a line log, and a line that contains a newline would break every
 * reader of it. Long text is truncated with a marker rather than dropped.
 */
export function formatRendererLine(kind: string, text: string, at: Date = new Date()): string {
  const folded = text.replace(/\r?\n/g, '\\n')
  const body = folded.length > MAX_TEXT_CHARS ? `${folded.slice(0, MAX_TEXT_CHARS)}…(truncated)` : folded
  return `${localIso(at)} ${kind} ${body}`
}

/**
 * Only error-level console output is worth a record; everything else (verbose,
 * info, warning) is normal chatter. The renderer's level arrives as a string in
 * the current Electron details object ('error'), but the legacy positional
 * argument is a number (0..3, error is 3) -- accept both so a future signature
 * flip does not quietly stop recording.
 */
export function shouldRecordConsoleLevel(level: string | number): boolean {
  if (typeof level === 'number') return level >= 3
  return level.toLowerCase() === 'error'
}

/** Trim `content` to its trailing whole lines that fit within `limit` bytes. */
function keepTailWithinLimit(content: string, limit: number): string {
  const lines = content.split('\n')
  // A trailing newline leaves a final empty element; that is the terminator of
  // the last record, not a record of its own.
  if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop()
  const kept: string[] = []
  let size = 0
  for (let i = lines.length - 1; i >= 0; i--) {
    const recordBytes = Buffer.byteLength(lines[i], 'utf8') + 1 // + the '\n'
    if (size + recordBytes > limit) break
    kept.unshift(lines[i])
    size += recordBytes
  }
  return kept.length > 0 ? `${kept.join('\n')}\n` : ''
}

/**
 * Append one record to `file`, keeping the file under `limit` bytes by dropping
 * whole records from the front when it grows past the cap. Creates the parent
 * directory on demand. IO errors are swallowed and reported as `false`:
 * diagnostics must never be the reason the app crashes.
 */
export function appendBounded(file: string, line: string, limit = RECORD_LIMIT_BYTES): boolean {
  try {
    mkdirSync(dirname(file), { recursive: true })
    const prior = existsSync(file) ? readFileSync(file, 'utf8') : ''
    let next = `${prior}${line}\n`
    if (Buffer.byteLength(next, 'utf8') > limit) next = keepTailWithinLimit(next, limit)
    writeFileSync(file, next, 'utf8')
    return true
  } catch {
    return false
  }
}
