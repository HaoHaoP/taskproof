<script setup lang="ts">
/**
 * The status atom. Every status mark in the app goes through this component --
 * the lamp glyph on a card, the marker in a column header, the dot on a chip.
 *
 * It sets `data-status` rather than building a class name, so the colour mapping
 * lives in tokens.css in exactly one place. An undeclared status still renders
 * (neutral), which is the whole point: never hide a task.
 */
import { computed } from 'vue'
import { metaFor } from '../contract'

const props = withDefaults(
  defineProps<{
    status: string
    /** glyph = the lamp on a card; dot = the marker in a header or chip. */
    shape?: 'glyph' | 'dot'
  }>(),
  { shape: 'glyph' }
)

const meta = computed(() => metaFor(props.status))
</script>

<template>
  <span class="tp-mark" :data-status="meta.id" :data-shape="shape">
    <span v-if="shape === 'dot'" class="dot" />
    <template v-else>{{ meta.glyph }}</template>
  </span>
</template>

<style scoped>
.tp-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  color: var(--c);
}
.tp-mark[data-shape='glyph'] {
  font: 600 11px/1 var(--mono);
}
.tp-mark[data-shape='glyph'][data-status='running'],
.tp-mark[data-shape='glyph'][data-status='verifying'] {
  text-shadow: 0 0 7px currentColor;
  animation: tp-pulse 1.6s ease-in-out infinite;
}
.tp-mark .dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c);
}
@keyframes tp-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}
@media (prefers-reduced-motion: reduce) {
  .tp-mark[data-shape='glyph'][data-status='running'],
  .tp-mark[data-shape='glyph'][data-status='verifying'] {
    animation: none;
  }
}
</style>
