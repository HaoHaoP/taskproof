<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TaskDrawer from '../components/TaskDrawer.vue'
import { useBoardStore } from '../stores/board'

const store = useBoardStore()
const { t } = useI18n()
const rows = computed(() => store.projects)
</script>

<template>
  <div class="projects-view">
    <div class="panes">
      <h2>{{ t('nav.projects') }}</h2>
      <p class="sub">{{ t('projects.sub') }}</p>
      <el-table :data="rows" size="small" class="tp-table">
        <el-table-column :label="t('rail.title')" width="150">
          <template #default="scope">
            <span class="mono">{{ scope.row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="path" min-width="320" show-overflow-tooltip>
          <template #default="scope">
            <span class="mono muted">{{ scope.row.path }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="group" width="120" />
        <el-table-column prop="verify_kind" width="110" />
        <el-table-column prop="tasks" width="90" />
        <el-table-column prop="in_progress" width="110" />
        <el-table-column prop="failed" width="90" />
        <el-table-column prop="last_activity" min-width="170">
          <template #default="scope">
            <span class="mono muted">{{ scope.row.last_activity ?? '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <TaskDrawer />
  </div>
</template>

<style scoped>
.projects-view {
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
.mono {
  font-family: var(--mono);
  font-size: 11.5px;
}
.muted {
  color: var(--ink-4);
}
</style>
