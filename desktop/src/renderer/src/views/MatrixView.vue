<script setup lang="ts">
/**
 * Matrix container.
 *
 * Columns are pipeline stages; the last one collects the failure-like terminal
 * states, while cancellation gets a column of its own. Cards are presentational
 * and know nothing about the store.
 *
 * The board's *reasoning* -- each column's window and cap, its ordering, the
 * per-column unfold set, the range / project narrowing, and the fetch budget
 * the range needs -- lives in `matrix.ts`. This file only reads the filter off the
 * address bar, mirrors it into the store (which owns the fetch), and wires the
 * answers to markup.
 */
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import StatusMark from '../components/StatusMark.vue'
import TaskCard from '../components/TaskCard.vue'
import TaskDrawer from '../components/TaskDrawer.vue'
import type { ProjectGroup, Task } from '../api/client'
import { ICONS } from '../icons'
import {
  DEFAULT_CAPS,
  HIDE_KEY,
  RANGES,
  boardQuery,
  canGrowBudget,
  capChipLabel,
  capMenuFor,
  columnWindow,
  filterBoard,
  gridTracks,
  groupColumns,
  hiddenTally,
  owningProject,
  parseBoardFilter,
  visibleColumns,
  visibleProjects,
  withColumnOpen,
  type BoardFilter,
  type CapMenu,
  type ColumnWindow,
  type MatrixLabel,
  type RangeChoice
} from '../matrix'
import { COLUMNS, columnLabelKey } from '../contract'
import { useBoardStore } from '../stores/board'
import { useSettingsStore } from '../stores/settings'

const store = useBoardStore()
const settings = useSettingsStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

/** The board's filter, read straight off the address bar. */
const filter = computed(() => parseBoardFilter(route.query))

/** Every project row the matrix draws. This is the *same* selected set
 *  `filterBoard` keeps cards by -- so a project the multi-select drops loses
 *  its row and its cards together, never one without the other. The rows come
 *  from the grouped (D2 shape C) view: one row per project, its lanes nested. */
const projects = computed(() => visibleProjects(store.projectGroups, filter.value))

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

/** The registry's project ids, in order: what "all selected" means.
 *  `filter.projects` is null in that default state, so the multi-select model
 *  falls back to this full list rather than to an empty selection. The values
 *  (and so the whole "all / none / selected N" arithmetic) are project ids. */
const allProjectIds = computed(() => store.projectGroups.map((group) => group.id))

/** What the multi-select shows as checked. */
const selectedProjects = computed(() => filter.value.projects ?? allProjectIds.value)

/** The narrowed board, grouped and ordered -- the source of every cell. The
 *  fourth argument is the lane -> project map: a task row's `project` column
 *  is a *lane* id, so `filterBoard` and `tasksIn` below must route it through
 *  the registry to know which project row it belongs under. */
const columns = computed(() =>
  groupColumns(filterBoard(store.tasks, filter.value, Date.now(), store.laneProject))
)


/** One column's display cap, from App settings with the code default as the
 *  backstop. `0` means "do not fold". */
function capFor(key: string): number {
  return settings.settings.columnCaps[key] ?? DEFAULT_CAPS[key] ?? 0
}

/** Every column's window, keyed by column. The chip and menu read `hidden` /
 *  `total`; the cell reads `visible`. Computed once per column so the template
 *  does not re-slice inside each `v-if`. */
const windows = computed<Record<string, ColumnWindow>>(() => {
  const out: Record<string, ColumnWindow> = {}
  for (const column of COLUMNS) {
    const expanded = filter.value.open.includes(column.key)
    out[column.key] = columnWindow(columns.value[column.key] ?? [], expanded, capFor(column.key))
  }
  return out
})

/** The chip copy each column draws, including the empty-column state. */
const capChips = computed<Record<string, MatrixLabel>>(() => {
  const out: Record<string, MatrixLabel> = {}
  for (const column of COLUMNS) {
    out[column.key] = capChipLabel(
      windows.value[column.key],
      capFor(column.key),
      filter.value.open.includes(column.key)
    )
  }
  return out
})

/** The fixed choices and state-dependent action each column's menu draws. */
const capMenus = computed<Record<string, CapMenu>>(() => {
  const out: Record<string, CapMenu> = {}
  for (const column of COLUMNS) {
    out[column.key] = capMenuFor(
      windows.value[column.key],
      capFor(column.key),
      filter.value.open.includes(column.key)
    )
  }
  return out
})

/** How many columns are hidden and how many cards (in hand) went with them --
 *  the number the board row's hint reports. Read from the fetched, filtered
 *  cards, never from a summary: we only ever claim what we actually hold. */
const hidden = computed(() => hiddenTally(filter.value, columns.value))

/** Whether the fetch budget still has room to grow. The capped warning asks
 *  this -- not a second comparison of its own -- before it offers "继续取回":
 *  at the cap `growBudget()` returns without touching the budget, so a button
 *  there would be a promise the click cannot keep. */
const canGrow = computed(() => canGrowBudget(store.fetchBudget))

/** Header counts and cell contents, with every column already windowed. */
const shown = computed<Record<string, Task[]>>(() => {
  const out: Record<string, Task[]> = { ...columns.value }
  for (const column of COLUMNS) out[column.key] = windows.value[column.key].visible
  return out
})

function tasksIn(projectId: string, columnKey: string): Task[] {
  // A task's own `project` column is the lane, not the owning project: file it
  // under the project row the registry maps its lane to, and nowhere else.
  return (shown.value[columnKey] ?? []).filter(
    (task) => owningProject(task, store.laneProject) === projectId
  )
}

/** How many lanes a project row carries. A single-lane project (the
 *  uncollected-registry case) reports 1 -- the row still reads as its own lane. */
function laneCount(group: ProjectGroup): number {
  return group.taskgroups.length
}

/** The project's total card count: the grouped view's status summary summed.
 *  Same aggregate the per-lane row used to carry on its own. */
function groupTasks(group: ProjectGroup): number {
  return Object.values(group.summary).reduce((sum, n) => sum + (n || 0), 0)
}

/** In-flight across the project's lanes (running + verifying). */
function groupFlying(group: ProjectGroup): number {
  return (group.summary.running ?? 0) + (group.summary.verifying ?? 0)
}

/** Failure-like terminals across the project's lanes (failed + timeout). */
function groupFailed(group: ProjectGroup): number {
  return (group.summary.failed ?? 0) + (group.summary.timeout ?? 0)
}

/** The row's tooltip: the registered aliases. The visible name stays the id --
 *  aliases are a lookup aid, not the row's identity. Empty when there are none,
 *  so the attribute is simply absent. */
function aliasHint(group: ProjectGroup): string {
  return group.aliases.join(', ')
}

/** Unfold one column past its window -- `done` and `cancelled` move
 *  independently now, so the click names the column it belongs to. */
function openColumn(key: string): void {
  applyFilter({ open: withColumnOpen(filter.value.open, key, true) })
}

/** Fold one column back to its cap. */
function closeColumn(key: string): void {
  applyFilter({ open: withColumnOpen(filter.value.open, key, false) })
}

/** One dropdown command: a fixed cap value, or the current column's fold /
 *  unfold action. The menu never offers an action its pure decision did not
 *  produce, so this handler cannot repeat that state logic. */
function onCapCommand(key: string, command: unknown): void {
  if (command === 'expand') {
    openColumn(key)
    return
  }
  if (command === 'collapse') {
    closeColumn(key)
    return
  }
  if (typeof command === 'number') settings.setColumnCap(key, command)
}

function isExpanded(id: string): boolean {
  return route.params.taskId === id
}

function openTask(id: string): void {
  // Carry the filter / tab query along: a bare path clears the address bar,
  // which is the real reason opening a detail used to lose the filter.
  void router.push({ name: 'matrix', params: { taskId: id }, query: route.query })
}

/** Every query key the board itself reads or writes. Anything else (today
 *  `tab`, tomorrow whatever a later feature adds) belongs to another feature
 *  and has to survive a filter change rather than be rebuilt away. */
const BOARD_KEYS = new Set(['range', 'projects', 'project', 'done', 'open', HIDE_KEY])

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
            v-for="group in store.projectGroups"
            :key="group.id"
            :value="group.id"
            :label="group.id"
          >
            <!-- The visible name is the project id; aliases ride a tooltip. -->
            <span :title="aliasHint(group) || undefined">{{ group.id }}</span>
          </el-option>
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

          <!-- The per-column control band, *inside* the header so it rides the
               sticky band. The chip is the whole second line: its text states
               what the column is showing, and the dropdown holds the fixed cap
               choices plus any current fold / unfold action. It is a real
               control, so both the chip and its commands stop propagation. -->
          <div class="hdctl">
            <el-dropdown
              class="cap-dd"
              trigger="click"
              placement="bottom-end"
              popper-class="cap-menu-popper"
              :teleported="true"
              @command="(value) => onCapCommand(column.key, value)"
            >
              <button
                type="button"
                class="cap-chip"
                :data-col="column.key"
                :title="t('board.capMenu.title')"
                @click.stop
                @dblclick.stop
              >
                <span class="cap-chip-label">
                  {{ t(capChips[column.key].key, capChips[column.key].params) }}
                </span>
                <span class="cap-caret" aria-hidden="true">▾</span>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item disabled class="cap-menu-title">
                    {{ t('board.capMenu.title') }}
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-for="option in capMenus[column.key].options"
                    :key="option.value"
                    :command="option.value"
                  >
                    <span class="cap-option-label">
                      {{ t(option.label.key, option.label.params) }}
                    </span>
                    <span v-if="option.checked" class="cap-check" aria-hidden="true">✓</span>
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-for="action in capMenus[column.key].actions"
                    :key="action.kind"
                    divided
                    :command="action.kind"
                    :class="`cap-action cap-action-${action.kind}`"
                  >
                    {{ t(action.label.key, action.label.params) }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <template v-for="group in projects" :key="group.id">
          <div class="lane">
            <!-- The row is a *project*: its id names it, aliases ride a tooltip,
                 and the lane count says how many lanes sit inside it. -->
            <div class="name" :title="aliasHint(group) || undefined">{{ group.id }}</div>
            <div class="pth">{{ group.path }}</div>
            <div class="tally">
              <span>{{ laneCount(group) }} {{ t('rail.lanes') }}</span>
              <span>{{ groupTasks(group) }} {{ t('rail.tasks') }}</span>
              <span v-if="groupFlying(group)">{{ groupFlying(group) }} {{ t('tally.flying') }}</span>
              <span v-if="groupFailed(group)" class="bad">{{ groupFailed(group) }} {{ t('tally.failed') }}</span>
            </div>
          </div>
          <div
            v-for="(column, index) in lanes"
            :key="column.key"
            class="mcell"
            :class="{ zcol: index % 2 === 1 }"
          >
            <TaskCard
              v-for="task in tasksIn(group.id, column.key)"
              :key="task.id"
              :task="task"
              :expanded="isExpanded(task.id)"
              @open="openTask"
            />
            <div v-if="!tasksIn(group.id, column.key).length" class="dash">—</div>
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
/* The band must answer as the header itself: the label and tally are
   decoration, so they do not intercept a hit -- only the hide switch does. The
   chip is a real control in `.hdctl`, not part of this decoration layer. */
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
/* The per-column control band: the chip is the only thing on this full-width
   line under the label row, so the header keeps one self-describing number. */
.hdctl {
  flex: 1 0 100%;
  display: flex;
  align-items: center;
  min-width: 0;
}
.cap-dd {
  display: block;
  width: 100%;
  min-width: 0;
}
.cap-dd :deep(.el-tooltip__trigger) {
  display: block;
  width: 100%;
  min-width: 0;
}
/* Every column's chip. Its own click stops, but the Element Plus trigger still
   sees the same click and opens the menu. */
.cap-chip {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-width: 0;
  padding: 8px 9px;
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  background: var(--panel);
  color: var(--ink-2);
  font: 11.5px/1 var(--sans);
  text-align: left;
  cursor: pointer;
}
.cap-chip:hover,
.cap-chip:focus-visible {
  border-color: var(--rule-2);
  background: var(--raise);
  color: var(--ink);
}
.cap-chip-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cap-caret {
  flex: none;
  color: var(--ink-4);
  font-size: 9px;
  transform: translateY(-0.5px);
}
</style>

<!-- These poppers are teleported to the body, so their content cannot live in
     the scoped block. Each rule is keyed under that popper's own class. -->
<style>
.cap-menu-popper {
  min-width: 176px;
}
.cap-menu-popper .el-dropdown-menu__item {
  justify-content: space-between;
  gap: 16px;
  min-height: 30px;
  padding: 7px 10px;
  font: 12px/1.2 var(--sans);
}
.cap-menu-popper .el-dropdown-menu__item.cap-menu-title {
  color: var(--ink-4);
  font-size: 10.5px;
  cursor: default;
}
.cap-menu-popper .el-dropdown-menu__item.cap-action {
  color: var(--accent);
}
.cap-menu-popper .cap-check {
  flex: none;
  color: var(--accent);
  font-weight: 700;
}
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
