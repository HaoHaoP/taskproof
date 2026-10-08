<script setup lang="ts">
/**
 * All tasks, following the prototype's column set: a status pill, the id, the
 * project, the brief, the adapter and the duration. Clicking a row opens the
 * drawer the same way the matrix does.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TaskDrawer from '../components/TaskDrawer.vue'
import { duration } from '../format'
import { useBoardStore } from '../stores/board'
import { useRouter } from 'vue-router'

const store = useBoardStore()
const router = useRouter()
const { t } = useI18n()

const rows = computed(() => store.tasks)

function open(id: string): void {
  void router.push(`/tasks/${id}`)
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
          style="width: 100%"
          @row-click="(row: { id: string }) => open(row.id)"
        >
          <el-table-column :label="t('status.label')" width="92">
            <template #default="scope">
              <span class="sc" :data-status="scope.row.status">
                {{ t(`status.${scope.row.status}`) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column label="id" width="148">
            <template #default="scope">
              <span class="mono">{{ scope.row.id }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('rail.title')" width="118">
            <template #default="scope">
              <span class="mono muted">{{ scope.row.project }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="brief" :label="t('tasks.col.brief')" min-width="300" class-name="tp-clip" />

          <el-table-column :label="t('tasks.col.adapter')" width="126">
            <template #default="scope">
              <span class="mono muted">{{ scope.row.adapter ?? '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('tasks.col.dur')" width="82" align="right">
            <template #default="scope">
              <span class="mono">{{ duration(scope.row.started_at, scope.row.finished_at) }}</span>
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
