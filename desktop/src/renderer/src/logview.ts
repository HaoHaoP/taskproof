/**
 * The log panel's reasoning, pulled out of the SFC so it can be pinned without
 * a DOM.
 *
 * Everything here is plain data in / data out: ANSI stripping, the local search
 * (matching + highlight segments), the "is the reader at the bottom" rule, and
 * the line cap / byte formatter the notices are built from.
 */

/**
 * ANSI / VT escape sequences: SGR colours, cursor moves, OSC titles. The shape
 * mirrors the well-known `ansi-regex`; it is only ever used to *remove* them for
 * display, never to interpret them.
 */
const ANSI_PATTERN =
  /[\u001B\u009B][[\]()#;?]*(?:(?:(?:(?:;[-a-zA-Z\d/#&.:=?%@~_]+)*|[a-zA-Z\d]+(?:;[-a-zA-Z\d/#&.:=?%@~_]*)*)?\u0007)|(?:(?:\d{1,4}(?:;\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]))/g

/**
 * Drop ANSI escape sequences so the panel shows plain text. The *un-stripped*
 * text stays in the store -- the copy button copies what the process wrote.
 */
export function stripAnsi(text: string): string {
  return text.replace(ANSI_PATTERN, '')
}

interface Match {
  index: number
  length: number
}

/**
 * Every match of `query` in `text`, as start/length pairs.
 *
 * Case-insensitive: reading a log is debugging, and nobody should have to
 * remember whether the process shouted `ERROR` or `Error`. Matching advances
 * past each hit, so occurrences do not overlap -- the same convention as a
 * browser's find-in-page.
 */
function findMatches(text: string, query: string): Match[] {
  if (!query) return []
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(escaped, 'gi')
  const out: Match[] = []
  let found: RegExpExecArray | null
  while ((found = re.exec(text)) !== null) {
    out.push({ index: found.index, length: found[0].length })
    if (found[0].length === 0) re.lastIndex += 1
  }
  return out
}

/** How many times `query` appears in `text`. An empty query matches nothing. */
export function countMatches(text: string, query: string): number {
  return findMatches(text, query).length
}

/**
 * 0-based line indexes that contain a match, one entry per occurrence -- a line
 * with two hits is listed twice, so the count and the jump share one list. An
 * empty query yields no hits.
 */
export function matchLineIndexes(text: string, query: string): number[] {
  return findMatches(text, query).map((match) => lineOf(text, match.index))
}

function lineOf(text: string, index: number): number {
  let line = 0
  const stop = Math.min(index, text.length)
  for (let i = 0; i < stop; i += 1) {
    if (text[i] === '\n') line += 1
  }
  return line
}

export interface Segment {
  text: string
  hit: boolean
}

/**
 * Split one line into plain and matching segments, preserving the line's own
 * case (only the *comparison* is case-insensitive). An empty query yields the
 * whole line as one non-hit segment.
 */
export function highlightSegments(line: string, query: string): Segment[] {
  const matches = findMatches(line, query)
  if (!matches.length) return [{ text: line, hit: false }]
  const out: Segment[] = []
  let cursor = 0
  for (const match of matches) {
    if (match.index > cursor) out.push({ text: line.slice(cursor, match.index), hit: false })
    out.push({ text: line.slice(match.index, match.index + match.length), hit: true })
    cursor = match.index + match.length
  }
  if (cursor < line.length) out.push({ text: line.slice(cursor), hit: false })
  return out
}

/**
 * Is the reader (near) the bottom? True when the distance from the current
 * scroll position to the end is within `threshold` pixels -- inclusive, so a
 * position exactly `threshold` away still counts as "sticking". A negative
 * distance (over-scrolled past the end) counts too.
 */
export function shouldStickBottom(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
  threshold = 24
): boolean {
  return scrollHeight - clientHeight - scrollTop <= threshold
}

/** `1536` -> `1.5 KB`. Binary units (1024), one decimal, a trailing `.0` dropped. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  const rounded = unit === 0 ? Math.round(value) : Math.round(value * 10) / 10
  return `${rounded} ${units[unit]}`
}

/** UTF-8 byte length. The search scope is stated in bytes, so a JS string
 *  length would undercount multi-byte characters. */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length
}

/** Newline count -- lets the store keep a running line total without holding a
 *  second copy of the whole log. */
export function countNewlines(text: string): number {
  let count = 0
  for (let i = 0; i < text.length; i += 1) if (text[i] === '\n') count += 1
  return count
}

/** Lines in `text`, matching what `text.split('\n')` will render (a trailing
 *  newline opens a final empty line). */
export function countLines(text: string): number {
  return text === '' ? 0 : countNewlines(text) + 1
}

/**
 * Keep at most the last `max` lines. Returns the same string when it is already
 * short enough, and `truncated: true` once anything was dropped -- the panel
 * must say so rather than silently losing the head of a very long log.
 */
export function capToLastLines(text: string, max: number): { text: string; truncated: boolean } {
  if (max <= 0) return { text: '', truncated: text.length > 0 }
  const lines = countLines(text)
  if (lines <= max) return { text, truncated: false }
  const drop = lines - max
  let seen = 0
  let cut = 0
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === '\n') {
      seen += 1
      if (seen === drop) {
        cut = i + 1
        break
      }
    }
  }
  return { text: text.slice(cut), truncated: true }
}
