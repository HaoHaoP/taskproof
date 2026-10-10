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
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import StatusMark from './StatusMark.vue'
import { ABNORMAL } from '../contract'
import { duration, eventSummary, isBadEvent, shortTime } from '../format'
import {
  byteLength,
  countMatches,
  formatBytes,
  highlightSegments,
  matchLineIndexes,
  shouldStickBottom,
  stripAnsi
} from '../logview'
import { LOG_MAX_LINES, useBoardStore } from '../stores/board'

const store = useBoardStore()
const route = useRoute()
const router = useRouter()
const { t, te } = useI18n()

const open = computed(() => typeof route.params.taskId === 'string' && route.params.taskId !== '')
const task = computed(() => store.detail?.task ?? null)
const events = computed(() => store.detail?.events ?? [])

/** Which drawer tab is showing. Only an exact `?tab=log` selects the log;
 *  anything else -- absent, or a stale hand-edited value -- is the default
 *  overview. The address bar is the one source of truth, so the tab is
 *  deep-linkable and survives a reload. */
const tab = computed<'overview' | 'log'>(() => (route.query.tab === 'log' ? 'log' : 'overview'))

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
  // Leave the query (the board's filter, and the tab) in the address bar; the
  // missing `params.taskId` is what actually closes the drawer.
  void router.push({ name, query: route.query })
}

/** Switch tabs in place: same task, same filter, only `?tab=` changes. */
function go(nextTab: 'overview' | 'log'): void {
  const name = typeof route.name === 'string' ? route.name : 'matrix'
  const id = typeof route.params.taskId === 'string' ? route.params.taskId : ''
  const query = { ...route.query }
  if (nextTab === 'log') query.tab = 'log'
  else delete query.tab
  void router.push({ name, params: { taskId: id }, query })
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

/* ------------------------------------------------------------------ *
 * The log tab. The store owns the fetch and the tail; everything below
 * is presentation reasoning pulled out of the template so it can hold
 * still: stripping ANSI for display, the local search, and the "follow
 * the tail until the reader scrolls up" rule.
 * ------------------------------------------------------------------ */

/** Loaded text with ANSI removed, for display and search. stripAnsi never
 *  touches newlines, so a line index here matches the raw text's line. */
const logDisplay = computed(() => stripAnsi(store.logText))
/** Blank text means "no output", not one empty line. */
const logLines = computed(() => (logDisplay.value === '' ? [] : logDisplay.value.split('\n')))

/** The search is local to what is loaded -- no paging upward -- so its
 *  counter and highlight never claim to cover bytes we never fetched. */
const query = ref('')
const matchCount = computed(() => countMatches(logDisplay.value, query.value))
const hitLines = computed(() => matchLineIndexes(logDisplay.value, query.value))
const currentHit = ref(0)
const hitPosition = computed(() => (matchCount.value ? currentHit.value + 1 : 0))
/** Case-insensitivity lives in logview's matcher (a debugging convenience);
 *  changing the query resets the cursor to the first hit. */
watch(query, () => (currentHit.value = 0))

const logEl = ref<HTMLElement | null>(null)
/** Whether new lines should keep dragging the viewport down. Starts true so
 *  the first page lands at the bottom. */
const stuck = ref(true)
/** How many lines arrived while the reader was scrolled up -- the count the
 *  "back to bottom" button offers. */
const newLines = ref(0)

function onLogScroll(): void {
  const el = logEl.value
  if (!el) return
  if (shouldStickBottom(el.scrollTop, el.scrollHeight, el.clientHeight)) {
    stuck.value = true
    newLines.value = 0
  } else {
    stuck.value = false
  }
}

function scrollToBottom(): void {
  const el = logEl.value
  if (el) el.scrollTop = el.scrollHeight
}

/** Follow the tail only while the reader is already at (within 24px of) the
 *  bottom. Once they scroll up, hold their position and count the arrivals --
 *  yanking the viewport back down would fight the reader. */
watch(
  () => logDisplay.value,
  async (now, before) => {
    if (before === undefined || now === before) return
    const beforeLines = before === '' ? 0 : before.split('\n').length
    const afterLines = logLines.value.length
    await nextTick()
    if (stuck.value) scrollToBottom()
    else if (afterLines > beforeLines) newLines.value += afterLines - beforeLines
  }
)

/** A different task's log starts pinned to the bottom, with a clean search. */
watch(
  () => store.logTaskId,
  () => {
    stuck.value = true
    newLines.value = 0
    query.value = ''
    void nextTick(scrollToBottom)
  }
)

function jumpBottom(): void {
  stuck.value = true
  newLines.value = 0
  scrollToBottom()
  void nextTick(scrollToBottom)
}

/** Does this line hold the occurrence "next"/"prev" is standing on? */
function isCurrentHitLine(index: number): boolean {
  return hitLines.value[currentHit.value] === index
}

function scrollHitIntoView(): void {
  const el = logEl.value
  const line = hitLines.value[currentHit.value]
  if (!el || line == null) return
  const target = el.querySelector<HTMLElement>(`[data-line="${line}"]`)
  if (!target) return
  const delta = target.getBoundingClientRect().top - el.getBoundingClientRect().top
  el.scrollTop += delta - el.clientHeight / 2 + target.clientHeight / 2
}

function goToHit(index: number): void {
  const total = hitLines.value.length
  if (!total) return
  currentHit.value = ((index % total) + total) % total
  void nextTick(scrollHitIntoView)
}

function nextHit(): void {
  goToHit(currentHit.value + 1)
}

function prevHit(): void {
  goToHit(currentHit.value - 1)
}

function onQuery(value: string): void {
  query.value = value
}

/** Copy the *raw* text -- ANSI and all -- because that is what the process
 *  actually wrote, and a reader pasting it elsewhere wants those bytes. */
const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | undefined
async function copyLog(): Promise<void> {
  if (!navigator.clipboard) return
  try {
    await navigator.clipboard.writeText(store.logText)
    copied.value = true
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => (copied.value = false), 1200)
  } catch {
    // A refused clipboard read leaves the button alone rather than claiming a
    // copy that did not happen.
  }
}

/** The tail runs only while the log tab is open and the drawer has a task. */
watch(
  [open, tab, () => route.params.taskId],
  ([isOpen, whichTab, id]) => {
    if (isOpen && whichTab === 'log' && typeof id === 'string' && id) store.startLog(id)
    else store.stopLog()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  store.stopLog()
  if (copiedTimer) clearTimeout(copiedTimer)
})

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

      <!-- Selected state lives in `?tab=`; the default board has no `tab` key.
           Real buttons, so Tab reaches both and Enter / Space switch (the
           explicit handlers keep the behaviour even where a native click is
           swallowed). -->
      <div class="dtabs" role="tablist">
        <button
          role="tab"
          type="button"
          :aria-selected="tab === 'overview'"
          :class="{ on: tab === 'overview' }"
          @click="go('overview')"
          @keydown.enter.prevent="go('overview')"
          @keydown.space.prevent="go('overview')"
        >
          {{ t('drawer.tab.overview') }}
        </button>
        <button
          role="tab"
          type="button"
          :aria-selected="tab === 'log'"
          :class="{ on: tab === 'log' }"
          @click="go('log')"
          @keydown.enter.prevent="go('log')"
          @keydown.space.prevent="go('log')"
        >
          {{ t('drawer.tab.log') }}
        </button>
      </div>

      <div v-show="tab === 'overview'" class="dbody">
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
              <dd>{{ task.files_changed_live ?? task.files_changed ?? 0 }}</dd>
              <dt>{{ t('ev.adapter') }}</dt>
              <dd>{{ task.adapter ?? '—' }}{{ task.model ? ` · ${task.model}` : '' }}</dd>
              <dt>{{ t('ev.group') }}</dt>
              <dd>{{ task.group_name ?? '—' }}</dd>
              <!-- The lane (taskgroup) is one of the task's facts, at the same
                   level as the rest: the `project` column is the lane id. -->
              <dt>{{ t('ev.lane') }}</dt>
              <dd>{{ task.project }}</dd>
            </dl>
          </div>
        </div>
      </div>

      <!-- The log tab. The store owns the tail; this only renders it. Search
           is local to the loaded bytes, the display is ANSI-stripped while the
           copy button keeps the raw text, and a read failure shows one line
           without clearing what is already here. -->
      <div v-show="tab === 'log'" class="logpanel">
        <div class="logbar">
          <input
            class="logq"
            type="search"
            :value="query"
            :placeholder="t('log.search.placeholder')"
            :aria-label="t('log.search.placeholder')"
            @input="onQuery(($event.target as HTMLInputElement).value)"
          />
          <span class="logcount">{{ hitPosition }} / {{ matchCount }}</span>
          <button
            type="button"
            class="lognav"
            :aria-label="t('log.search.prev')"
            :disabled="!matchCount"
            @click="prevHit"
          >
            ↑
          </button>
          <button
            type="button"
            class="lognav"
            :aria-label="t('log.search.next')"
            :disabled="!matchCount"
            @click="nextHit"
          >
            ↓
          </button>
          <button type="button" class="logact" @click="copyLog">
            {{ copied ? t('log.copied') : t('log.copy') }}
          </button>
          <button type="button" class="logact" @click="store.refreshLog()">
            {{ t('log.refresh') }}
          </button>
        </div>

        <p class="logscope">
          {{ t('log.search.scope', { n: formatBytes(byteLength(store.logText)) }) }}
          <span v-if="query && !matchCount" class="lognone">{{ t('log.search.none') }}</span>
        </p>

        <!-- The fixed notices. `omitted` is the file's head the first read
             never fetched; `truncated` is our own 5000-line trim; the error
             line sits above whatever text did load, never in place of it. -->
        <p v-if="store.logOmitted > 0" class="lognote">
          {{ t('log.omitted', { n: formatBytes(store.logOmitted) }) }}
        </p>
        <p v-if="store.logTruncated" class="lognote">
          {{ t('log.truncated', { n: LOG_MAX_LINES }) }}
        </p>
        <p v-if="store.logError" class="logerr">{{ store.logError }}</p>

        <div ref="logEl" class="logscroll" @scroll="onLogScroll">
          <p v-if="!logLines.length && !store.logError" class="logempty">
            {{ t('log.empty') }}
          </p>
          <!-- Index keys are stable for an append-only tail: existing rows are
               patched in place and only the new ones are created. -->
          <div
            v-for="(line, index) in logLines"
            :key="index"
            class="logline"
            :data-line="index"
            :class="{ cur: isCurrentHitLine(index) }"
          >
            <span
              v-for="(seg, si) in highlightSegments(line, query)"
              :key="si"
              :class="{ hit: seg.hit }"
            >{{ seg.text }}</span>
          </div>
        </div>

        <button v-if="!stuck" type="button" class="logjump" @click="jumpBottom">
          {{ t('log.jumpBottom', { n: newLines }) }}
        </button>
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
/* Tabs: two real buttons; the selected one carries a rule under it. */
.dtabs {
  display: flex;
  gap: 2px;
  padding: 0 16px;
  border-bottom: 1px solid var(--rule-2);
  flex: none;
}
.dtabs button {
  font: 600 12px/1 var(--sans);
  color: var(--ink-4);
  background: none;
  border: 0;
  border-bottom: 2px solid transparent;
  padding: 11px 10px 9px;
  margin-bottom: -1px;
  cursor: pointer;
}
.dtabs button:hover {
  color: var(--ink-2);
}
.dtabs button.on {
  color: var(--ink);
  border-bottom-color: var(--accent);
}
/* The log panel fills the drawer body: a fixed toolbar and notices above a
   scrolling tail, with the jump button floating at its lower right. */
.logpanel {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.logbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--rule-2);
  flex: none;
}
.logq {
  flex: 1;
  min-width: 0;
  font: 11.5px/1.4 var(--mono);
  color: var(--ink);
  background: var(--sunken);
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  padding: 5px 8px;
}
.logq:focus {
  outline: none;
  border-color: var(--accent);
}
.logcount {
  font: 11px/1 var(--mono);
  color: var(--ink-3);
  white-space: nowrap;
  min-width: 44px;
  text-align: center;
}
.lognav,
.logact {
  font: 11.5px/1 var(--mono);
  color: var(--ink-2);
  background: var(--panel);
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  padding: 5px 8px;
  cursor: pointer;
}
.lognav:hover:not(:disabled),
.logact:hover {
  background: var(--raise);
}
.lognav:disabled {
  color: var(--ink-4);
  opacity: 0.5;
  cursor: default;
}
.logscope {
  margin: 0;
  padding: 6px 12px;
  font: 10.5px/1.4 var(--mono);
  color: var(--ink-4);
  border-bottom: 1px solid var(--rule-2);
  flex: none;
}
.lognone {
  color: var(--c-failed);
  margin-left: 6px;
}
.lognote,
.logerr {
  margin: 0;
  padding: 6px 12px;
  font: 10.5px/1.5 var(--mono);
  flex: none;
}
.lognote {
  color: var(--ink-3);
  background: var(--sunken);
  border-bottom: 1px solid var(--rule-2);
}
.logerr {
  color: var(--c-failed);
  border-bottom: 1px solid var(--rule-2);
}
.logscroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 12px;
  font: 10.5px/1.55 var(--mono);
  color: var(--ink-2);
  background: var(--bg);
}
.logline {
  white-space: pre-wrap;
  word-break: break-word;
}
.logline.cur {
  background: var(--w-running);
  border-radius: 3px;
}
.logline .hit {
  background: color-mix(in srgb, var(--accent) 35%, transparent);
  border-radius: 2px;
}
.logempty {
  margin: 0;
  color: var(--ink-4);
}
.logjump {
  position: absolute;
  right: 14px;
  bottom: 14px;
  font: 11.5px/1 var(--sans);
  color: #fff;
  background: var(--accent);
  border: 0;
  border-radius: var(--r-pill);
  padding: 7px 12px;
  cursor: pointer;
  box-shadow: 0 6px 16px -6px rgba(0, 0, 0, 0.5);
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
