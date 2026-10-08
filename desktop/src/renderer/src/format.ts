/** Small display helpers. Formatting is presentation, so it lives here, not in
 *  the store and not inline in templates. */

/** `2026-10-08T10:33:10+08:00` -> `10:33:10`; unparseable input is shown as-is. */
export function shortTime(value: string | null | undefined): string {
  if (!value) return '—'
  const match = value.match(/T(\d{2}:\d{2}:\d{2})/)
  return match ? match[1] : value
}

/** `30m00s` / `0m48s`, matching the prototype. Running tasks measure to now. */
export function duration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return '—'
  const start = Date.parse(startedAt)
  const end = finishedAt ? Date.parse(finishedAt) : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end)) return '—'
  const total = Math.max(0, Math.round((end - start) / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}m${String(seconds).padStart(2, '0')}s`
}

/** Renders an event payload as one readable line without dropping anything --
 *  an unrecognised key is still shown, which is how a new Python-side field
 *  becomes visible instead of silently ignored. */
export function payloadLine(payload: unknown): string {
  if (payload == null) return ''
  if (typeof payload !== 'object') return String(payload)
  const parts: string[] = []
  for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
    if (value === null || value === undefined || value === '') continue
    if (Array.isArray(value)) {
      parts.push(`${key} ${value.length}`)
    } else if (typeof value === 'object') {
      parts.push(`${key} {...}`)
    } else {
      parts.push(`${key} ${String(value)}`)
    }
  }
  return parts.join(' · ')
}

/**
 * One short line for a timeline entry.
 *
 * `adapter` and `done` carry the worker's whole summary -- thousands of
 * characters. Printing that in the timeline would bury the event it belongs to,
 * so each known event projects just the fields that answer "what happened", and
 * anything unrecognised still falls back to the full payload line.
 */
export function eventSummary(name: string, payload: unknown): string {
  const p = (payload ?? {}) as Record<string, unknown>
  const cap = (value: string, limit = 160): string =>
    value.length > limit ? `${value.slice(0, limit)}…` : value
  switch (name) {
    case 'started':
      return [p.adapter, p.group, p.worktree ? 'worktree' : null].filter(Boolean).join(' · ')
    case 'result_schema':
      if (p.enabled === false) return 'off'
      return String(p.path ?? '').split('/').pop() || '—'
    case 'adapter':
      return [
        p.exit_code != null ? `exit ${p.exit_code}` : null,
        p.degraded ? 'degraded' : null
      ]
        .filter(Boolean)
        .join(' · ')
    case 'verify':
      return [p.status, p.exit_code != null ? `exit ${p.exit_code}` : null]
        .filter(Boolean)
        .join(' · ')
    case 'done':
      return [p.verify, p.files_changed != null ? String(p.files_changed) : null]
        .filter(Boolean)
        .join(' · ')
    case 'failed':
      return cap(String(p.reason ?? p.stage ?? payloadLine(payload)))
    case 'forbidden': {
      const paths = Array.isArray(p.paths) ? (p.paths as string[]).join(', ') : ''
      return cap(paths || payloadLine(payload))
    }
    default:
      return cap(payloadLine(payload))
  }
}

/** Whether a timeline entry marks something going wrong, for the red dot.
 *  A skipped verification is not a failure -- it simply did not run. */
export function isBadEvent(name: string, payload: unknown): boolean {
  const p = (payload ?? {}) as Record<string, unknown>
  if (['failed', 'forbidden', 'blocked', 'timeout', 'cancelled'].includes(name)) return true
  if (name === 'verify') return p.status === 'FAILED'
  if (name === 'adapter') return typeof p.exit_code === 'number' && p.exit_code !== 0
  return false
}
