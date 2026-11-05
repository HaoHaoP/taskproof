<script setup lang="ts">
/**
 * All tasks: status, human disposition, id, project, brief, adapter and
 * duration. Clicking a row opens the drawer the same way the matrix does.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TaskDrawer from '../components/TaskDrawer.vue'
import { dispositionText, duration } from '../format'
import { useBoardStore } from '../stores/board'
import { useRoute, useRouter } from 'vue-router'

const store = useBoardStore()
const router = useRouter()
const route = useRoute()
const { t, te } = useI18n()

const rows = computed(() => store.tasks)

/** Status, DISPO, id, project, brief, adapter, duration. */
const TASK_COLUMN_WIDTHS = ['10%', '14%', '14%', '13%', '30%', '11%', '8%'] as const
const tableStyle = {
  width: '100%',
  '--task-col-status': TASK_COLUMN_WIDTHS[0],
  '--task-col-dispo': TASK_COLUMN_WIDTHS[1],
  '--task-col-id': TASK_COLUMN_WIDTHS[2],
  '--task-col-project': TASK_COLUMN_WIDTHS[3],
  '--task-col-brief': TASK_COLUMN_WIDTHS[4],
  '--task-col-adapter': TASK_COLUMN_WIDTHS[5],
  '--task-col-duration': TASK_COLUMN_WIDTHS[6]
}

function reasonTitle(value: string | null | undefined): string | undefined {
  return value?.trim() || undefined
}

function open(id: string): void {
  // Keep the filter / tab query intact: a bare path drops everything the
  // address bar was carrying, which is how opening a row used to lose the filter.
  void router.push({ name: 'tasks', params: { taskId: id }, query: route.query })
}
</script>

<template>
  <div class="tasks-view">
    <div class="panes">
      <h3>{{ t('tasks.title') }}</h3>
      <p class="sub">{{ t('tasks.sub') }}</p>

      <!-- The list is bounded by a fetch budget, and that must never be silent:
           say how many rows are in hand against how many exist, and let the
           reader pull more. -->
      <div class="taken">
        <span>{{ t('board.taken', { n: store.tasks.length, m: store.total }) }}</span>
        <button
          v-if="store.tasks.length < store.total"
          type="button"
          @click="store.growBudget()"
        >
          {{ t('board.takeMore') }}
        </button>
      </div>

      <div class="tp-table">
        <el-table
          :data="rows"
          :style="tableStyle"
          @row-click="(row: { id: string }) => open(row.id)"
        >
          <el-table-column :label="t('status.label')" class-name="tp-clip">
            <template #default="scope">
              <span
                class="sc"
                :data-status="scope.row.status"
                :title="t(`status.${scope.row.status}`)"
              >
                {{ t(`status.${scope.row.status}`) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column :label="t('tasks.col.dispo')" class-name="tp-clip">
            <template #default="scope">
              <span
                class="mono"
                :data-disposition="scope.row.disposition"
                :title="reasonTitle(scope.row.disposition_reason)"
              >
                {{ dispositionText(scope.row.disposition, t, te) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column label="id" class-name="tp-clip">
            <template #default="scope">
              <span class="mono" :title="scope.row.id">{{ scope.row.id }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('rail.title')" class-name="tp-clip">
            <template #default="scope">
              <span class="mono muted" :title="scope.row.project">{{ scope.row.project }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('tasks.col.brief')" class-name="tp-clip">
            <template #default="scope">
              <span :title="scope.row.brief">{{ scope.row.brief }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('tasks.col.adapter')" class-name="tp-clip">
            <template #default="scope">
              <span class="mono muted" :title="scope.row.adapter ?? '—'">
                {{ scope.row.adapter ?? '—' }}
              </span>
            </template>
          </el-table-column>

          <el-table-column :label="t('tasks.col.dur')" align="right" class-name="tp-clip">
            <template #default="scope">
              <span
                class="mono"
                :title="duration(scope.row.started_at, scope.row.finished_at)"
              >
                {{ duration(scope.row.started_at, scope.row.finished_at) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    <TaskDrawer />
  </div>
</template>

<style scoped>
.tasks-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.tp-table :deep(.el-table__row) {
  cursor: pointer;
}
.tp-table :deep(.el-table__header),
.tp-table :deep(.el-table__body) {
  width: 100% !important;
  table-layout: fixed !important;
}
.tp-table :deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* Element Plus parses column props as pixels, so responsive percentages live
   on the generated col elements; the sum is exactly 100% and never scrolls. */
.tp-table :deep(colgroup > col:nth-child(1)) {
  width: var(--task-col-status) !important;
}
.tp-table :deep(colgroup > col:nth-child(2)) {
  width: var(--task-col-dispo) !important;
}
.tp-table :deep(colgroup > col:nth-child(3)) {
  width: var(--task-col-id) !important;
}
.tp-table :deep(colgroup > col:nth-child(4)) {
  width: var(--task-col-project) !important;
}
.tp-table :deep(colgroup > col:nth-child(5)) {
  width: var(--task-col-brief) !important;
}
.tp-table :deep(colgroup > col:nth-child(6)) {
  width: var(--task-col-adapter) !important;
}
.tp-table :deep(colgroup > col:nth-child(7)) {
  width: var(--task-col-duration) !important;
}
.taken {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 2px 0 10px;
  font: 11.5px/1 var(--mono);
  color: var(--ink-3);
}
.taken button {
  font: 11.5px/1 var(--sans);
  color: var(--accent);
  background: var(--panel);
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  padding: 5px 10px;
  cursor: pointer;
}
.taken button:hover {
  background: var(--raise);
}
</style>
