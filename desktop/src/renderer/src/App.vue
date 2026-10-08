<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBoardStore } from './stores/board'
import { useSettingsStore } from './stores/settings'

const store = useBoardStore()
const settings = useSettingsStore()
const { t } = useI18n()

const views = [
  { name: 'matrix', key: 'nav.matrix', path: '/matrix' },
  { name: 'projects', key: 'nav.projects', path: '/projects' },
  { name: 'tasks', key: 'nav.tasks', path: '/tasks' },
  { name: 'settings', key: 'nav.settings', path: '/settings' }
]

onMounted(async () => {
  await settings.load()
  await store.watchService()
  store.start()
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

    <div class="shell">
      <nav class="nav">
        <RouterLink v-for="view in views" :key="view.name" class="nitem" :to="view.path">
          {{ t(view.key) }}
        </RouterLink>
      </nav>

      <main class="content">
        <!-- The service not being up is a normal state, not a crash: say so and
             keep the last snapshot on screen. -->
        <div v-if="!store.connected" class="banner">
          <strong>{{ t('offline.title') }}</strong>
          <span>{{ t('offline.hint') }}</span>
          <span v-if="store.lastError" class="detail">{{ store.lastError }}</span>
        </div>

        <!-- The API reported a status word this build does not know. It is
             still rendered; this banner is how the drift becomes visible
             instead of silently mislabelling a task. -->
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
</style>
