<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import FilterBar from './components/FilterBar.vue'
import { ICONS } from './icons'
import { shellPlaceholder } from './shell'
import { useBoardStore } from './stores/board'
import { useSettingsStore } from './stores/settings'

const store = useBoardStore()
const settings = useSettingsStore()
const route = useRoute()
const { t } = useI18n()

/** The three data views. Settings sits below a separator, as in the prototype. */
const mainViews = [
  { name: 'matrix', key: 'nav.matrix', path: '/matrix' },
  { name: 'projects', key: 'nav.projects', path: '/projects' },
  { name: 'tasks', key: 'nav.tasks', path: '/tasks' }
] as const
const settingsView = { name: 'settings', key: 'nav.settings', path: '/settings' } as const

/** The rail collapses the whole nav away; shown by default. */
const rail = ref(true)

//: The toolbar belongs to the three data views; settings has nothing to filter.
const isDataView = computed(() => ['matrix', 'projects', 'tasks'].includes(String(route.name)))

/**
 * Which placeholder the matrix body shows, if any.
 *
 * The rule lives in `shell.ts` so it can be unit-tested: only the matrix body
 * ever gives way, the nav stays put in every state, and the projects / tasks /
 * settings pages keep their real layouts -- which is what lets a first project
 * be registered out of an empty registry.
 *
 * Not the prototype's `!ready`: there, "ready" was a constant, so the check was
 * really "did we fail". Here the service genuinely takes a moment to come up,
 * and a launch that is merely slow is not an error -- claiming otherwise would
 * flash a full-page failure on every start.
 */
const blank = computed(() =>
  shellPlaceholder({
    connected: store.connected,
    projectCount: store.projects.length,
    lastError: store.lastError,
    routeName: route.name == null ? null : String(route.name)
  })
)

onMounted(async () => {
  await settings.load()
  await store.watchService()
  store.setPoll(settings.settings.poll)
})

onBeforeUnmount(() => store.dispose())
</script>

<template>
  <div class="app">
    <!-- The whole mast is draggable; the one interactive control opts back out. -->
    <header class="mast">
      <button
        class="mastbtn"
        type="button"
        :aria-label="t(rail ? 'nav.collapse' : 'nav.expand')"
        :title="t(rail ? 'nav.collapse' : 'nav.expand')"
        v-html="rail ? ICONS.collapse : ICONS.expand"
        @click="rail = !rail"
      ></button>
      <div class="id">Taskproof <em>· {{ t('app.subtitle') }}</em></div>
      <div class="spacer"></div>
      <div class="tally">
        <span>{{ t('tally.tasks') }}<b>{{ store.tasks.length }}</b></span>
        <span>{{ t('tally.flying') }}<b>{{ store.inFlightCount }}</b></span>
        <span class="alarm">{{ t('tally.failed') }}<b>{{ store.abnormalCount }}</b></span>
      </div>
      <div class="svc" :data-state="store.connected ? 'on' : 'off'">
        <i></i>
        <span v-if="store.connected">{{ t('service.local') }} :{{ store.service.port ?? '—' }}</span>
        <span v-else>{{ t('service.offline') }}</span>
      </div>
    </header>

    <div class="shell">
      <nav v-show="rail" class="nav">
        <template v-for="view in mainViews" :key="view.name">
          <RouterLink custom :to="view.path" v-slot="{ href, navigate, isActive }">
            <a
              class="nitem"
              :href="href"
              :aria-current="isActive ? 'page' : undefined"
              @click="navigate"
            >
              <span v-html="ICONS[view.name]"></span>{{ t(view.key) }}
            </a>
          </RouterLink>
        </template>
        <div class="nsep"></div>
        <RouterLink custom :to="settingsView.path" v-slot="{ href, navigate, isActive }">
          <a class="nitem" :href="href" :aria-current="isActive ? 'page' : undefined" @click="navigate">
            <span v-html="ICONS[settingsView.name]"></span>{{ t(settingsView.key) }}
          </a>
        </RouterLink>
      </nav>

      <main class="content">
        <FilterBar
          v-if="isDataView && !blank"
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

        <!-- Offline, or a registry with nothing in it yet: this replaces the
             matrix body only. The nav above never gives way, and the projects
             page keeps its real layout -- that is where the first project is
             registered. -->
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
        <RouterView v-else />
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
/* Title bar. Copied from the prototype's `.mast` -- including the 78px left
   inset, which reserves room for the OS traffic lights (titleBarStyle:
   hiddenInset). `-webkit-app-region: drag` lets the window be dragged by it. */
.mast {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  height: var(--mast);
  flex: none;
  padding: 0 14px 0 78px;
  background: var(--side);
  border-bottom: 1px solid var(--rule);
  backdrop-filter: blur(30px) saturate(180%);
  -webkit-backdrop-filter: blur(30px) saturate(180%);
  -webkit-app-region: drag;
}
.mastbtn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  color: var(--ink-3);
  -webkit-app-region: no-drag;
}
.mastbtn:hover {
  background: var(--rule-2);
  color: var(--ink);
}
.id {
  font: 600 14px/1 var(--sans);
  letter-spacing: -0.01em;
  white-space: nowrap;
}
.id em {
  font-style: normal;
  font-weight: 400;
  color: var(--ink-3);
}
.spacer {
  flex: 1;
}
.tally {
  display: flex;
  gap: 16px;
  font: 12px/1 var(--sans);
  color: var(--ink-3);
  white-space: nowrap;
}
.tally b {
  color: var(--ink);
  font-weight: 600;
  margin-left: 5px;
}
.tally .alarm b {
  color: var(--c-failed);
}
.svc {
  display: flex;
  align-items: center;
  gap: 6px;
  font: 11.5px/1 var(--mono);
  color: var(--ink-2);
  padding: 5px 9px;
  border: 1px solid var(--rule);
  border-radius: var(--r-pill);
  background: var(--sunken);
}
.svc i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ok);
  flex: none;
}
.svc[data-state='on'] i {
  box-shadow: 0 0 6px var(--ok);
}
.svc[data-state='off'] {
  color: var(--c-failed);
  border-color: transparent;
  background: var(--w-failed);
}
.svc[data-state='off'] i {
  background: var(--c-failed);
  box-shadow: none;
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
  padding: 8px 10px 10px;
  background: var(--side);
  border-right: 1px solid var(--rule);
  backdrop-filter: blur(30px) saturate(180%);
  -webkit-backdrop-filter: blur(30px) saturate(180%);
}
.nitem {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  height: 30px;
  padding: 0 9px;
  border-radius: var(--r-ctl);
  font: 13px/1 var(--sans);
  color: var(--ink-2);
  text-decoration: none;
}
/* The icon is injected with v-html, so it carries no scope attribute -- reach
   into it explicitly. */
.nitem :deep(svg) {
  flex: none;
  opacity: 0.85;
}
.nitem:hover {
  background: var(--rule-2);
  color: var(--ink);
}
.nitem[aria-current='page'] {
  background: rgba(10, 132, 255, 0.22);
  color: var(--accent);
  font-weight: 500;
}
.nitem[aria-current='page'] :deep(svg) {
  opacity: 1;
}
html[data-theme='light'] .nitem[aria-current='page'] {
  background: rgba(0, 122, 255, 0.14);
}
.nsep {
  height: 1px;
  background: var(--rule);
  margin: 8px 9px;
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
