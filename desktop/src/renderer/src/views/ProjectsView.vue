<script setup lang="ts">
/**
 * Project overview, following the prototype: a page head, then one row per
 * project.
 *
 * Two prototype columns are deliberately absent. The probe pill and the row
 * actions need data and a write path the frozen REST API does not have -- the
 * `probe` field is not in the project payload at all, and editing the registry
 * is the CRUD stage. A column that can only ever render "—" would be a lie.
 */
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
      <div class="pagehead">
        <div>
          <h3>{{ t('projects.title') }}</h3>
          <p class="sub">{{ t('projects.sub') }}</p>
        </div>
      </div>

      <div class="tp-table">
        <el-table :data="rows" style="width: 100%">
          <el-table-column :label="t('projects.col.id')" min-width="150">
            <template #default="scope">
              <span class="mono">{{ scope.row.id }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.group')" width="136">
            <template #default="scope">
              <span class="mono" :class="{ muted: scope.row.group === 'default' }">
                {{ scope.row.group === 'default' ? t('proj.group.default') : scope.row.group }}
              </span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.path')" min-width="230">
            <template #default="scope">
              <span class="mono muted">{{ scope.row.path }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.tasks')" width="72" align="right">
            <template #default="scope">
              <span class="mono">{{ scope.row.tasks }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.flying')" width="72" align="right">
            <template #default="scope">
              <span class="mono">{{ scope.row.in_progress }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.failed')" width="72" align="right">
            <template #default="scope">
              <span class="mono" :class="{ bad: scope.row.failed > 0 }">{{ scope.row.failed }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.last')" width="170">
            <template #default="scope">
              <span class="mono muted">{{ scope.row.last_activity ?? '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
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
.mono.bad {
  color: var(--c-failed);
  font-weight: 600;
}
</style>
