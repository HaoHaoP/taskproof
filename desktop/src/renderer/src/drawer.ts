/**
 * The drawer's mount-retry decision, pulled out of `TaskDrawer.vue`.
 *
 * The failure this guards is narrow and permanent: a Vue patch that throws while
 * mounting the `<el-drawer>` subtree leaves the component *alive* -- it has an
 * instance, it emits, its lockscreen class is on `<body>` -- but with no DOM in
 * the document, because `mountElement` builds the element before inserting it
 * and the throw happened in between. Vue believes the subtree is mounted, so no
 * later render ever mounts it again; the drawer stays gone for the life of the
 * page. Keying the drawer by an attempt counter forces Vue to tear the (DOM-less)
 * subtree down and build a fresh one, which retries the mount.
 *
 * This is deliberately plain data in / boolean out so the decision is pinned by
 * a unit test without a DOM; the DOM probe itself lives in the component.
 */
export const DRAWER_MOUNT_RETRIES = 3

export interface DrawerMountState {
  /** Is the drawer supposed to be showing? */
  open: boolean
  /** Did the DOM probe actually find the drawer in the document? */
  mounted: boolean
  /** How many times we have already bumped the key for this open cycle. */
  attempt: number
}

/**
 * Retry only while it can help: the drawer is open, the probe says it is not in
 * the document, and we have attempts left. Closed never retries; already
 * mounted never retries; and the cap stops a mount that always throws from
 * spinning forever.
 */
export function shouldRetryDrawerMount(
  state: DrawerMountState,
  retries: number = DRAWER_MOUNT_RETRIES
): boolean {
  return state.open && !state.mounted && state.attempt < retries
}

/**
 * The `:key` on the drawer. Only a bump changes it, so switching tasks (or any
 * other re-render) keeps the same key and does not remount -- no flicker, and no
 * throwing away the open/close animation.
 */
export function drawerMountKey(attempt: number): string {
  return `drawer-${attempt}`
}

/** The four facts the drawer shows from the dispatch mandate. */
export interface MandateSummary {
  lane: string
  branch: string
  verify: string
  drifted: boolean
}

function mandateText(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value : '—'
}

/**
 * Project the stored mandate JSON to the fields an operator needs. The API's
 * mandate is a twelve-key audit snapshot; pasting it into the drawer would bury
 * the four facts that explain the dispatch. A missing or malformed snapshot
 * yields `null`, so older task rows render no mandate block at all.
 */
export function mandateSummary(
  raw: string | null | undefined,
  events: ReadonlyArray<{ event: string }> = [],
  currentVerify?: string | null
): MandateSummary | null {
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
  const mandate = parsed as Record<string, unknown>
  const verify = typeof mandate.verify === 'string' ? mandate.verify : null
  return {
    lane: mandateText(mandate.lane),
    branch: mandateText(mandate.branch),
    verify: mandateText(verify),
    // Prefer the lane's current command. The event is the fallback when the
    // drawer has no project snapshot (for example, projects failed to load).
    drifted:
      currentVerify !== undefined
        ? verify !== currentVerify
        : events.some((event) => event.event === 'mandate_drift')
  }
}
