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
