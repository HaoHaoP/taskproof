<script setup lang="ts">
/**
 * The task drawer, ported from the prototype's `.tp-drawer`.
 *
 * Open state comes from the route (`/<view>/:taskId`), so a detail view is
 * deep-linkable and the page container owns it.
 *
 * The layout is the prototype's: a header strip (state chip, id, duration,
 * close), then the brief, then a real timeline -- a hairline with a dot per
 * event -- then the duel between what the worker claimed and what taskproof
 * observed. The verdict block only exists when verification actually ran:
 * printing an empty verdict box for a task that was never verified would
 * invent a judgement that was never made.
 */
import { computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import StatusMark from './StatusMark.vue'
import { ABNORMAL } from '../contract'
import { duration, eventSummary, isBadEvent, shortTime } from '../format'
import { useBoardStore } from '../stores/board'

const store = useBoardStore()
const route = useRoute()
const router = useRouter()
const { t, te } = useI18n()

const open = computed(() => typeof route.params.taskId === 'string' && route.params.taskId !== '')
const task = computed(() => store.detail?.task ?? null)
const events = computed(() => store.detail?.events ?? [])

/** The task is still moving, so the last timeline dot pulses. */
const liveTask = computed(() => {
  const status = task.value?.status
  return store.polling && (status === 'running' || status === 'verifying')
})

/** Timeline rows: the API's `{ts, event, payload}` projected to what the
 *  prototype's markup shows. Unknown events keep their raw name -- inventing a
 *  label for a word the backend just introduced would hide the new state. */
const timeline = computed(() =>
  events.value.map((event) => ({
    t: shortTime(event.ts),
    k: te(`event.${event.event}`) ? t(`event.${event.event}`) : event.event,
    g: event.event === 'adapter' || event.event === 'verify' ? '' : '',
    d: eventSummary(event.event, event.payload),
    bad: isBadEvent(event.event, event.payload)
  }))
)

const verify = computed(() => task.value?.verify_exit ?? null)
const verifyText = computed(() =>
  verify.value == null ? t('ev.notrun') : `exit ${verify.value}`
)

const dur = computed(() => duration(task.value?.started_at ?? null, task.value?.finished_at ?? null))
const started = computed(() => shortTime(task.value?.started_at))
const ended = computed(() => (task.value?.finished_at ? shortTime(task.value.finished_at) : t('drawer.now')))

function close(): void {
  const name = typeof route.name === 'string' ? route.name : 'matrix'
  void router.push({ name })
}

function onVisible(value: boolean): void {
  if (!value) close()
}

/**
 * The worker's own account is only worth the space when the outcome is in
 * doubt. On a passing or cancelled card it is noise -- the operator just needs
 * to know it passed -- so it renders only for the failure-like states.
 */
const showClaim = computed(() => ABNORMAL.includes(task.value?.status ?? ''))

/**
 * The drawer is modal, so focus must move into it on open and come back to
 * whatever opened it (a task card, a table row) on close. Element Plus' focus
 * trap already restores to the element focused when it activated, but we pin
 * that element ourselves too, so the round trip never depends on the trap's
 * timing.
 */
let lastFocused: HTMLElement | null = null
watch(open, (isOpen) => {
  if (isOpen) {
    lastFocused = (document.activeElement as HTMLElement | null) ?? null
  } else {
    const target = lastFocused
    lastFocused = null
    void nextTick(() => target?.focus?.())
  }
})

/**
 * The route owns which task is open, so this is where the detail gets loaded.
 *
 * Nothing else did: the cards and the table rows only push the route, and the
 * store's `detail` stayed null, which is why the drawer used to show its
 * "nothing here" fallback for every task. `immediate` covers a deep link.
 */
watch(
  () => route.params.taskId,
  (id) => {
    if (typeof id === 'string' && id) void store.openTask(id)
    else store.closeTask()
  },
  { immediate: true }
)
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
    <template v-if="task">
      <div class="dh">
        <span class="sc" :data-status="task.status">
          <StatusMark :status="task.status" shape="dot" />
          {{ t(`status.${task.status}`) }}
        </span>
        <span class="cid">{{ task.id }}</span>
        <span class="dur">{{ dur }}<br />{{ started }} → {{ ended }}</span>
        <button class="x" type="button" :aria-label="t('drawer.close')" @click="close">✕</button>
      </div>

      <div class="dbody">
        <section class="sec">
          <h4>{{ t('drawer.brief') }}</h4>
          <pre class="full">{{ task.brief }}</pre>
        </section>

        <section class="sec">
          <h4>
            {{ t('drawer.timeline') }}
            <span class="live" :data-off="store.polling ? null : ''">
              <i></i>{{ store.polling ? t('live.on') : t('live.off') }}
            </span>
          </h4>
          <ol class="tl">
            <li
              v-for="(entry, index) in timeline"
              :key="index"
              class="ev"
              :class="{ now: liveTask && index === timeline.length - 1, isbad: entry.bad }"
            >
              <span class="dot"></span>
              <span class="t">{{ entry.t }}</span>
              <span class="k">{{ entry.k }}</span>
              <span class="g">{{ entry.g }}</span>
              <span v-if="entry.d" class="d">{{ entry.d }}</span>
            </li>
            <li v-if="!timeline.length" class="ev">
              <span class="dot"></span><span class="t">—</span>
            </li>
          </ol>
        </section>

        <!-- No verification ran -> no verdict block at all. When it ran it
             always leads the outcome, so the worker's own account can only
             ever follow it. -->
        <section v-if="verify != null" class="sec">
          <h4>{{ t('drawer.verdict') }}<em>— {{ t('verdict.by') }}</em></h4>
          <div class="vrow">
            <span class="vdot" :class="{ bad: verify !== 0 }"></span>
            <span class="vlabel">{{ t(verify === 0 ? 'verdict.passed' : 'verdict.failed') }}</span>
            <span class="vcode" :class="{ bad: verify !== 0 }">exit {{ verify }}</span>
          </div>
          <p v-if="task.verify_cmd" class="vcmd">{{ task.verify_cmd }}</p>
        </section>

        <!-- What the worker said vs what taskproof observed. They sit side by
             side on purpose: the point is that the self-report and the observed
             evidence are independent. The self-report is only rendered for the
             failure-like states -- on anything else it is noise -- so the duel
             collapses to the evidence alone otherwise. -->
        <div class="duel" :class="{ solo: !showClaim }">
          <div v-if="showClaim" class="side claim">
            <h5>{{ t('drawer.claim') }}</h5>
            <p class="body">{{ task.reasoning || t('drawer.noClaim') }}</p>
          </div>
          <div v-if="showClaim" class="rule"></div>
          <div class="side ev">
            <h5>{{ t('drawer.evidence') }}</h5>
            <dl>
              <dt>{{ t('ev.exit') }}</dt>
              <dd>{{ task.exit_code ?? '—' }}</dd>
              <dt>{{ t('ev.verify') }}</dt>
              <dd :class="{ bad: verify != null && verify !== 0, good: verify === 0 }">
                {{ verifyText }}
              </dd>
              <dt>{{ t('ev.files') }}</dt>
              <dd>{{ task.files_changed ?? 0 }}</dd>
              <dt>{{ t('ev.adapter') }}</dt>
              <dd>{{ task.adapter ?? '—' }}{{ task.model ? ` · ${task.model}` : '' }}</dd>
              <dt>{{ t('ev.group') }}</dt>
              <dd>{{ task.group_name ?? '—' }}</dd>
            </dl>
          </div>
        </div>
      </div>
    </template>
    <p v-else class="none">{{ t('drawer.noTask') }}</p>
  </el-drawer>
</template>

<style scoped>
.dh {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 13px 16px 12px;
  border-bottom: 1px solid var(--rule-2);
  flex: none;
}
.sc {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 600 11px/1 var(--sans);
  padding: 4px 9px;
  border-radius: var(--r-pill);
  background: var(--w);
  color: var(--c);
  flex: none;
}
.dh .cid {
  font: 600 12px/1 var(--mono);
  color: var(--ink);
  overflow: visible;
  white-space: normal;
}
.dh .dur {
  font: 10px/1.4 var(--mono);
  color: var(--ink-4);
  margin-left: auto;
  text-align: right;
}
.dh .x {
  font: 13px/1 var(--sans);
  color: var(--ink-4);
  padding: 2px 6px;
  margin-left: 8px;
  border-radius: 6px;
  cursor: pointer;
}
.dh .x:hover {
  color: var(--ink);
  background: var(--raise);
}
.dbody {
  overflow: auto;
  padding: 0 0 26px;
  flex: 1;
}
.sec {
  padding: 15px 16px;
  border-bottom: 1px solid var(--rule-2);
}
.sec h4 {
  margin: 0 0 10px;
  font: 600 11px/1 var(--sans);
  letter-spacing: 0.02em;
  color: var(--ink-3);
  display: flex;
  align-items: center;
  gap: 9px;
}
.sec h4 em {
  font-style: normal;
  font-weight: 400;
  color: var(--ink-4);
}
.full {
  margin: 0;
  font: 11px/1.6 var(--mono);
  color: var(--ink-2);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--sunken);
  border-radius: var(--r-ctl);
  padding: 10px 12px;
}
/* Timeline: a hairline with one dot per event. */
.tl {
  list-style: none;
  margin: 0;
  padding: 0 0 0 4px;
}
.tl .ev {
  position: relative;
  display: grid;
  grid-template-columns: 52px 1fr auto;
  gap: 0 11px;
  padding: 0 0 13px 16px;
  border-left: 1px solid var(--rule);
}
.tl .ev:last-child {
  border-left-color: transparent;
  padding-bottom: 0;
}
.tl .dot {
  position: absolute;
  left: -4.5px;
  top: 3px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bg);
  border: 1.5px solid var(--ink-4);
}
.tl .ev.now .dot {
  border-color: var(--c-running);
  background: var(--c-running);
  animation: tp-pulse 1.6s ease-in-out infinite;
}
.tl .ev.isbad .dot {
  border-color: var(--c-failed);
  background: var(--c-failed);
}
.tl .t {
  font: 10px/1.5 var(--mono);
  color: var(--ink-4);
}
.tl .k {
  font: 600 11.5px/1.5 var(--sans);
  grid-column: 2;
  color: var(--ink-2);
}
.tl .g {
  font: 10px/1.5 var(--mono);
  color: var(--ink-4);
  text-align: right;
}
.tl .d {
  grid-column: 2/4;
  font: 10px/1.55 var(--mono);
  color: var(--ink-3);
  word-break: break-word;
}
.live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 11.5px/1 var(--sans);
  color: var(--ink-3);
}
.live i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-running);
  animation: tp-pulse 1.6s ease-in-out infinite;
}
.live[data-off] i {
  background: var(--ink-4);
  animation: none;
}
/* The duel: claim | rule | evidence. */
.duel {
  display: grid;
  grid-template-columns: 1fr 1px 1fr;
  border-bottom: 1px solid var(--rule-2);
}
.duel .side {
  padding: 14px 16px 16px;
  min-width: 0;
}
.duel .side h5 {
  margin: 0 0 8px;
  font: 600 11px/1 var(--sans);
  color: var(--ink-3);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.duel .side h5 em {
  font-style: normal;
  font-weight: 400;
  color: var(--ink-4);
}
.duel.solo {
  grid-template-columns: 1fr;
}
.duel .rule {
  background: var(--rule-2);
}
.duel .claim .body {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-2);
  white-space: pre-wrap;
  word-break: break-word;
}
.duel .ev dl {
  margin: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
}
.duel .ev dt {
  font: 11px/1.5 var(--sans);
  color: var(--ink-4);
  white-space: nowrap;
}
.duel .ev dd {
  margin: 0;
  font: 11px/1.5 var(--mono);
  color: var(--ink);
  word-break: break-word;
}
.duel .ev dd.bad {
  color: var(--c-failed);
  font-weight: 600;
}
.duel .ev dd.good {
  color: var(--ok);
  font-weight: 600;
}
.vrow {
  display: flex;
  align-items: center;
  gap: 9px;
}
.vdot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  background: var(--ok);
}
.vdot.bad {
  background: var(--c-failed);
}
.vlabel {
  font: 600 13px/1.4 var(--sans);
  color: var(--ink);
}
.vcode {
  margin-left: auto;
  font: 11.5px/1 var(--mono);
  color: var(--ink-3);
}
.vcode.bad {
  color: var(--c-failed);
  font-weight: 600;
}
.vcmd {
  margin: 7px 0 0;
  font: 10px/1.5 var(--mono);
  color: var(--ink-4);
  overflow-wrap: anywhere;
}
.none {
  padding: 16px;
  color: var(--ink-4);
}
@media (prefers-reduced-motion: reduce) {
  .tl .ev.now .dot,
  .live i {
    animation: none;
  }
}
</style>

<!--
  Element Plus owns the drawer shell, so these have to reach its own elements.
  Keyed under `.tp-drawer` rather than left global, so no other drawer in the
  app picks them up.
-->
<style>
.tp-drawer {
  top: var(--mast) !important;
  height: calc(100% - var(--mast)) !important;
  background: var(--panel) !important;
  border-left: 1px solid var(--rule) !important;
  border-radius: var(--r-card) 0 0 var(--r-card);
  box-shadow: -20px 0 44px -26px rgba(0, 0, 0, 0.8) !important;
  display: flex;
  flex-direction: column;
}
html[data-theme='light'] .tp-drawer {
  box-shadow: -20px 0 44px -26px rgba(0, 0, 0, 0.28) !important;
}
.tp-drawer .el-drawer__body {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
