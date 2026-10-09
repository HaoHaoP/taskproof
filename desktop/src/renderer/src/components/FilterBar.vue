<script setup lang="ts">
/**
 * The toolbar above the data views: which projects the matrix shows, and
 * whether the app is still polling for changes.
 *
 * Presentational, like every other component here: it reads its props and
 * emits intent. The count is derived from the same props the dropdown renders,
 * so the "shown / total" number and the tick marks cannot disagree.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Project } from '../api/client'

const props = defineProps<{
  projects: Project[]
  /** Absent means visible -- a new project shows up without an entry here. */
  visible: Record<string, boolean>
  polling: boolean
}>()

const emit = defineEmits<{
  toggle: [id: string]
  selectAll: [on: boolean]
  compose: []
}>()

const { t } = useI18n()

const shown = computed(
  () => props.projects.filter((project) => props.visible[project.id] !== false).length
)

function isOn(id: string): boolean {
  return props.visible[id] !== false
}
</script>

<template>
  <div class="toolbar">
    <el-dropdown trigger="click" :hide-on-click="false" placement="bottom-start">
      <button class="pfilter" type="button">
        <span>{{ t('rail.title') }}</span>
        <span class="n">{{ shown }} / {{ projects.length }}</span>
        <span class="cv">▾</span>
      </button>
      <template #dropdown>
        <el-dropdown-menu class="tp-filter-menu">
          <el-dropdown-item
            v-for="project in projects"
            :key="project.id"
            @click="emit('toggle', project.id)"
          >
            <span class="mcheck">{{ isOn(project.id) ? '✓' : '' }}</span>
            <span class="mname">{{ project.id }}</span>
            <span class="mnum">
              {{ project.tasks }}<template v-if="project.failed"> · {{ project.failed }}</template>
            </span>
          </el-dropdown-item>
          <el-dropdown-item divided @click="emit('selectAll', true)">
            {{ t('rail.all') }}
          </el-dropdown-item>
          <el-dropdown-item @click="emit('selectAll', false)">
            {{ t('rail.none') }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <el-button class="newtask" type="primary" size="small" @click="emit('compose')">
      {{ t('task.new') }}
    </el-button>

    <div class="spacer" />

    <span class="live" :data-off="polling ? null : ''">
      <i />{{ polling ? t('live.on') : t('live.off') }}
    </span>
  </div>
</template>

<style scoped>
.toolbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--bar);
  padding: 0 16px;
  border-bottom: 1px solid var(--rule-2);
}
.newtask {
  flex: none;
  height: 28px;
}
.spacer {
  flex: 1;
}
.pfilter {
  display: flex;
  align-items: center;
  gap: 7px;
  font: 12.5px/1 var(--sans);
  color: var(--ink);
  background: var(--panel);
  border: 1px solid var(--rule);
  border-radius: var(--r-ctl);
  padding: 6px 11px;
  height: 28px;
  cursor: pointer;
}
.pfilter:hover {
  background: var(--raise);
}
.pfilter .n {
  font: 11px/1 var(--mono);
  color: var(--ink-3);
}
.pfilter .cv {
  font: 8px/1 var(--sans);
  color: var(--ink-4);
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
  animation: tp-live 1.6s ease-in-out infinite;
}
.live[data-off] i {
  background: var(--ink-4);
  animation: none;
}
@keyframes tp-live {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}
@media (prefers-reduced-motion: reduce) {
  .live i {
    animation: none;
  }
}
</style>

<!--
  The dropdown menu is teleported out of this component, so scoped styles cannot
  reach it. These rules are keyed off the class put on the menu itself rather
  than left global, so they cannot leak into any other Element Plus dropdown.
-->
<style>
.tp-filter-menu .mcheck {
  width: 15px;
  flex: none;
  font: 11px/1 var(--sans);
  display: inline-block;
}
.tp-filter-menu .mname {
  font-family: var(--mono);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tp-filter-menu .mnum {
  float: right;
  font: 11px/1.3 var(--mono);
  opacity: 0.65;
  margin-left: 14px;
}
</style>
