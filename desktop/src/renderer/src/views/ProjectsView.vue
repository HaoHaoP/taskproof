<script setup lang="ts">
/**
 * Project overview, following the prototype: a page head, then one row per
 * project. Projects are registered from the CLI (`taskproof register`), so this
 * view is read-only -- it renders exactly what the board poll returns and offers
 * no add / edit / remove controls.
 *
 * One row is a *project*, not a lane: the row is drawn from the grouped
 * (`?by=project`) view and each row expands to the lanes it owns. The join
 * between the grouped roster and the flat per-lane detail -- and every decision
 * about counts, activity and probes -- lives in `projects.ts`; this file only
 * wires the rows to markup and owns the expansion state.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import TaskDrawer from '../components/TaskDrawer.vue'
import { useBoardStore } from '../stores/board'
import { projectRows, type ProjectRow } from '../projects'

const board = useBoardStore()
const { t } = useI18n()

/** One row per project, each with its lane child rows. */
const rows = computed(() => projectRows(board.projectGroups, board.projects))

/** Which projects are open. Expansion is view state, so it stays component-local
 *  -- never the store, and never the address bar. `row-key` + this ref keep a
 *  row open across the board's poll, which hands the table a fresh array. */
const expanded = ref<string[]>([])

function onExpand(_row: ProjectRow, openRows: ProjectRow[]): void {
  expanded.value = openRows.map((row) => row.id)
}
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
        <el-table
          :data="rows"
          style="width: 100%"
          row-key="id"
          :expand-row-keys="expanded"
          @expand-change="onExpand"
        >
          <!-- The lane rows live here: a project row expands to the lanes it
               owns instead of spending a column on a lock the project lacks. -->
          <el-table-column type="expand" width="40">
            <template #default="scope">
              <div class="lanes">
                <el-table :data="scope.row.lanes" style="width: 100%">
                  <el-table-column :label="t('projects.col.lane')" min-width="150">
                    <template #default="lane">
                      <span class="mono">{{ lane.row.id }}</span>
                    </template>
                  </el-table-column>

                  <el-table-column :label="t('projects.col.group')" width="136">
                    <template #default="lane">
                      <span class="mono" :class="{ muted: lane.row.group === 'default' }">
                        {{
                          lane.row.group === 'default' ? t('proj.group.default') : lane.row.group
                        }}
                      </span>
                    </template>
                  </el-table-column>

                  <el-table-column :label="t('projects.col.path')" min-width="210">
                    <template #default="lane">
                      <span class="mono muted">{{ lane.row.path }}</span>
                    </template>
                  </el-table-column>

                  <!-- The acceptance command can be long: clip it, keep the
                       whole string in the title. -->
                  <el-table-column
                    :label="t('projects.col.verify')"
                    min-width="240"
                    class-name="tp-clip"
                  >
                    <template #default="lane">
                      <span class="mono muted" :title="lane.row.verify ?? ''">
                        {{ lane.row.verify ?? '—' }}
                      </span>
                    </template>
                  </el-table-column>

                  <el-table-column :label="t('projects.col.tasks')" width="72" align="right">
                    <template #default="lane">
                      <span class="mono">{{ lane.row.tasks }}</span>
                    </template>
                  </el-table-column>

                  <el-table-column :label="t('projects.col.failed')" width="72" align="right">
                    <template #default="lane">
                      <span class="mono" :class="{ bad: lane.row.failed > 0 }">
                        {{ lane.row.failed }}
                      </span>
                    </template>
                  </el-table-column>

                  <el-table-column :label="t('projects.col.last')" width="170">
                    <template #default="lane">
                      <span class="mono muted">{{ lane.row.lastActivity ?? '—' }}</span>
                    </template>
                  </el-table-column>

                  <el-table-column :label="t('projects.col.probe')" width="112">
                    <template #default="lane">
                      <span class="probe" :class="lane.row.probe ?? 'none'">
                        {{ t('probe.' + (lane.row.probe ?? 'none')) }}
                      </span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.id')" min-width="150">
            <template #default="scope">
              <span class="mono">{{ scope.row.id }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.path')" min-width="230">
            <template #default="scope">
              <span class="mono muted">{{ scope.row.path }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.lanes')" width="72" align="right">
            <template #default="scope">
              <span class="mono">{{ scope.row.lanes.length }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.tasks')" width="72" align="right">
            <template #default="scope">
              <span class="mono">{{ scope.row.tasks }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.flying')" width="72" align="right">
            <template #default="scope">
              <span class="mono">{{ scope.row.inProgress }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.failed')" width="72" align="right">
            <template #default="scope">
              <span class="mono" :class="{ bad: scope.row.failed > 0 }">{{ scope.row.failed }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.last')" width="170">
            <template #default="scope">
              <span class="mono muted">{{ scope.row.lastActivity ?? '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="t('projects.col.probe')" width="112">
            <template #default="scope">
              <span class="probe" :class="scope.row.probe ?? 'none'">
                {{ t('probe.' + (scope.row.probe ?? 'none')) }}
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

/* The expanded project row. Element Plus pads the expanded cell heavily by
   default; strip that padding so the nested lane table sits flush and the
   lanes read as belonging to the row above them. The insets are the row's own,
   on a sunken tone from the token set (never a colour invented here). */
.projects-view :deep(.el-table__expanded-cell) {
  padding: 0;
  background-color: var(--zebra);
}
.lanes {
  padding: 2px 12px 8px 40px;
}
</style>
