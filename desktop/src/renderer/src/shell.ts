/**
 * The shell's body-placeholder decision, pulled out of `App.vue`.
 *
 * The rule the empty state got wrong: a placeholder may only ever cover the
 * *matrix body*. It must never swallow the nav, nor the projects / tasks pages
 * -- with an empty registry the projects page is the only place a first project
 * can be registered, so blanking it out locked the user out of the very flow
 * that would un-empty the app.
 *
 * Keeping this as plain data in / data out (rather than a computed buried in the
 * SFC) is what lets the decision be pinned by a unit test without a DOM; the
 * prototype port had it as a full-page `v-if`, which is exactly the bug.
 */
export type ShellPlaceholder = 'offline' | 'empty' | null

export interface ShellState {
  /** Is the local service reachable? */
  connected: boolean
  /** How many projects the registry reports. */
  projectCount: number
  /** The last connection failure, if any -- distinguishes "offline" from a service that is merely still coming up. */
  lastError: string | null
  /** The current route's name (`matrix`, `projects`, ...). */
  routeName: string | null
}

export function shellPlaceholder(state: ShellState): ShellPlaceholder {
  // Only the matrix body ever gives way. Every other view keeps its real layout
  // in every state, so the nav is never the only thing left to see.
  if (state.routeName !== 'matrix') return null
  if (state.connected) return state.projectCount === 0 ? 'empty' : null
  return state.lastError ? 'offline' : null
}
