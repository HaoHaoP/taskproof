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
import { useRoute, useRouter } from 'vue-router'
import StatusMark from '../components/StatusMark.vue'
import TaskCard from '../components/TaskCard.vue'
import TaskDrawer from '../components/TaskDrawer.vue'
import type { Task } from '../api/client'
import { COLUMNS } from '../contract'
import {
  DONE_WINDOW,
  MAX_BUDGET,
  RANGES,
  boardQuery,
  doneWindow,
  filterBoard,
  groupColumns,
  parseBoardFilter,
  type BoardFilter,
  type RangeChoice
} from '../matrix'
import { useBoardStore } from '../stores/board'

const store = useBoardStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

/** The board's filter, read straight off the address bar. */
const filter = computed(() => parseBoardFilter(route.query))

/** Every project the matrix draws a lane for: visible in the toolbar, and, when
 *  a board-level project is chosen, that one alone. */
const projects = computed(() =>
  store.projects.filter(
    (project) =>
      store.isVisible(project.id) &&
      (filter.value.project === null || project.id === filter.value.project)
  )
)

/** The narrowed board, grouped and ordered -- the source of every cell. */
const columns = computed(() => groupColumns(filterBoard(store.tasks, filter.value, Date.now())))

/** The finished column's window. The fold bar reads `hidden`; the cell reads
 *  `visible`. */
const done = computed(() => doneWindow(columns.value.done ?? [], filter.value.expanded))

/** The cancelled column gets the same window as the finished column -- both are
 *  terminal, both are read as a recent head, and both share the board's one
 *  fold-bar toggle (`?done=expanded`). Same pure function, not a second copy. */
const cancelled = computed(() => doneWindow(columns.value.cancelled ?? [], filter.value.expanded))

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

function isExpanded(id: string): boolean {
  return route.params.taskId === id
}

function openTask(id: string): void {
  void router.push(`/matrix/${id}`)
}

/** Rewrite the board's query, dropping defaults so a default board is `/matrix`
 *  with no query. `push` (not `replace`): the back button has to undo filter
 *  changes, which is the whole point of putting them in the address bar. */
function applyFilter(patch: Partial<BoardFilter>): void {
  const next = { ...filter.value, ...patch }
  void router.push({ query: Object.fromEntries(new URLSearchParams(boardQuery(next))) })
}

function onRange(value: string): void {
  applyFilter({ range: value as RangeChoice })
}

function onProject(value: string): void {
  applyFilter({ project: value || null })
}

// Keep the store's fetch budget in step with the address bar's range. A change
// resets the budget, so a narrower range never inherits a wider fetch.
watch(filter, (next) => store.setRange(next.range), { immediate: true })
</script>

<template>
  <div class="matrix-view">
    <div class="boardbar">
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
      <label class="fld">
        <span>{{ t('board.project') }}</span>
        <el-select
          class="sel"
          size="small"
          :model-value="filter.project ?? ''"
          @change="onProject"
        >
          <el-option value="" :label="t('board.allProjects')" />
          <el-option
            v-for="project in store.projects"
            :key="project.id"
            :value="project.id"
            :label="project.id"
          />
        </el-select>
      </label>
      <span class="fetched">{{ t('board.fetched', { n: store.tasks.length }) }}</span>
      <span v-if="store.capped" class="cap">{{ t('board.capped', { n: MAX_BUDGET }) }}</span>
    </div>

    <div class="matrix">
      <div class="grid">
        <div class="hd corner">{{ t('rail.title') }}</div>
        <div
          v-for="(column, index) in COLUMNS"
          :key="column.key"
          class="hd"
          :class="{ zcol: index % 2 === 1 }"
          :data-status="column.key"
        >
          <span class="lb">
            <StatusMark :status="column.key" shape="dot" />
            {{ t(`status.${column.key}`) }}
          </span>
          <span class="n">{{ countIn(column.key) }}</span>
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
            v-for="(column, index) in COLUMNS"
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
            />
            <div v-if="!tasksIn(project.id, column.key).length" class="dash">—</div>
          </div>
        </template>

        <!-- The terminal columns' fold bars: one trailing grid row, pinned under
             the done column and under the cancelled column so each reads as the
             foot of its own lane. Both drive the board's single fold toggle. -->
        <button
          v-if="done.hidden > 0"
          type="button"
          class="fold"
          data-col="done"
          @click="applyFilter({ expanded: true })"
        >
          {{ t('board.expand', { n: done.hidden }) }}
        </button>
        <button
          v-else-if="filter.expanded && done.total > DONE_WINDOW"
          type="button"
          class="fold collapse"
          data-col="done"
          @click="applyFilter({ expanded: false })"
        >
          {{ t('board.collapse') }}
        </button>
        <button
          v-if="cancelled.hidden > 0"
          type="button"
          class="fold"
          data-col="cancelled"
          @click="applyFilter({ expanded: true })"
        >
          {{ t('board.expand', { n: cancelled.hidden }) }}
        </button>
        <button
          v-else-if="filter.expanded && cancelled.total > DONE_WINDOW"
          type="button"
          class="fold collapse"
          data-col="cancelled"
          @click="applyFilter({ expanded: false })"
        >
          {{ t('board.collapse') }}
        </button>
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
/* The board filter: the two dimensions (project, time range) plus the honest
   fetch readout. It scopes the whole board, six columns at once. */
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
.boardbar .fetched {
  font: 11.5px/1 var(--mono);
  color: var(--ink-2);
}
.boardbar .cap {
  font: 11.5px/1 var(--sans);
  color: var(--c-failed);
}
.matrix {
  flex: 1;
  overflow: auto;
  min-width: 0;
  padding: 10px 0 24px;
}
/* The column count here must equal COLUMNS.length -- if it does not, each
   project's lane gets pushed into the next column and the rows interleave,
   silently. */
.grid {
  display: grid;
  grid-template-columns: var(--lane) repeat(6, minmax(var(--col), 1fr));
  align-content: start;
  min-height: 100%;
  padding: 0 10px;
}
.hd {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 8px 10px 9px;
  font: 500 12px/1 var(--sans);
  color: var(--ink-2);
  background: var(--bg);
  border-bottom: 1px solid var(--rule-2);
}
.hd .lb {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.hd .n {
  font: 11px/1 var(--mono);
  color: var(--ink-4);
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
/* The fold bars sit in their own trailing row: the done lane is grid column 5
   and the cancelled lane is 6 (the lane is 1, then the six status columns
   2..7). Both drive the same `expanded` flag. */
.fold {
  grid-column: 5;
  margin: 0 6px;
  padding: 9px 10px;
  text-align: left;
  font: 11.5px/1 var(--sans);
  color: var(--accent);
  background: transparent;
  border: 1px dashed var(--rule);
  border-radius: var(--r-card);
  cursor: pointer;
}
.fold[data-col='cancelled'] {
  grid-column: 6;
}
.fold:hover {
  background: var(--raise);
}
.fold.collapse {
  color: var(--ink-4);
}
</style>
