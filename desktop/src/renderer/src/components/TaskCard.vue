<script setup lang="ts">
/**
 * A task card. Pure props in, events out: no store, no fetching.
 *
 * Ported from the prototype's `button.card`: a state lamp, the id, then the
 * verification stamp and the disclosure chevron on the right. The stamp is the
 * verification exit code and nothing else -- `✓ 0` or `✗ N` -- and a task that
 * was never verified gets no stamp at all, because there is no verdict to show.
 *
 * The console adds two affordances to the same card:
 *  - an actions menu whose items follow the status (see `menuFor`), and
 *  - for a queued card, its `queue_seq` as an editable number and a "same
 *    wave" chip. The chip carries no number -- the editable seq is the card's
 *    one and only number -- and its colour is keyed off that same `queue_seq`,
 *    so two cards with the same number visibly share a wave.
 *
 * The card is a div with `role="button"` rather than a real <button>, because a
 * menu and a number input cannot legally nest inside one.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusMark from './StatusMark.vue'
import type { Task } from '../api/client'
import { menuFor, waveSlot, type TaskAction } from '../taskmenu'
import { duration } from '../format'

const props = defineProps<{ task: Task; expanded?: boolean }>()
const emit = defineEmits<{
  open: [id: string]
  action: [action: TaskAction]
  reorder: [seq: number]
}>()

const { t } = useI18n()

/** null means "no stamp": the prototype only renders one when verify !== null. */
const stamp = computed(() => {
  const exit = props.task.verify_exit
  if (exit == null) return null
  return { text: exit === 0 ? '✓ 0' : `✗ ${exit}`, cls: exit === 0 ? 'good' : 'bad' }
})

const menu = computed(() => menuFor(props.task.status))
const queued = computed(() => props.task.status === 'queued')

/** The wave chip's palette slot, keyed off the card's own `queue_seq` (see
 *  `waveSlot`). Same seq, same colour; the colour does not depend on which
 *  cards happen to be visible. The chip renders a word, never a number. */
const waveClass = computed(() => `w${waveSlot(props.task.queue_seq)}`)
</script>

<template>
  <div
    class="tp-card"
    role="button"
    tabindex="0"
    :data-status="task.status"
    :aria-expanded="expanded ? 'true' : 'false'"
    @click="emit('open', task.id)"
    @keydown.enter.prevent="emit('open', task.id)"
    @keydown.space.prevent="emit('open', task.id)"
  >
    <span class="line-1">
      <StatusMark :status="task.status" />
      <span class="cid">{{ task.id }}</span>
      <span class="tail">
        <span v-if="stamp" class="stamp" :class="stamp.cls">{{ stamp.text }}</span>
        <el-dropdown trigger="click" placement="bottom-end" @command="(a: TaskAction) => emit('action', a)">
          <button
            class="menu-btn"
            type="button"
            :aria-label="t('task.menu')"
            :title="t('task.menu')"
            @click.stop
          >
            ⋯
          </button>
          <template #dropdown>
            <el-dropdown-menu class="tp-card-menu">
              <el-dropdown-item
                v-for="item in menu"
                :key="item.action"
                :command="item.action"
                :disabled="item.disabled"
                :class="{ danger: item.danger }"
              >
                {{ t(item.label) }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chev">▸</span>
      </span>
    </span>

    <span class="line-2">{{ task.brief }}</span>

    <span class="meta">
      <span>{{ task.adapter ?? '—' }}</span>
      <span>{{ t('card.attempt') }} {{ task.attempt ?? 0 }}</span>
      <span>{{ duration(task.started_at, task.finished_at) }}</span>
      <span>{{ t('card.files') }} {{ task.files_changed ?? 0 }}</span>
    </span>

    <!-- The queue's order: a "same wave" chip whose colour reads as the wave,
         and the one number -- the seq itself -- editable in place. Only a
         queued row has a place. -->
    <span v-if="queued" class="qbar" @click.stop>
      <span class="wave" :class="waveClass" :title="t('task.queue.waveHint')">
        {{ t('task.queue.wave') }}
      </span>
      <span class="qlab">{{ t('task.queue.order') }}</span>
      <el-input-number
        class="qseq"
        size="small"
        controls-position="right"
        :min="0"
        :model-value="task.queue_seq ?? 0"
        @change="(v: number | undefined) => v != null && emit('reorder', v)"
      />
    </span>
  </div>
</template>

<style scoped>
.tp-card {
  display: block;
  width: 100%;
  position: relative;
  overflow: hidden;
  text-align: left;
  background-color: var(--panel);
  background-image: linear-gradient(var(--w), var(--w));
  border: 1px solid var(--rule);
  border-left: 3px solid var(--c);
  border-radius: var(--r-card);
  padding: 8px 10px 9px 11px;
  color: var(--ink);
  cursor: pointer;
  font: inherit;
}
.tp-card + .tp-card {
  margin-top: 6px;
}
.tp-card:hover {
  background-image: linear-gradient(var(--w), var(--w)), linear-gradient(var(--rule-2), var(--rule-2));
}
.tp-card[aria-expanded='true'] {
  box-shadow: 0 0 0 2px var(--accent);
}
.tp-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.line-1 {
  display: flex;
  align-items: center;
  gap: 7px;
}
.cid {
  font: 10px/1 var(--mono);
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tail {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 5px;
  flex: none;
}
.stamp {
  font: 600 9.5px/1 var(--mono);
  color: var(--ink-3);
  border: 1px solid var(--rule);
  border-radius: 5px;
  padding: 2px 5px;
}
.stamp.good {
  color: var(--ok);
  border-color: transparent;
  background: var(--w-done);
}
.stamp.bad {
  color: var(--c-failed);
  border-color: transparent;
  background: var(--w-failed);
}
/* The actions menu trigger: quiet until the card is hovered or the menu is
   open, so it does not compete with the lamp and the id. */
.menu-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--ink-4);
  font: 12px/1 var(--sans);
  cursor: pointer;
  opacity: 0;
}
.tp-card:hover .menu-btn,
.menu-btn:focus-visible {
  opacity: 1;
}
.menu-btn:hover {
  background: var(--raise);
  color: var(--ink);
}
/* The chevron is the disclosure affordance: it turns to point down while the
   drawer is open. */
.chev {
  font: 8px/1 var(--sans);
  color: var(--ink-4);
  transition: transform 0.15s;
}
.tp-card[aria-expanded='true'] .chev {
  transform: rotate(90deg);
  color: var(--ink-2);
}
.line-2 {
  display: -webkit-box;
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.45;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: var(--ink);
}
.tp-card[data-status='queued'] .line-2,
.tp-card[data-status='done'] .line-2 {
  color: var(--ink-2);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 7px;
  font: 9.5px/1 var(--mono);
  color: var(--ink-4);
}
/* The queue strip: wave chip, the label, and the editable number. */
.qbar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px dashed var(--rule);
}
.qbar .qlab {
  font: 9.5px/1 var(--sans);
  color: var(--ink-4);
}
.qbar .wave {
  flex: none;
  font: 600 9.5px/1 var(--sans);
  padding: 3px 7px;
  border-radius: var(--r-pill);
  color: var(--wv-ink);
  background: var(--wv-bg);
}
/* A fixed palette: same index, same colour -- the whole point of the chip.
   Numbers stay legible on both themes (the ink is the darker system hue). */
.wave.w0 { --wv-ink: #0a84ff; --wv-bg: rgba(10, 132, 255, 0.16); }
.wave.w1 { --wv-ink: #30d158; --wv-bg: rgba(48, 209, 88, 0.16); }
.wave.w2 { --wv-ink: #bf5af2; --wv-bg: rgba(191, 90, 242, 0.16); }
.wave.w3 { --wv-ink: #ff9f0a; --wv-bg: rgba(255, 159, 10, 0.16); }
.wave.w4 { --wv-ink: #ff375f; --wv-bg: rgba(255, 55, 95, 0.16); }
.wave.w5 { --wv-ink: #5e5ce6; --wv-bg: rgba(94, 92, 230, 0.16); }
.qseq {
  width: 92px;
  margin-left: auto;
}
@media (prefers-reduced-motion: reduce) {
  .chev {
    transition: none;
  }
}
</style>

<!-- The dropdown is teleported out of this component, so scoped styles cannot
     reach it. Keyed off the menu's own class, like FilterBar's, so it cannot
     leak into any other Element Plus dropdown. -->
<style>
.tp-card-menu .el-dropdown-menu__item.danger {
  color: var(--c-failed);
}
.tp-card-menu .el-dropdown-menu__item.danger.is-disabled {
  color: var(--ink-4);
}
</style>
