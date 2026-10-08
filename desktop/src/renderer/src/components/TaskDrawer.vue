<script setup lang="ts">
/**
 * The task drawer. Open state comes from the route (`/<view>/:taskId`), so a
 * detail view is deep-linkable and the page container owns it.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import StatusMark from './StatusMark.vue'
import { EXIT_MEANINGS } from '../contract'
import { duration, payloadLine, shortTime } from '../format'
import { useBoardStore } from '../stores/board'

const store = useBoardStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const open = computed(() => typeof route.params.taskId === 'string' && route.params.taskId !== '')
const task = computed(() => store.detail?.task ?? null)
const events = computed(() => store.detail?.events ?? [])

function close(): void {
  const name = typeof route.name === 'string' ? route.name : 'matrix'
  void router.push({ name })
}

function onVisible(value: boolean): void {
  if (!value) close()
}
</script>

<template>
  <el-drawer
    :model-value="open"
    :size="520"
    direction="rtl"
    :with-header="false"
    class="tp-drawer"
    @update:model-value="onVisible"
  >
    <div v-if="task" class="body">
      <header class="head">
        <span class="id">{{ task.id }}</span>
        <span class="chip" :data-status="task.status">
          <StatusMark :status="task.status" shape="dot" />
          {{ t(`status.${task.status}`) }}
        </span>
      </header>

      <section class="block">
        <h3>{{ t('drawer.brief') }}</h3>
        <pre class="brief">{{ task.brief }}</pre>
      </section>

      <section class="block">
        <h3>{{ t('drawer.timeline') }}</h3>
        <ol class="tl">
          <li v-for="(event, index) in events" :key="index">
            <span class="ts">{{ shortTime(event.ts) }}</span>
            <span class="ev">{{ event.event }}</span>
            <span class="pl">{{ payloadLine(event.payload) }}</span>
          </li>
          <li v-if="!events.length" class="empty">—</li>
        </ol>
      </section>

      <!-- claim is what the worker said; evidence is what taskproof observed.
           They are deliberately side by side: the whole point is that they
           are independent. -->
      <section class="duel">
        <div>
          <h3>{{ t('drawer.claim') }}</h3>
          <p v-if="task.reasoning" class="claim">{{ task.reasoning }}</p>
          <p v-else class="none">{{ t('drawer.claimNone') }}</p>
        </div>
        <div>
          <h3>{{ t('drawer.evidence') }}</h3>
          <dl>
            <dt>{{ t('drawer.exitCode') }}</dt>
            <dd>
              {{ task.exit_code ?? '—' }}
              <span v-if="task.exit_code != null" class="muted">
                {{ EXIT_MEANINGS[task.exit_code] ?? 'unknown' }}
              </span>
            </dd>
            <dt>{{ t('drawer.verify') }}</dt>
            <dd>{{ task.verify_exit ?? 'skipped' }}</dd>
            <dt>{{ t('drawer.duration') }}</dt>
            <dd>{{ duration(task.started_at, task.finished_at) }}</dd>
            <dt>{{ t('drawer.files') }}</dt>
            <dd>{{ task.files_changed ?? 0 }}</dd>
            <dt>{{ t('drawer.adapter') }}</dt>
            <dd>{{ task.adapter ?? '—' }}</dd>
            <dt>{{ t('drawer.model') }}</dt>
            <dd>{{ task.model ?? '—' }}</dd>
            <dt>{{ t('drawer.group') }}</dt>
            <dd>{{ task.group_name ?? '—' }}</dd>
          </dl>
        </div>
      </section>
    </div>
    <p v-else class="none">{{ t('drawer.claimNone') }}</p>
  </el-drawer>
</template>

<style scoped>
.body {
  padding: 4px 2px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.id {
  font: 600 13px/1 var(--mono);
  color: var(--ink);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 500 11px/1 var(--sans);
  color: var(--c);
  background: var(--w);
  border-radius: var(--r-pill);
  padding: 4px 9px;
}
.block {
  margin-top: 20px;
}
h3 {
  margin: 0 0 7px;
  font: 600 11px/1 var(--sans);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink-4);
}
.brief {
  margin: 0;
  padding: 10px 12px;
  background: var(--sunken);
  border-radius: var(--r-ctl);
  font: 12px/1.6 var(--sans);
  color: var(--ink);
  white-space: pre-wrap;
}
.tl {
  margin: 0;
  padding: 0;
  list-style: none;
}
.tl li {
  display: grid;
  grid-template-columns: 62px 96px 1fr;
  gap: 8px;
  align-items: baseline;
  padding: 5px 0;
  border-bottom: 1px solid var(--rule-2);
  font-size: 12px;
  color: var(--ink-2);
}
.tl .ts,
.tl .ev {
  font-family: var(--mono);
  font-size: 11px;
}
.tl .ev {
  color: var(--ink);
}
.tl .pl {
  color: var(--ink-3);
  overflow-wrap: anywhere;
}
.tl .empty,
.none {
  color: var(--ink-4);
}
.duel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  margin-top: 20px;
}
.claim {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-2);
  white-space: pre-wrap;
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
  margin: 0;
  font-size: 12px;
}
dt {
  color: var(--ink-4);
}
dd {
  margin: 0;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink);
}
.muted {
  color: var(--ink-4);
}
</style>
