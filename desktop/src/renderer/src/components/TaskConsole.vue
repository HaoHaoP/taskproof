<script setup lang="ts">
/**
 * The console's sheets: the dispatch form (and its consequence step) plus the
 * two dangerous-action confirmations.
 *
 * Mounted once at the shell so any view can raise them; the *state* lives in
 * `stores/tasks`, so this component only arranges the store's fields into the
 * app's sheet look (`SHEET_TRANSITION` + `.sheet`, like the project editors).
 *
 * Every successful write re-reads the board rather than stitching the row in
 * locally. A write that changes nothing -- a card already released elsewhere --
 * is shown as a transient notice instead, rendered by the matrix.
 */
import { useI18n } from 'vue-i18n'
import { SHEET_TRANSITION } from './sheetTransition'
import { ADAPTERS, draftValid } from '../compose'
import { useBoardStore } from '../stores/board'
import { useTasksStore } from '../stores/tasks'

const board = useBoardStore()
const store = useTasksStore()
const { t } = useI18n()

/** A write that landed ends in a fresh read, never a locally patched row. */
async function submit(start: boolean): Promise<void> {
  if (await store.submit(start)) await board.refresh()
}

async function confirmStop(): Promise<void> {
  if (await store.confirmStop()) await board.refresh()
}

async function confirmAccept(): Promise<void> {
  // A 409 ("no longer blocked") also returns true, so the board is re-read and
  // the stale card leaves no still-clickable leftover.
  if (await store.confirmAccept()) await board.refresh()
}

async function confirmDelete(): Promise<void> {
  if (await store.confirmDelete()) await board.refresh()
}

/** The two-step sheet is open whenever either step is; closing the step that is
 *  not showing (the X) closes the whole flow. */
function stepOpen(): boolean {
  return store.composeOpen || store.summaryOpen
}

function onStepVisibility(value: boolean): void {
  if (!value) store.closeCompose()
}
</script>

<template>
  <!-- Step one: the four-field form. -->
  <el-dialog
    :model-value="stepOpen()"
    :transition="SHEET_TRANSITION"
    class="sheet"
    width="580"
    append-to-body
    @update:model-value="onStepVisibility"
  >
    <template #header>
      <span>
        {{ store.rerunOf ? t('task.compose.rerun') : t('task.compose.title') }}
        <template v-if="store.rerunOf"> · {{ store.rerunOf }}</template>
      </span>
    </template>

    <template v-if="!store.summaryOpen">
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.compose.project') }}</div></div>
        <div class="ctl wide">
          <el-select
            class="pick"
            size="small"
            :model-value="store.draft.project"
            :placeholder="t('task.compose.project')"
            @update:model-value="(v: string) => store.setDraft({ project: v })"
          >
            <el-option
              v-for="project in board.projects"
              :key="project.id"
              :value="project.id"
              :label="project.id"
            />
          </el-select>
        </div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.compose.brief') }}</div></div>
        <div class="ctl wide">
          <el-input
            v-model="store.draft.brief"
            type="textarea"
            :rows="3"
            :placeholder="t('task.compose.briefPlaceholder')"
          />
        </div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.compose.adapter') }}</div></div>
        <div class="ctl">
          <el-select
            class="pick sm"
            size="small"
            :model-value="store.draft.adapter"
            @update:model-value="(v: string) => store.setDraft({ adapter: v })"
          >
            <el-option v-for="a in ADAPTERS" :key="a" :value="a" :label="a" />
          </el-select>
        </div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.compose.timeout') }}</div></div>
        <div class="ctl">
          <el-input-number
            size="small"
            :min="1"
            :step="60"
            :model-value="store.draft.timeout"
            @update:model-value="(v: number | undefined) => v != null && store.setDraft({ timeout: v })"
          />
          <span class="unit">{{ t('task.compose.seconds') }}</span>
        </div>
      </div>
      <p v-if="!board.projects.length" class="hint">{{ t('task.compose.noProjects') }}</p>
      <p v-if="store.error" class="err">{{ store.error }}</p>
    </template>

    <!-- Step two: the consequence summary, then the two exits. -->
    <template v-else>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.summary.project') }}</div></div>
        <div class="ctl wide"><span class="ro">{{ store.summary.project || '—' }}</span></div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.summary.path') }}</div></div>
        <div class="ctl wide"><span class="ro">{{ store.summary.path || '—' }}</span></div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.summary.adapter') }}</div></div>
        <div class="ctl wide"><span class="ro">{{ store.summary.adapter }}</span></div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.summary.timeout') }}</div></div>
        <div class="ctl wide">
          <span class="ro">{{ t('task.summary.seconds', { n: store.summary.timeout }) }}</span>
        </div>
      </div>
      <div class="setrow">
        <div class="lab"><div class="t">{{ t('task.summary.forbidden') }}</div></div>
        <div class="ctl wide">
          <span class="ro">
            {{
              store.summary.forbiddenPaths.length
                ? store.summary.forbiddenPaths.join('、')
                : t('task.summary.none')
            }}
          </span>
        </div>
      </div>
      <p v-if="store.error" class="err">{{ store.error }}</p>
    </template>

    <template #footer>
      <template v-if="!store.summaryOpen">
        <el-button size="small" @click="store.closeCompose()">{{ t('dlg.cancel') }}</el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="!draftValid(store.draft)"
          @click="store.toSummary()"
        >
          {{ t('task.compose.review') }}
        </el-button>
      </template>
      <template v-else>
        <el-button size="small" @click="store.backToCompose()">
          {{ t('task.compose.back') }}
        </el-button>
        <el-button size="small" :disabled="store.busy" @click="submit(false)">
          {{ t('task.summary.queue') }}
        </el-button>
        <el-button size="small" type="primary" :disabled="store.busy" @click="submit(true)">
          {{ store.busy ? t('task.busy') : t('task.summary.dispatch') }}
        </el-button>
      </template>
    </template>
  </el-dialog>

  <!-- Stop: the consequence is said before the verb. -->
  <el-dialog
    v-model="store.stopOpen"
    :transition="SHEET_TRANSITION"
    class="sheet"
    width="500"
    append-to-body
  >
    <template #header><span>{{ t('task.confirmStop.title') }}</span></template>
    <div class="setrow">
      <div class="lab"><div class="t">{{ store.target?.id }}</div></div>
    </div>
    <p class="hint">{{ t('task.confirmStop.body') }}</p>
    <p v-if="store.error" class="err">{{ store.error }}</p>
    <template #footer>
      <el-button size="small" @click="store.closeStop()">{{ t('dlg.cancel') }}</el-button>
      <el-button size="small" type="danger" :disabled="store.busy" @click="confirmStop()">
        {{ store.busy ? t('task.busy') : t('task.confirmStop.confirm') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- Accept: the release of a blocked card. It is not undoable, so the
       consequence is spelled out before the verb, like stop and delete. -->
  <el-dialog
    v-model="store.acceptOpen"
    :transition="SHEET_TRANSITION"
    class="sheet"
    width="500"
    append-to-body
  >
    <template #header><span>{{ t('task.confirmAccept.title') }}</span></template>
    <div class="setrow">
      <div class="lab"><div class="t">{{ store.target?.id }}</div></div>
    </div>
    <p class="hint">{{ t('task.confirmAccept.body') }}</p>
    <p v-if="store.error" class="err">{{ store.error }}</p>
    <template #footer>
      <el-button size="small" @click="store.closeAccept()">{{ t('dlg.cancel') }}</el-button>
      <el-button size="small" type="danger" :disabled="store.busy" @click="confirmAccept()">
        {{ store.busy ? t('task.busy') : t('task.confirmAccept.confirm') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- Delete: terminal rows only; the store refuses a live one even if a future
       caller slips through. -->
  <el-dialog
    v-model="store.deleteOpen"
    :transition="SHEET_TRANSITION"
    class="sheet"
    width="500"
    append-to-body
  >
    <template #header><span>{{ t('task.confirmDelete.title') }}</span></template>
    <div class="setrow">
      <div class="lab"><div class="t">{{ store.target?.id }}</div></div>
    </div>
    <p class="hint">{{ t('task.confirmDelete.body') }}</p>
    <p v-if="store.error" class="err">{{ store.error }}</p>
    <template #footer>
      <el-button size="small" @click="store.closeDelete()">{{ t('dlg.cancel') }}</el-button>
      <el-button size="small" type="danger" :disabled="store.busy" @click="confirmDelete()">
        {{ store.busy ? t('task.busy') : t('task.confirmDelete.confirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.unit {
  font: 11.5px/1 var(--sans);
  color: var(--ink-3);
}
.pick {
  width: 220px;
}
.pick.sm {
  width: 150px;
}
</style>
