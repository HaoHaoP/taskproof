<script setup lang="ts">
/**
 * A task card. Pure props in, events out: no store, no fetching.
 *
 * Ported from the prototype's `button.card`: a state lamp, the id, then the
 * verification stamp and the disclosure chevron on the right. The stamp is the
 * verification exit code and nothing else -- `✓ 0` or `✗ N` -- and a task that
 * was never verified gets no stamp at all, because there is no verdict to show.
 *
 * The card is a div with `role="button"` rather than a real <button>, so the
 * nested interactive badges stay clickable inside it.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusMark from './StatusMark.vue'
import type { Task } from '../api/client'
import { acceptancePassed, laneLabel } from '../card'
import { duration } from '../format'

const props = defineProps<{ task: Task; expanded?: boolean }>()
const emit = defineEmits<{
  open: [id: string]
}>()

const { t } = useI18n()

/** null means "no stamp": the prototype only renders one when verify !== null. */
const stamp = computed(() => {
  const exit = props.task.verify_exit
  if (exit == null) return null
  return { text: exit === 0 ? '✓ 0' : `✗ ${exit}`, cls: exit === 0 ? 'good' : 'bad' }
})

/** The "acceptance passed" badge: shown on a blocked card whose acceptance went
 *  green (see `acceptancePassed`). It answers "the result is fine, only the
 *  boundary was crossed" without ever claiming a pass that was not earned. */
const passBadge = computed(() => acceptancePassed(props.task))

/** The lane the task ran in, from the task row itself (see `laneLabel`). Shown
 *  as one small meta item -- the existing density and colours are untouched. */
const lane = computed(() => laneLabel(props.task))
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
        <span v-if="passBadge" class="stamp good">{{ t('card.acceptancePassed') }}</span>
        <span v-if="stamp" class="stamp" :class="stamp.cls">{{ stamp.text }}</span>
        <span class="chev">▸</span>
      </span>
    </span>

    <span class="line-2">{{ task.brief }}</span>

    <span class="meta">
      <span>{{ task.adapter ?? '—' }}</span>
      <span>{{ t('card.attempt') }} {{ task.attempt ?? 0 }}</span>
      <span>{{ duration(task.started_at, task.finished_at) }}</span>
      <span>{{ t('card.files') }} {{ task.files_changed_live ?? task.files_changed ?? 0 }}</span>
      <span class="lane" :title="t('card.lane')">{{ lane }}</span>
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
@media (prefers-reduced-motion: reduce) {
  .chev {
    transition: none;
  }
}
</style>
