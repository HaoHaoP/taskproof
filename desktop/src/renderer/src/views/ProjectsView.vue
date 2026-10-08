<script setup lang="ts">
/**
 * Project overview, following the prototype: a page head with an "Add project"
 * button, then one row per project, then the three editor sheets.
 *
 * The reasoning (hash handshake, conflict handling, which failure maps to
 * which copy) lives in `stores/projects`; this component only arranges the
 * prototype's markup. After a write it asks the board to re-read the list --
 * nothing is stitched together locally.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TaskDrawer from '../components/TaskDrawer.vue'
import { ICONS } from '../icons'
import { useBoardStore } from '../stores/board'
import { useProjectsStore } from '../stores/projects'
import type { Project } from '../api/client'

const board = useBoardStore()
const projects = useProjectsStore()
const { t } = useI18n()
const rows = computed(() => board.projects)

/** A successful write re-reads the registry rather than patching the row. */
async function refetch(): Promise<void> {
  await board.refresh()
}

async function register(): Promise<void> {
  if (await projects.register()) await refetch()
}

async function save(): Promise<void> {
  if (await projects.save()) await refetch()
}

async function remove(): Promise<void> {
  if (await projects.remove()) await refetch()
}

async function reloadFile(): Promise<void> {
  projects.reloadFile()
  await refetch()
}

async function keepEdits(): Promise<void> {
  if (await projects.keepEdits()) await refetch()
}

function openEdit(row: Project): void {
  projects.openEdit(row)
}

function openRemove(row: Project): void {
  projects.openRemove(row)
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
        <el-button class="btn-primary" @click="projects.openAdd()">{{ t('proj.add') }}</el-button>
      </div>

      <!-- Only while a 409 is in flight: the registry changed under us. -->
      <div class="conflict" v-if="projects.conflict">
        <span>{{ t('proj.conflict') }}</span><span class="sp"></span>
        <el-button size="small" @click="reloadFile">{{ t('proj.reload') }}</el-button>
        <el-button size="small" class="btn-danger" @click="keepEdits">{{ t('proj.keep') }}</el-button>
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

          <el-table-column :label="t('projects.col.probe')" width="112">
            <template #default="scope">
              <span class="probe" :class="scope.row.probe ?? 'none'">
                {{ t('probe.' + (scope.row.probe ?? 'none')) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column :label="t('proj.actions')" width="92" align="right">
            <template #default="scope">
              <button
                class="ricon"
                type="button"
                :title="t('proj.edit')"
                :aria-label="t('proj.edit')"
                @click.stop="openEdit(scope.row)"
                v-html="ICONS.pencil"
              ></button>
              <button
                class="ricon danger"
                type="button"
                :title="t('proj.remove')"
                :aria-label="t('proj.remove')"
                @click.stop="openRemove(scope.row)"
                v-html="ICONS.trash"
              ></button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 新增项目：路径 → 探测（等价 taskproof register --dry-run）→ 登记 -->
    <el-dialog v-model="projects.addOpen" class="sheet" width="580" append-to-body>
      <template #header><span>{{ t('proj.add') }}</span></template>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.path') }}</div>
          <div class="d">{{ t('proj.path.d') }}</div>
        </div>
        <div class="ctl wide">
          <el-input v-model="projects.draft.path" size="small" placeholder="/absolute/path/to/repo" />
        </div>
      </div>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.detect') }}</div>
          <div class="d">{{ t('proj.detect.d') }}</div>
        </div>
        <div class="ctl">
          <el-button size="small" :disabled="projects.detecting" @click="projects.detect()">
            {{ projects.detecting ? t('proj.detecting') : t('proj.detect.run') }}
          </el-button>
        </div>
      </div>
      <template v-if="projects.draft.detected">
        <div class="setrow">
          <div class="lab"><div class="t">{{ t('projects.col.id') }}</div></div>
          <div class="ctl"><span class="ro">{{ projects.draft.id }}</span></div>
        </div>
        <div class="setrow">
          <div class="lab"><div class="t">{{ t('proj.group') }}</div></div>
          <div class="ctl"><span class="ro">{{ projects.draft.group }}</span></div>
        </div>
        <div class="setrow">
          <div class="lab"><div class="t">{{ t('proj.verify') }}</div></div>
          <div class="ctl wide">
            <span class="ro">{{ projects.draft.verify || t('proj.verify.none') }}</span>
          </div>
        </div>
        <div class="setrow">
          <div class="lab"><div class="t">{{ t('proj.forbidden') }}</div></div>
          <div class="ctl wide"><span class="ro">{{ projects.draft.forbidden || '—' }}</span></div>
        </div>
        <div class="setrow">
          <div class="lab"><div class="t">{{ t('proj.probe') }}</div></div>
          <div class="ctl">
            <span class="probe" :class="projects.draft.probe ?? 'none'">
              {{ t('probe.' + (projects.draft.probe ?? 'none')) }}
            </span>
          </div>
        </div>
      </template>
      <p v-if="projects.error" class="err">{{ projects.error }}</p>
      <p class="hint">{{ t('proj.add.hint') }}</p>
      <template #footer>
        <el-button size="small" @click="projects.closeAdd()">{{ t('dlg.cancel') }}</el-button>
        <el-button
          size="small"
          class="btn-primary"
          :disabled="!projects.draft.detected || projects.busy"
          @click="register"
        >
          {{ projects.busy ? t('proj.writing') : t('proj.register') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑项目：id 与路径不可改（改了等于换了项目，历史任务会挂空） -->
    <el-dialog v-model="projects.editOpen" class="sheet" width="640">
      <template #header><span>{{ t('proj.edit') }} · {{ projects.draft.id }}</span></template>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('projects.col.id') }}</div>
          <div class="d">{{ t('proj.id.locked') }}</div>
        </div>
        <div class="ctl"><span class="ro">{{ projects.draft.id }}</span></div>
      </div>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.path') }}</div>
          <div class="d">{{ t('proj.path.locked') }}</div>
        </div>
        <div class="ctl wide"><span class="ro">{{ projects.draft.path }}</span></div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('proj.aliases') }}</div></div>
        <div class="ctl wide">
          <el-input v-model="projects.draft.aliases" size="small" placeholder="app, web" />
        </div>
      </div>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.group') }}</div>
          <div class="d">{{ t('proj.group.d') }}</div>
        </div>
        <div class="ctl">
          <el-input v-model="projects.draft.group" size="small" style="width: 160px" />
        </div>
      </div>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.verify') }}</div>
          <div class="d">{{ t('proj.verify.d') }}</div>
        </div>
        <div class="ctl wide">
          <el-input v-model="projects.draft.verify" size="small" placeholder="npm run build" />
        </div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('proj.verifykind') }}</div></div>
        <div class="ctl">
          <el-segmented
            v-model="projects.draft.verify_kind"
            size="small"
            :options="[
              { label: 'check', value: 'check' },
              { label: 'build', value: 'build' },
              { label: 'none', value: 'none' }
            ]"
          />
        </div>
      </div>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.forbidden') }}</div>
          <div class="d">{{ t('proj.forbidden.d') }}</div>
        </div>
        <div class="ctl wide">
          <el-input v-model="projects.draft.forbidden" size="small" placeholder=".git/, dist/" />
        </div>
      </div>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.schema') }}</div>
          <div class="d">{{ t('proj.schema.d') }}</div>
        </div>
        <div class="ctl">
          <el-segmented
            v-model="projects.draft.result_schema"
            size="small"
            :options="[
              { label: t('proj.schema.default'), value: 'default' },
              { label: t('proj.schema.none'), value: 'none' }
            ]"
          />
        </div>
      </div>
      <p v-if="projects.error" class="err">{{ projects.error }}</p>
      <p class="hint">{{ t('proj.edit.hint') }}</p>
      <template #footer>
        <el-button size="small" @click="projects.closeEdit()">{{ t('dlg.cancel') }}</el-button>
        <el-button size="small" class="btn-primary" :disabled="projects.busy" @click="save">
          {{ projects.busy ? t('proj.writing') : t('dlg.save') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 移除：只从注册表里去掉，不碰仓库文件；但要提醒任务记录会失去对应项目 -->
    <el-dialog v-model="projects.removeOpen" class="sheet" width="500">
      <template #header><span>{{ t('proj.remove') }}</span></template>
      <div class="setrow">
        <div class="lab">
          <div class="t">{{ t('proj.remove.q') }}</div>
          <div class="d">{{ projects.draft.id }} · {{ projects.draft.path }}</div>
        </div>
      </div>
      <p v-if="projects.error" class="err">{{ projects.error }}</p>
      <p class="hint">{{ t('proj.remove.hint') }}</p>
      <template #footer>
        <el-button size="small" @click="projects.closeRemove()">{{ t('dlg.cancel') }}</el-button>
        <el-button size="small" class="btn-danger" :disabled="projects.busy" @click="remove">
          {{ projects.busy ? t('proj.writing') : t('proj.remove') }}
        </el-button>
      </template>
    </el-dialog>

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
