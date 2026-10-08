<script setup lang="ts">
/**
 * Matrix container.
 *
 * Columns are pipeline stages; the last one collects every abnormal terminal
 * state. Cards are presentational and know nothing about the store.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import StatusMark from '../components/StatusMark.vue'
import TaskCard from '../components/TaskCard.vue'
import TaskDrawer from '../components/TaskDrawer.vue'
import type { Task } from '../api/client'
import { COLUMNS } from '../contract'
import { useBoardStore } from '../stores/board'

const store = useBoardStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const projects = computed(() => store.projects.filter((project) => store.isVisible(project.id)))

function tasksIn(projectId: string, columnKey: string): Task[] {
  const grouped = store.tasksByColumn[columnKey] ?? []
  return grouped.filter((task) => task.project === projectId)
}

function countIn(columnKey: string): number {
  return (store.tasksByColumn[columnKey] ?? []).length
}

function isExpanded(id: string): boolean {
  return route.params.taskId === id
}

function openTask(id: string): void {
  void router.push(`/matrix/${id}`)
}
</script>

<template>
  <div class="matrix-view">
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
  grid-template-columns: var(--lane) repeat(5, minmax(var(--col), 1fr));
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
</style>
