<script setup lang="ts">
/**
 * Matrix container.
 *
 * Columns are pipeline stages; the last one collects the failure-like terminal
 * states, while cancellation gets a column of its own. Cards are presentational
 * and know nothing about the store.
 *
 * The board's *reasoning* -- the finished column's window, each column's
 * ordering, the range / project narrowing, and the fetch budget the range
 * needs -- lives in `matrix.ts`. This file only reads the filter off the
 * address bar, mirrors it into the store (which owns the fetch), and wires the
 * answers to markup.
 */
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import StatusMark from '../components/StatusMark.vue'
import TaskCard from '../components/TaskCard.vue'
import TaskDrawer from '../components/TaskDrawer.vue'
import type { Task } from '../api/client'
import { ICONS } from '../icons'
import {
  DONE_WINDOW,
  HIDE_KEY,
  RANGES,
  boardQuery,
  canGrowBudget,
  doneWindow,
  filterBoard,
  gridTracks,
  groupColumns,
  hiddenTally,
  parseBoardFilter,
  visibleColumns,
  visibleProjects,
  type BoardFilter,
  type RangeChoice
} from '../matrix'
import { columnLabelKey } from '../contract'
import { useBoardStore } from '../stores/board'
import { useTasksStore } from '../stores/tasks'
import type { TaskAction } from '../taskmenu'

const store = useBoardStore()
const tasks = useTasksStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

/** The board's filter, read straight off the address bar. */
const filter = computed(() => parseBoardFilter(route.query))

/** Every 项目 (project row) the matrix draws a lane for. This is the *same*
 *  selected set `filterBoard` keeps cards by -- so a project the multi-select
 *  drops loses its row and its cards together, never one without the other. */
const projects = computed(() => visibleProjects(store.projects, filter.value))

/**
 * The status columns (泳道) the board shows: every contract column the address
 * bar has not hidden, in contract order. This is the ONE list the header row,
 * every project's cells and the grid's track count all read, so a hidden column
 * cannot leak cards into a neighbour -- header order and member assignment come
 * from the same array by construction.
 */
const lanes = computed(() => visibleColumns(filter.value))

/** The grid's track list: one lane track, then one per *visible* column. The
 *  count is the visible count -- never a fixed six -- so hiding a column widens
 *  the rest and no hidden column claims a track. */
const gridStyle = computed(() => ({ gridTemplateColumns: gridTracks(lanes.value.length) }))

/** The registry's ids, in order: what "all selected" means. `filter.projects`
 *  is null in that default state, so the multi-select model falls back to this
 *  full list rather than to an empty selection. */
const allProjectIds = computed(() => store.projects.map((project) => project.id))

/** What the multi-select shows as checked. */
const selectedProjects = computed(() => filter.value.projects ?? allProjectIds.value)

/** The narrowed board, grouped and ordered -- the source of every cell. */
const columns = computed(() => groupColumns(filterBoard(store.tasks, filter.value, Date.now())))


/** The finished column's window. The fold bar reads `hidden`; the cell reads
 *  `visible`. */
const done = computed(() => doneWindow(columns.value.done ?? [], filter.value.expanded))

/** The cancelled column gets the same window as the finished column -- both are
 *  terminal, both are read as a recent head, and both share the board's one
 *  fold-bar toggle (`?done=expanded`). Same pure function, not a second copy. */
const cancelled = computed(() => doneWindow(columns.value.cancelled ?? [], filter.value.expanded))

/** How many columns are hidden and how many cards (in hand) went with them --
 *  the number the board row's hint reports. Read from the fetched, filtered
 *  cards, never from a summary: we only ever claim what we actually hold. */
const hidden = computed(() => hiddenTally(filter.value, columns.value))

/** Whether the fetch budget still has room to grow. The capped warning asks
 *  this -- not a second comparison of its own -- before it offers "继续取回":
 *  at the cap `growBudget()` returns without touching the budget, so a button
 *  there would be a promise the click cannot keep. */
const canGrow = computed(() => canGrowBudget(store.fetchBudget))

/** Header counts and cell contents, with the terminal columns already windowed. */
const shown = computed<Record<string, Task[]>>(() => ({
  ...columns.value,
  done: done.value.visible,
  cancelled: cancelled.value.visible
}))

function countIn(columnKey: string): number {
  // The header tallies the whole scope, not the window: a folded column still
  // says how many cards it actually holds.
  return (columns.value[columnKey] ?? []).length
}

function tasksIn(projectId: string, columnKey: string): Task[] {
  return (shown.value[columnKey] ?? []).filter((task) => task.project === projectId)
}

/** The fold control a terminal header draws *inside itself*, read off the one
 *  `?done=expanded` window the board has always used. `null` -- no bar, and so
 *  no reserved space -- whenever the column hides nothing and has nothing to
 *  collapse; the header's own band then closes up with no seam. */
type FoldControl = { mode: 'expand' | 'collapse'; n: number } | null

function foldFor(key: string): FoldControl {
  const win = key === 'done' ? done.value : key === 'cancelled' ? cancelled.value : null
  if (!win) return null
  if (win.hidden > 0) return { mode: 'expand', n: win.hidden }
  if (filter.value.expanded && win.total > DONE_WINDOW) return { mode: 'collapse', n: 0 }
  return null
}

function isExpanded(id: string): boolean {
  return route.params.taskId === id
}

function openTask(id: string): void {
  // Carry the filter / tab query along: a bare path clears the address bar,
  // which is the real reason opening a detail used to lose the filter.
  void router.push({ name: 'matrix', params: { taskId: id }, query: route.query })
}

/** The card menu's actions. Advance / rerun go straight to the store; stop,
 *  accept and delete raise their confirmation sheets first (a write that landed
 *  re-reads the board). `accept` is blocked-only and cannot be undone, so it
 *  goes through the same confirm step as stop / delete. */
function onAction(task: Task, action: TaskAction): void {
  if (action === 'advance') void advance(task)
  else if (action === 'stop') tasks.openStop(task)
  else if (action === 'accept') tasks.openAccept(task)
  else if (action === 'delete') tasks.openDelete(task)
  else if (action === 'rerun') void tasks.openRerun(task)
}

async function advance(task: Task): Promise<void> {
  if (await tasks.advance(task)) await store.refresh()
}

async function reorder(task: Task, seq: number): Promise<void> {
  if (await tasks.patchQueueSeq(task, seq)) await store.refresh()
}

/** Every query key the board itself reads or writes. Anything else (today
 *  `tab`, tomorrow whatever a later feature adds) belongs to another feature
 *  and has to survive a filter change rather than be rebuilt away. */
const BOARD_KEYS = new Set(['range', 'projects', 'project', 'done', HIDE_KEY])

/** Rewrite the board's query, dropping defaults so a default board is `/matrix`
 *  with no query. `push` (not `replace`): the back button has to undo filter
 *  changes, which is the whole point of putting them in the address bar. Keys
 *  the board does not own are carried over untouched -- rebuilding the whole
 *  query from `boardQuery` used to silently drop them. */
function applyFilter(patch: Partial<BoardFilter>): void {
  const next = { ...filter.value, ...patch }
  const produced = Object.fromEntries(new URLSearchParams(boardQuery(next)))
  const query: LocationQueryRaw = {}
  for (const [key, value] of Object.entries(route.query)) {
    if (!BOARD_KEYS.has(key) && value !== undefined) query[key] = value
  }
  Object.assign(query, produced)
  void router.push({ query })
}

function onRange(value: string): void {
  applyFilter({ range: value as RangeChoice })
}

/** Hide one status column. The switch lives in that column's own header, so
 *  "which column" needs no menu -- it is the header you clicked. */
function hideLane(key: string): void {
  applyFilter({ hidden: [...filter.value.hidden, key] })
}

/** Bring every hidden column back. The board row carries this, so a column the
 *  operator swept away is never stranded off-screen. */
function showAllLanes(): void {
  applyFilter({ hidden: [] })
}

/**
 * Write the multi-select's checked set back to the address bar. Checking every
 * project is the default, so it clears the query instead of pinning the full
 * list -- a registry that grows later still reads as "all".
 */
function onProjects(value: string[]): void {
  const all = allProjectIds.value
  const isAll = value.length === all.length && all.every((id) => value.includes(id))
  applyFilter({ projects: isAll ? null : [...value] })
}

/** Already showing "every project"? `null` is the default that also counts
 *  projects registered later, so it is what "全选" means. */
const allProjectsSelected = computed(() => filter.value.projects === null)

/** Already showing "none"? The explicit empty array -- different from the
 *  default, so it is a real, disable-able state of its own. */
const noProjectsSelected = computed(
  () => filter.value.projects !== null && filter.value.projects.length === 0
)

function selectAllProjects(): void {
  applyFilter({ projects: null })
}

function clearProjects(): void {
  applyFilter({ projects: [] })
}

// Keep the store's fetch budget in step with the address bar's range. A change
// resets the budget, so a narrower range never inherits a wider fetch.
watch(filter, (next) => store.setRange(next.range), { immediate: true })
</script>

<template>
  <div class="matrix-view">
    <!-- The matrix row is exactly two controls: 项目 (rows and cards, one set)
         and 范围. Nothing else lives here in the normal state -- in particular
         no "已取回 N 条" readout. -->
    <div class="boardbar">
      <label class="fld">
        <span>{{ t('board.project') }}</span>
        <el-select
          class="sel sel-projects"
          popper-class="sel-projects-popper"
          size="small"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          :model-value="selectedProjects"
          @change="onProjects"
        >
          <!-- All / none, inside the dropdown's own header. Both stop the
               click so the popper stays open: picking "all" is a step in the
               filter, not a dismissal of it. -->
          <template #header>
            <div class="sel-head">
              <button
                type="button"
                :disabled="allProjectsSelected"
                @click.stop.prevent="selectAllProjects"
              >
                {{ t('rail.all') }}
              </button>
              <button
                type="button"
                :disabled="noProjectsSelected"
                @click.stop.prevent="clearProjects"
              >
                {{ t('rail.none') }}
              </button>
            </div>
          </template>
          <el-option
            v-for="project in store.projects"
            :key="project.id"
            :value="project.id"
            :label="project.id"
          />
        </el-select>
      </label>
      <label class="fld">
        <span>{{ t('board.range') }}</span>
        <el-select
          class="sel"
          size="small"
          :model-value="filter.range"
          @change="onRange"
        >
          <el-option v-for="r in RANGES" :key="r" :value="r" :label="t(`board.ranges.${r}`)" />
        </el-select>
      </label>

      <!-- The non-silent half of hiding: a column you swept off the board is
           never silently gone. The hint says how many columns are hidden and
           how many cards went with them, and one click brings them all back.
           It sits in this row, apart from the per-column switches in the
           headers -- it is the undo for the columns, not another filter. -->
      <div class="rest">
        <button
          v-if="hidden.count > 0"
          type="button"
          class="hidden-lanes"
          :title="t('board.showAllLanes')"
          @click="showAllLanes"
        >
          {{ t('board.hiddenLanes', { n: hidden.count, m: hidden.cards }) }}
        </button>

        <!-- Only when the fetch was cut off by the budget: say so, and offer to
             pull an older window rather than leave the reader thinking this is
             all there is. -->
        <div v-if="store.capped" class="cap">
          <span>{{ t('board.capped', { n: store.tasks.length }) }}</span>
          <button
            v-if="canGrow"
            type="button"
            class="grow"
            @click="store.growBudget()"
          >
            {{ t('board.continue') }}
          </button>
          <span v-else class="cap-reached">{{ t('board.capReached') }}</span>
        </div>
      </div>
    </div>

    <!-- A refused spawn (429) changes nothing: the card stays queued at its
         number. Say so, and let it be dismissed -- never show it as a failure. -->
    <div v-if="tasks.notice" class="notice">
      <span>{{ tasks.notice }}</span>
      <button type="button" class="nx" @click="tasks.dismissNotice()">
        {{ t('task.dismiss') }}
      </button>
    </div>

    <div class="matrix">
      <div class="grid" :style="gridStyle">
        <div class="hd corner">{{ t('rail.title') }}</div>
        <div
          v-for="(column, index) in lanes"
          :key="column.key"
          class="hd"
          :class="{ zcol: index % 2 === 1 }"
          :data-status="column.key"
        >
          <span class="lb">
            <StatusMark :status="column.key" shape="dot" />
            {{ t(columnLabelKey(column.key)) }}
          </span>
          <span class="rt">
            <span class="n">{{ countIn(column.key) }}</span>
            <!-- The lane switch: one per header, same shape on every one. It
                 hides *this* column and lives in the header for that reason. -->
            <button
              type="button"
              class="lane-hide"
              :title="t('board.hideLane', { name: t(columnLabelKey(column.key)) })"
              :aria-label="t('board.hideLane', { name: t(columnLabelKey(column.key)) })"
              @click="hideLane(column.key)"
            >
              <span v-html="ICONS.eyeOff" />
            </button>
          </span>

          <!-- The terminal fold bar, *inside* the header so it rides the
               sticky band: it sits directly under this column's label, above
               the first card, and is part of the opaque pinned header for
               hit-testing. Only drawn when this column hides cards (or can be
               collapsed); absent means no bar and no gap. It drives the same
               single `expanded` flag as before -- no second toggle. -->
          <button
            v-if="foldFor(column.key)?.mode === 'expand'"
            type="button"
            class="fold"
            :data-col="column.key"
            @click="applyFilter({ expanded: true })"
          >
            {{ t('board.expand', { n: foldFor(column.key)?.n ?? 0 }) }}
          </button>
          <button
            v-else-if="foldFor(column.key)?.mode === 'collapse'"
            type="button"
            class="fold collapse"
            :data-col="column.key"
            @click="applyFilter({ expanded: false })"
          >
            {{ t('board.collapse') }}
          </button>
        </div>

        <template v-for="project in projects" :key="project.id">
          <div class="lane">
            <div class="name">{{ project.id }}</div>
            <div class="pth">{{ project.path }}</div>
            <div class="tally">
              <span>{{ project.tasks }} {{ t('rail.tasks') }}</span>
              <span v-if="project.in_progress">{{ project.in_progress }} {{ t('tally.flying') }}</span>
              <span v-if="project.failed" class="bad">{{ project.failed }} {{ t('tally.failed') }}</span>
            </div>
          </div>
          <div
            v-for="(column, index) in lanes"
            :key="column.key"
            class="mcell"
            :class="{ zcol: index % 2 === 1 }"
          >
            <TaskCard
              v-for="task in tasksIn(project.id, column.key)"
              :key="task.id"
              :task="task"
              :expanded="isExpanded(task.id)"
              @open="openTask"
              @action="(action: TaskAction) => onAction(task, action)"
              @reorder="(seq: number) => reorder(task, seq)"
            />
            <div v-if="!tasksIn(project.id, column.key).length" class="dash">—</div>
          </div>
        </template>
      </div>
    </div>
    <TaskDrawer />
  </div>
</template>

<style scoped>
.matrix-view {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}
/* The matrix row: the project multi-select and the time range. Both scope the
   whole board, six status columns (泳道) at once; there is no third control in
   the normal state. */
.boardbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 7px 16px;
  border-bottom: 1px solid var(--rule-2);
  font: 12px/1 var(--sans);
  color: var(--ink-3);
}
.boardbar .fld {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.boardbar .sel {
  width: 128px;
}
.boardbar .sel-projects {
  width: 240px;
}
/* The right-hand cluster: the hidden-column undo, then the capped warning.
   Both are notes, not filters, so they ride at the far end of the row rather
   than sitting inline with the two scoping controls. */
.boardbar .rest {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  margin-left: auto;
}
/* The undo for hidden columns: not a filter, an escape hatch. It reads as a
   button because clicking it brings every hidden column back. */
.boardbar .hidden-lanes {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  background: var(--panel);
  color: var(--ink-2);
  font: 11.5px/1 var(--sans);
  cursor: pointer;
}
.boardbar .hidden-lanes:hover {
  background: var(--raise);
}
/* The capped warning is a note, not an alarm: the amber of "incomplete", not
   the red of "failed". While the budget can still rise it carries its own
   "继续取回" so the reader can pull the older window; once the cap is reached
   that button would be a dead click, so the note states the limit instead. */
.boardbar .cap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font: 11.5px/1.2 var(--sans);
  color: var(--c-timeout);
}
.boardbar .cap .grow {
  flex: none;
  padding: 4px 10px;
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  background: var(--panel);
  color: inherit;
  font: 11.5px/1 var(--sans);
  cursor: pointer;
}
.boardbar .cap .grow:hover {
  background: var(--raise);
}
/* The "retry later" strip: a refused spawn is not a failure, so this reads as
   a note, not an alarm -- the amber of "timed out", not the red of "failed". */
.notice {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 16px 0;
  padding: 8px 12px;
  border-radius: var(--r-ctl);
  background: var(--w-timeout);
  color: var(--c-timeout);
  font: 12px/1.4 var(--sans);
}
.notice .nx {
  margin-left: auto;
  flex: none;
  padding: 3px 9px;
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  background: transparent;
  color: inherit;
  font: 11.5px/1 var(--sans);
  cursor: pointer;
}
.notice .nx:hover {
  background: var(--raise);
}
.matrix {
  flex: 1;
  overflow: auto;
  min-width: 0;
  /* No top padding: a scroll container's padding-top is not covered by a
     `top: 0` sticky header, so cards used to scroll through that strip. The
     10px breathing room now lives in `.hd`'s own top padding, under its
     opaque background. */
  padding: 0 0 24px;
}
/* The column count is the *visible* column count -- `grid-template-columns`
   is written from `lanes` (see `gridTracks`), so it rises and falls with the
   show/hide switches. This must never be re-pinned to a literal: a track count
   that disagrees with the header/cell loop pushes each project's lane into the
   next column and the rows interleave, silently. 列数 = 可见列数. */
.grid {
  display: grid;
  align-content: start;
  min-height: 100%;
  padding: 0 10px;
}
.hd {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 18px 10px 9px;
  font: 500 12px/1 var(--sans);
  color: var(--ink-2);
  background: var(--bg);
}
/* The pinned band has to be opaque all the way down to the first card, not
   just to the header's own box: a sliver of card scrolling up between the
   header's lower edge and the first card reads as the header being
   see-through (the TP-card40 穿透). `::after` extends the band across that
   seam and -- because a pseudo-element is hit-tested as the box that owns it
   -- every pixel of the seam answers `.hd` (or the `.fold` it carries) rather
   than a card. `background: inherit` keeps the zebra columns' tint, and the
   band's bottom rule moves here so the seam reads as part of the header. */
.hd::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  height: 10px;
  background: inherit;
  border-bottom: 1px solid var(--rule-2);
}
.hd .lb {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.hd .rt {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
/* The band must answer as the header itself: the label and the tallies are
   decoration, so they do not intercept a hit -- only the hide switch (the one
   control up here) does. This is what makes `elementFromPoint` on any point of
   the band return `.hd`/`.fold` and never a card that scrolled underneath. */
.hd .lb,
.hd .rt {
  pointer-events: none;
}
.hd .rt .lane-hide {
  pointer-events: auto;
}
.hd .rt .lane-hide * {
  pointer-events: none;
}
.hd .n {
  font: 11px/1 var(--mono);
  color: var(--ink-4);
}
/* The per-column hide switch. Same shape in every header, so the row reads as
   one control repeated, not a menu. It is the header's own column it hides. */
.hd .lane-hide {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--ink-4);
  cursor: pointer;
}
.hd .lane-hide:hover {
  border-color: var(--rule);
  background: var(--panel);
  color: var(--ink-2);
}
/* The corner is the lane column's own header, so it is sticky on BOTH axes:
   it rides with the header row vertically and with the lane column
   horizontally. It therefore has to outrank both -- z 4 sits above the
   header's 3 and the lane's 2 -- and carry its own opaque background, so
   neither the first lane cell nor the first status column can show through
   the intersection. The background is the prototype's corner colour (--bg). */
.hd.corner {
  position: sticky;
  top: 0;
  left: 0;
  z-index: 4;
  justify-content: flex-start;
  padding-left: 4px;
  color: var(--ink-3);
  font-size: 11.5px;
  background: var(--bg);
}
/* Column zebra: every other status column carries a faint tint, on both the
   header and the cells, so the band runs the full height and neighbouring
   columns cannot be read into each other. */
.zcol {
  background-color: var(--zebra);
}
.lane {
  position: sticky;
  left: 0;
  z-index: 2;
  padding: 12px 12px 12px 4px;
  background-color: var(--bg);
  border-right: 1px solid var(--rule-2);
  border-bottom: 1px solid var(--rule);
}
.lane .name {
  font: 600 12.5px/1 var(--mono);
  color: var(--ink);
}
.lane .pth {
  margin-top: 5px;
  font: 10.5px/1.35 var(--mono);
  color: var(--ink-4);
  overflow-wrap: anywhere;
}
.lane .tally {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 7px;
  font: 10.5px/1 var(--mono);
  color: var(--ink-3);
}
.lane .tally .bad {
  color: var(--c-failed);
  font-weight: 600;
}
/* Row separator: the lane and the cells each draw their own bottom border, and
   because they share a grid row the two lines meet into one. */
.mcell {
  min-height: 26px;
  padding: 10px 6px;
  border-bottom: 1px solid var(--rule);
}
.mcell .dash {
  padding-top: 2px;
  font: 11px/1 var(--mono);
  color: var(--ink-4);
  opacity: 0.4;
}
/* The fold bars ride *inside* their own column's header, so the sticky band
   carries them: they sit directly under that column's label and stay pinned
   there as the grid scrolls. `flex: 1 0 100%` forces each onto its own
   full-width line underneath the label row; a column that hides nothing draws
   no bar at all, so it leaves no gap. Both columns drive the ONE
   `expanded` flag -- there is no second toggle. */
.fold {
  flex: 1 0 100%;
  margin: 0;
  padding: 9px 10px;
  text-align: left;
  font: 11.5px/1 var(--sans);
  color: var(--accent);
  background: transparent;
  border: 1px dashed var(--rule);
  border-radius: var(--r-card);
  cursor: pointer;
}
.fold:hover {
  background: var(--raise);
}
.fold.collapse {
  color: var(--ink-4);
}
</style>

<!-- The dropdown is teleported to the body, so its header row cannot live in
     the scoped block. Keyed under the popper's own class so no other select
     picks it up. -->
<style>
.sel-projects-popper .sel-head {
  display: flex;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--rule-2);
}
.sel-projects-popper .sel-head button {
  flex: 1;
  font: 11.5px/1 var(--sans);
  color: var(--accent);
  background: var(--panel);
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  padding: 5px 8px;
  cursor: pointer;
}
.sel-projects-popper .sel-head button:hover:not(:disabled) {
  background: var(--raise);
}
.sel-projects-popper .sel-head button:disabled {
  color: var(--ink-4);
  opacity: 0.6;
  cursor: default;
}
</style>
