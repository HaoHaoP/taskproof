/**
 * The enum contract, and the presentation built on top of it.
 *
 * The vocabulary (which status words exist, which are terminal, the verify
 * kinds, the exit-code meanings) is NOT typed out here. It is imported from the
 * artefact generated out of the Python constants, so a status added to Python
 * cannot go missing in the UI.
 *
 * A missing status would not raise anything -- it would just never render, and
 * a task would disappear from the board. That is the failure this file exists to
 * prevent, and the one the Python board already guards against.
 */
import enums from '@contract/enums.json'

export interface StatusDecl {
  id: string
  terminal: boolean
}

export const STATUS_DECLS: StatusDecl[] = enums.statuses
export const VERIFY_KINDS: string[] = enums.verify_kinds
export const EXIT_MEANINGS: Record<number, string> = Object.fromEntries(
  enums.exit_codes.map((entry) => [entry.code, entry.meaning])
)

export const STATUS_IDS: string[] = STATUS_DECLS.map((s) => s.id)
export const TERMINAL_STATUSES: Set<string> = new Set(
  STATUS_DECLS.filter((s) => s.terminal).map((s) => s.id)
)

export interface StatusMeta {
  /** The word itself, also the `data-status` value. */
  id: string
  /** The lamp glyph on a card. */
  glyph: string
  /** Token suffix: colours come from `--c-<tone>` / `--w-<tone>`. */
  tone: string
}

/** Presentation. The contract owns the vocabulary; this owns how it looks. */
export const STATUS_META: Record<string, StatusMeta> = {
  queued: { id: 'queued', glyph: '○', tone: 'queued' },
  running: { id: 'running', glyph: '●', tone: 'running' },
  verifying: { id: 'verifying', glyph: '◉', tone: 'verifying' },
  done: { id: 'done', glyph: '✓', tone: 'done' },
  failed: { id: 'failed', glyph: '✗', tone: 'failed' },
  blocked: { id: 'blocked', glyph: '⊘', tone: 'blocked' },
  timeout: { id: 'timeout', glyph: '◐', tone: 'timeout' },
  cancelled: { id: 'cancelled', glyph: '⊖', tone: 'cancelled' }
}

/**
 * A column is a stage in the pipeline. A failure reason is not a stage -- it is
 * a property of the card -- so the failure-like terminal states share the last
 * column and keep their own colour and glyph. Cancellation is different: it is
 * an action the operator took, not a defect, so it gets a column of its own
 * rather than polluting the failure alarm.
 */
export interface Column {
  key: string
  members: string[]
}

/** The failure-like terminal states. Cancellation is deliberately not one of
 *  them: it has its own column. */
export const ABNORMAL: string[] = ['failed', 'blocked', 'timeout']

export const COLUMNS: Column[] = [
  { key: 'queued', members: ['queued'] },
  { key: 'running', members: ['running'] },
  { key: 'verifying', members: ['verifying'] },
  { key: 'done', members: ['done'] },
  { key: 'cancelled', members: ['cancelled'] },
  { key: 'abnormal', members: ABNORMAL }
]

export const LAST_COLUMN: Column = COLUMNS[COLUMNS.length - 1]

const KNOWN_STATUSES: Set<string> = new Set(STATUS_IDS)

/** Falls back to a neutral mark rather than nothing: never hide a status. */
export function metaFor(status: string): StatusMeta {
  return STATUS_META[status] ?? { id: status, glyph: '?', tone: 'unknown' }
}

/** Unknown statuses land in the column that collects everything that failed. */
export function columnFor(status: string): Column {
  return COLUMNS.find((column) => column.members.includes(status)) ?? LAST_COLUMN
}

/** True when the contract declares this word. Used to flag contract drift. */
export function isKnownStatus(status: string): boolean {
  return KNOWN_STATUSES.has(status)
}

/** Distinct status words the API reported that this build does not know about. */
export function unknownStatuses(ids: Iterable<string>): string[] {
  const out = new Set<string>()
  for (const id of ids) if (!KNOWN_STATUSES.has(id)) out.add(id)
  return [...out]
}

export function isTerminal(status: string): boolean {
  return TERMINAL_STATUSES.has(status)
}
