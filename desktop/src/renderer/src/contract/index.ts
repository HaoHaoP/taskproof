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
 * column and keep their own colour and glyph. Two terminal states are waiting
 * rooms rather than verdicts and get a column of their own, each for a different
 * reason: cancellation is an action the operator took, and `blocked` is a
 * boundary breach parked until a human either accepts it (`accept`) or clears
 * it another way. Neither belongs in the failure alarm.
 */
export interface Column {
  key: string
  members: string[]
}

/** The failure-like terminal states. Cancellation and `blocked` are deliberately
 *  not among them: each has a column of its own -- `cancelled` because the
 *  operator stopped it, `blocked` because it is waiting for a human, not because
 *  the work went wrong. `failed` / `timeout` are the only true verdicts here. */
export const ABNORMAL: string[] = ['failed', 'timeout']

/**
 * The board's columns (泳道), in draw order. `blocked` sits between `cancelled`
 * and the failure column: like `cancelled` it is a terminal state a card stops
 * at, but it is a waiting room ("needs review") rather than a verdict, so it is
 * kept out of `ABNORMAL`. `abnormal` stays last -- it collects every failure-like
 * state, including any status a future contract adds that no column claims.
 */
export const COLUMNS: Column[] = [
  { key: 'running', members: ['running'] },
  { key: 'verifying', members: ['verifying'] },
  { key: 'done', members: ['done'] },
  { key: 'cancelled', members: ['cancelled'] },
  { key: 'blocked', members: ['blocked'] },
  { key: 'abnormal', members: ABNORMAL }
]

export const LAST_COLUMN: Column = COLUMNS[COLUMNS.length - 1]

/**
 * i18n key for a column's header. Most columns reuse the status word
 * (`status.<key>`, e.g. `status.running` -> 进行中). The `blocked` lane is the one
 * exception: its header names the operator's job -- a human has to look and
 * either accept or clear the card -- not the status word itself, which stays
 * 阻塞 / Blocked. Two purposes, two keys; they are deliberately not shared.
 */
const COLUMN_LABEL_KEY: Record<string, string> = {
  blocked: 'column.blocked'
}

export function columnLabelKey(columnKey: string): string {
  return COLUMN_LABEL_KEY[columnKey] ?? `status.${columnKey}`
}

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
