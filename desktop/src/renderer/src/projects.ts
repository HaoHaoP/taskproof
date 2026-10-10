/**
 * The project-overview page's row model, pulled out of the SFC.
 *
 * Following `matrix.ts` and `shell.ts`, this is plain data in / data out: the
 * page's *decisions* -- how a project's newest activity is picked, how its
 * probe verdict is summed, how a lane with no matching detail record still
 * renders -- are worth pinning without a DOM or a server. The view only wires
 * these rows to markup.
 *
 * Two payloads feed one tree:
 *  - `GET /api/projects?by=project` is the *roster*: one row per project, each
 *    carrying its lanes and a lifecycle `summary` (the same aggregate the
 *    matrix reads),
 *  - `GET /api/projects` is the *detail*: the historical one-row-per-lane view,
 *    where the per-lane task counts, newest activity and probe verdict live.
 *
 * The two are separate requests, so they can disagree at the edges -- a lane in
 * the roster with no detail record (or vice versa) is a real state, not a
 * contrivance. This module joins them by lane id and never drops a lane the
 * roster names (the repository's "unknown is still rendered" rule).
 */
import type { Project, ProjectGroup } from './api/client'

/** The three probe verdicts the API reports (plus a null "never seen"). */
export type Probe = 'passed' | 'failed' | 'none' | null

export interface LaneRow {
  id: string
  /**
   * The concurrency lock. A lane whose registry entry omits it locks on
   * itself, so the missing case is shown as the lane's own id rather than
   * left blank.
   */
  group: string
  path: string
  /** The acceptance command. It can be long; the view truncates it and keeps
   *  the whole string in the cell's title. */
  verify: string | null
  tasks: number
  failed: number
  lastActivity: string | null
  probe: Probe
}

export interface ProjectRow {
  id: string
  path: string
  /** The project's lanes, in roster order. The count is `lanes.length`. */
  lanes: LaneRow[]
  /**
   * Total tasks across the project. Taken from the grouped view's `summary`
   * (summed over its status buckets) rather than re-summed from the lanes: it
   * is the same aggregate the matrix's counts read, so the two cannot drift.
   */
  tasks: number
  /** Non-terminal work -- running + verifying -- the exact set the service's
   *  overview counts as "in progress". */
  inProgress: number
  failed: number
  /** The newest activity across the project's lanes, or null if none ran. */
  lastActivity: string | null
  /**
   * The project's probe verdict: one failing lane marks the whole row failed,
   * else one passing lane makes it passed, else none. A probe the row cannot
   * see ("none" / null) never turns the summary red.
   */
  probe: Probe
}

function probeOf(value: unknown): Probe {
  return value === 'passed' || value === 'failed' || value === 'none' ? value : null
}

/** The newer of two optional ISO stamps. An unparseable stamp loses to a
 *  parseable one; if both parse, the later instant wins (ties keep `a`). */
function newest(a: string | null, b: string | null): string | null {
  if (a === null) return b
  if (b === null) return a
  const ta = Date.parse(a)
  const tb = Date.parse(b)
  if (Number.isNaN(ta)) return b
  if (Number.isNaN(tb)) return a
  return tb > ta ? b : a
}

function totalTasks(summary: Record<string, number>): number {
  return Object.values(summary).reduce((sum, n) => sum + (n || 0), 0)
}

function sumProbe(lanes: LaneRow[]): Probe {
  let passed = false
  for (const lane of lanes) {
    if (lane.probe === 'failed') return 'failed'
    if (lane.probe === 'passed') passed = true
  }
  return passed ? 'passed' : 'none'
}

/**
 * Join the grouped roster with the flat detail into the page's rows. Every
 * project in `groups` becomes one row; every lane it names becomes one child,
 * whether or not a matching detail record exists. A detail the roster does not
 * name is not invented into a row of its own -- the grouped view is the row
 * source, and an unnamed detail has no project to hang from.
 */
export function projectRows(groups: ProjectGroup[], details: Project[]): ProjectRow[] {
  const byId = new Map<string, Project>()
  for (const detail of details) byId.set(detail.id, detail)

  return groups.map((group) => {
    const lanes: LaneRow[] = group.taskgroups.map((lane) => {
      const detail = byId.get(lane.id)
      return {
        id: lane.id,
        // The roster is the lock's authority; a missing lock means "locks on
        // itself", so it is shown as the lane's own id, never blank.
        group: lane.group || lane.id,
        path: detail?.path ?? lane.path,
        verify: detail?.verify ?? lane.verify ?? null,
        tasks: detail?.tasks ?? 0,
        failed: detail?.failed ?? 0,
        lastActivity: detail?.last_activity ?? null,
        probe: probeOf(detail?.probe ?? lane.probe)
      }
    })

    return {
      id: group.id,
      path: group.path,
      lanes,
      tasks: totalTasks(group.summary),
      inProgress: (group.summary.running ?? 0) + (group.summary.verifying ?? 0),
      failed: group.summary.failed ?? 0,
      lastActivity: lanes.reduce<string | null>(
        (latest, lane) => newest(latest, lane.lastActivity),
        null
      ),
      probe: sumProbe(lanes)
    }
  })
}
