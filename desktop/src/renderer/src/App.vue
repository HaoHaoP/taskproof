<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import FilterBar from './components/FilterBar.vue'
import { useBoardStore } from './stores/board'
import { useSettingsStore } from './stores/settings'

const store = useBoardStore()
const settings = useSettingsStore()
const route = useRoute()
const { t } = useI18n()

const views = [
  { name: 'matrix', key: 'nav.matrix', path: '/matrix' },
  { name: 'projects', key: 'nav.projects', path: '/projects' },
  { name: 'tasks', key: 'nav.tasks', path: '/tasks' },
  { name: 'settings', key: 'nav.settings', path: '/settings' }
]

//: The toolbar belongs to the three data views; settings has nothing to filter.
const isDataView = computed(() => ['matrix', 'projects', 'tasks'].includes(String(route.name)))

/**
 * Which full-page state to show, if any.
 *
 * Not the prototype's `!ready`: there, "ready" was a constant, so the check was
 * really "did we fail". Here the service genuinely takes a moment to come up,
 * and a launch that is merely slow is not an error -- claiming otherwise would
 * flash a full-page failure on every start.
 */
const blank = computed<'offline' | 'empty' | null>(() => {
  if (store.connected) return store.projects.length === 0 ? 'empty' : null
  return store.lastError ? 'offline' : null
})

onMounted(async () => {
  await settings.load()
  await store.watchService()
  store.setPoll(settings.settings.poll)
})

onBeforeUnmount(() => store.dispose())
</script>

<template>
  <div class="app">
    <header class="mast">
      <span class="title">{{ t('app.title') }}</span>
      <span class="stats">
        <span>{{ store.tasks.length }} {{ t('tally.tasks') }}</span>
        <span>{{ store.inFlightCount }} {{ t('tally.flying') }}</span>
        <span :class="{ bad: store.abnormalCount > 0 }">
          {{ store.abnormalCount }} {{ t('tally.failed') }}
        </span>
        <span class="live" :class="{ on: store.connected }">
          <i />
          {{ t('service.local') }} · {{ store.service.port ?? '—' }}
        </span>
      </span>
    </header>

    <!-- Nothing to show. The whole shell gives way, as in the prototype: with no
         projects there is nothing to navigate to, so the nav would be a lie. -->
    <section v-if="blank" class="blank">
      <div class="big">{{ t(blank === 'offline' ? 'offline.title' : 'empty.projects') }}</div>
      <p class="hint">{{ t(blank === 'offline' ? 'offline.hint' : 'empty.hint') }}</p>
      <code>{{
        blank === 'offline' ? 'taskproof api --port 0' : 'taskproof register <path>'
      }}</code>
      <button v-if="blank === 'offline'" class="retry" type="button" @click="store.retry()">
        {{ t('service.retry') }}
      </button>
      <p v-if="blank === 'offline' && store.lastError" class="detail">{{ store.lastError }}</p>
    </section>

    <div v-else class="shell">
      <nav class="nav">
        <RouterLink v-for="view in views" :key="view.name" class="nitem" :to="view.path">
          {{ t(view.key) }}
        </RouterLink>
      </nav>

      <main class="content">
        <FilterBar
          v-if="isDataView"
          :projects="store.projects"
          :visible="store.visible"
          :polling="store.polling"
          @toggle="store.toggleProject"
          @select-all="store.selectAllProjects"
        />

        <!-- The API reported a status word this build does not know. It is still
             rendered; this banner is how the drift becomes visible instead of
             silently mislabelling a task. Not in the prototype: there the word
             list was hard-coded, so it could not drift. -->
        <div v-if="store.unknownWords.length" class="banner drift">
          <strong>{{ t('drift.title') }}</strong>
          <span class="detail">{{ store.unknownWords.join(', ') }}</span>
          <span>{{ t('drift.hint') }}</span>
        </div>

        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
}
.mast {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--mast);
  flex: none;
  padding: 0 14px;
  background: var(--side);
  border-bottom: 1px solid var(--rule);
  backdrop-filter: saturate(180%) blur(20px);
}
.title {
  font: 600 13px/1 var(--sans);
}
.stats {
  display: flex;
  align-items: center;
  gap: 14px;
  font: 11px/1 var(--mono);
  color: var(--ink-3);
}
.stats .bad {
  color: var(--c-failed);
  font-weight: 600;
}
.live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.live i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ink-4);
}
.live.on i {
  background: var(--ok);
}
.shell {
  display: flex;
  flex: 1;
  min-height: 0;
}
.nav {
  width: var(--nav);
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 8px;
  background: var(--side);
  border-right: 1px solid var(--rule);
}
.nitem {
  display: block;
  padding: 7px 10px;
  border-radius: var(--r-ctl);
  font-size: 13px;
  color: var(--ink-2);
  text-decoration: none;
}
.nitem:hover {
  background: var(--rule-2);
}
.nitem.router-link-active {
  background: var(--accent);
  color: #fff;
}
.content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.banner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 12px 14px 0;
  padding: 10px 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--rule);
  background: var(--sunken);
  font-size: 12.5px;
  color: var(--ink-2);
}
.banner strong {
  color: var(--ink);
}
.banner.drift {
  border-color: var(--c-blocked);
}
.banner .detail {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-4);
  overflow-wrap: anywhere;
}
/* Nothing to show: offline, or no projects registered. */
.blank {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 0 24px;
  text-align: center;
  color: var(--ink-4);
}
.blank .big {
  font: 600 15px/1.3 var(--sans);
  color: var(--ink-2);
}
.blank .hint {
  margin: 0;
  font: 12px/1.6 var(--sans);
  color: var(--ink-3);
  max-width: 440px;
}
.blank code {
  font: 11.5px/1.5 var(--mono);
  background: var(--sunken);
  border-radius: var(--r-ctl);
  padding: 5px 9px;
  color: var(--ink-2);
}
.blank .retry {
  margin-top: 4px;
  font: 12.5px/1 var(--sans);
  font-weight: 500;
  color: #fff;
  background: var(--accent);
  border-radius: var(--r-ctl);
  padding: 7px 14px;
  cursor: pointer;
}
.blank .retry:hover {
  filter: brightness(1.08);
}
.blank .detail {
  margin: 0;
  font-family: var(--mono);
  font-size: 11px;
  overflow-wrap: anywhere;
}
</style>
