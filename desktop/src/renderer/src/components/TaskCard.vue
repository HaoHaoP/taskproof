<script setup lang="ts">
/** A task card. Pure props in, one event out: no store, no fetching. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusMark from './StatusMark.vue'
import type { Task } from '../api/client'
import { EXIT_MEANINGS } from '../contract'
import { duration } from '../format'

const props = defineProps<{ task: Task; expanded?: boolean }>()
const emit = defineEmits<{ open: [id: string] }>()

const { t } = useI18n()

const outcome = computed(() => {
  const task = props.task
  if (task.verify_exit != null) return task.verify_exit === 0 ? 'good' : 'bad'
  if (task.exit_code != null) return task.exit_code === 0 ? 'good' : 'bad'
  return ''
})

const outcomeText = computed(() => {
  const task = props.task
  if (task.verify_exit != null) return `verify ${task.verify_exit}`
  if (task.exit_code != null) return `exit ${task.exit_code}`
  return ''
})

const exitMeaning = computed(() =>
  props.task.exit_code == null ? null : (EXIT_MEANINGS[props.task.exit_code] ?? 'unknown')
)
</script>

<template>
  <button
    type="button"
    class="tp-card"
    :data-status="task.status"
    :aria-expanded="expanded ? 'true' : 'false'"
    @click="emit('open', task.id)"
  >
    <span class="line-1">
      <StatusMark :status="task.status" />
      <span class="cid">{{ task.id }}</span>
      <span class="tail">
        <span v-if="outcomeText" class="stamp" :class="outcome" :title="exitMeaning ?? ''">
          {{ outcomeText }}
        </span>
      </span>
    </span>

    <span class="line-2">{{ task.brief }}</span>

    <span class="meta">
      <span>{{ task.adapter ?? '—' }}</span>
      <span>{{ t('card.attempt') }} {{ task.attempt ?? 0 }}</span>
      <span>{{ duration(task.started_at, task.finished_at) }}</span>
      <span>{{ t('card.files') }} {{ task.files_changed ?? 0 }}</span>
    </span>
  </button>
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
</style>
