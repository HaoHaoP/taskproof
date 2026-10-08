<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusMark from '../components/StatusMark.vue'
import TaskDrawer from '../components/TaskDrawer.vue'
import { useStatusLabel } from '../composables/useStatusLabel'
import { duration } from '../format'
import { useBoardStore } from '../stores/board'
import { useRouter } from 'vue-router'

const store = useBoardStore()
const router = useRouter()
const { t } = useI18n()
const statusLabel = useStatusLabel()

const rows = computed(() => store.tasks)

function open(id: string): void {
  void router.push(`/tasks/${id}`)
}
</script>

<template>
  <div class="tasks-view">
    <div class="panes">
      <h2>{{ t('tasks.all') }}</h2>
      <p class="sub">{{ t('tasks.sub') }}</p>
      <el-table
        :data="rows"
        size="small"
        class="tp-table"
        @row-click="(row: { id: string }) => open(row.id)"
      >
        <el-table-column :label="t('status.label')" width="104">
          <template #default="scope">
            <span class="chip" :data-status="scope.row.status">
              <StatusMark :status="scope.row.status" shape="dot" />
              {{ statusLabel(scope.row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="id" width="184">
          <template #default="scope">
            <span class="mono">{{ scope.row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="project" width="140">
          <template #default="scope">
            <span class="mono muted">{{ scope.row.project }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="brief" min-width="320" show-overflow-tooltip />
        <el-table-column prop="adapter" width="110">
          <template #default="scope">
            <span class="mono muted">{{ scope.row.adapter ?? '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column width="96">
          <template #default="scope">
            <span class="mono muted">
              {{ duration(scope.row.started_at, scope.row.finished_at) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
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
.panes {
  flex: 1;
  overflow: auto;
  padding: 22px 26px 40px;
}
h2 {
  margin: 0;
  font: 600 17px/1.2 var(--sans);
  color: var(--ink);
}
.sub {
  margin: 6px 0 18px;
  font-size: 12.5px;
  color: var(--ink-4);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 500 11px/1 var(--sans);
  color: var(--c);
}
.mono {
  font-family: var(--mono);
  font-size: 11.5px;
}
.muted {
  color: var(--ink-4);
}
.tp-table :deep(.el-table__row) {
  cursor: pointer;
}
</style>
