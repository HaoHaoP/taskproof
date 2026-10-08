<script setup lang="ts">
/**
 * The About sheet: the same `el-dialog sheet` frame the project editors use,
 * at the 500px width the remove sheet set. It is mounted once at the app root
 * so the macOS "About Taskproof" menu item opens it from any page; the settings
 * row opens the same instance by flipping the shared `aboutOpen` flag.
 *
 * The close path goes through `SHEET_TRANSITION` exactly like the project
 * sheets -- card 15's fix, which stops a closed sheet from leaving its mask
 * over the page when the window was occluded.
 *
 * Versions and paths are read from the main process and shown verbatim; a value
 * that is missing (no CLI installed, path unknown) becomes an em dash, never a
 * fabricated number. The copy button assembles a whitelist of fields -- no
 * write token is available to this process, so none can leak.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { SHEET_TRANSITION } from './sheetTransition'
// Bundled by Vite (hashed into renderer assets), so the mark resolves in both
// `electron-vite dev` and a packaged build -- not a path that only exists on
// the dev machine (TP-card25).
import iconUrl from '../../../../build/icon.png'
import {
  EM_DASH,
  aboutOpen,
  aboutPaths,
  buildDiagnostics,
  cliVersionLabel,
  openAbout,
  runtimeLabel
} from './about'
import { useBoardStore } from '../stores/board'
import { useSettingsStore } from '../stores/settings'
import type { AboutInfo, RuntimeVersions } from '../../../preload/types'


const { t } = useI18n()
const settings = useSettingsStore()
const board = useBoardStore()

const info = ref<AboutInfo | null>(null)
const copied = ref(false)
let unsubscribe: (() => void) | null = null

const appVersion = computed(() => info.value?.version || settings.version || EM_DASH)
const cliVersion = computed(() => cliVersionLabel(info.value?.cliVersion))
const runtime = computed(() => runtimeLabel(info.value?.runtime ?? emptyRuntime()))

function emptyRuntime(): RuntimeVersions {
  return { electron: '', chrome: '', node: '' }
}

const paths = computed(() => aboutPaths(settings.settings.workspace, info.value?.userData ?? ''))

async function load(): Promise<void> {
  const tp = window.tp
  if (!tp) return
  try {
    info.value = await tp.app.about()
  } catch {
    // A failed read leaves the version cells at their em-dash fallback rather
    // than blanking the sheet or surfacing an error the user cannot act on.
    info.value = null
  }
}

async function copy(): Promise<void> {
  const tp = window.tp
  if (!tp) return
  const text = buildDiagnostics({
    version: info.value?.version ?? settings.version,
    cliVersion: info.value?.cliVersion ?? null,
    runtime: info.value?.runtime ?? emptyRuntime(),
    workspace: settings.settings.workspace,
    service: { state: board.service.state, port: board.service.port },
    paths: paths.value
  })
  await tp.app.copyText(text)
  copied.value = true
}

function openRepo(): void {
  void window.tp?.shell.openExternal('https://github.com/HaoHaoP/taskproof')
}

function reveal(target: string): void {
  if (!target || target === EM_DASH) return
  void window.tp?.shell.reveal(target)
}

onMounted(() => {
  unsubscribe = window.tp?.app.onShowAbout(() => openAbout()) ?? null
  if (aboutOpen.value) void load()
})

onBeforeUnmount(() => unsubscribe?.())

watch(aboutOpen, (open) => {
  if (open) {
    info.value = null
    copied.value = false
    void load()
  }
})
</script>

<template>
  <el-dialog v-model="aboutOpen" :transition="SHEET_TRANSITION" class="sheet" width="500">
    <template #header><span>{{ t('about.title') }}</span></template>

    <div class="about-head">
      <img class="about-logo" :src="iconUrl" alt="Taskproof" />
      <div>
        <div class="about-name">Taskproof · 调度台</div>
        <div class="about-source">{{ t('about.source') }}</div>
      </div>
    </div>

    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.appVersion') }}</div></div>
      <div class="ctl"><span class="ro mono">{{ appVersion }}</span></div>
    </div>
    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.cliVersion') }}</div></div>
      <div class="ctl"><span class="ro mono">{{ cliVersion }}</span></div>
    </div>
    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.runtime') }}</div></div>
      <div class="ctl"><span class="ro mono">{{ runtime }}</span></div>
    </div>

    <div class="setrow">
      <div class="lab">
        <div class="t">{{ t('about.repo') }}</div>
        <div class="d">{{ t('about.repoHint') }}</div>
      </div>
      <div class="ctl">
        <button class="about-link" type="button" @click="openRepo">
          github.com/HaoHaoP/taskproof
        </button>
      </div>
    </div>
    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.license') }}</div></div>
      <div class="ctl"><span class="ro">Apache-2.0</span></div>
    </div>

    <div class="setrow about-paths-head">
      <div class="lab"><div class="t">{{ t('about.paths') }}</div></div>
    </div>
    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.userData') }}</div></div>
      <div class="ctl wide">
        <button class="about-path mono" type="button" @click="reveal(paths.userData)">
          {{ paths.userData }}
        </button>
      </div>
    </div>
    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.registry') }}</div></div>
      <div class="ctl wide">
        <button class="about-path mono" type="button" @click="reveal(paths.registry)">
          {{ paths.registry }}
        </button>
      </div>
    </div>
    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.database') }}</div></div>
      <div class="ctl wide">
        <button class="about-path mono" type="button" @click="reveal(paths.database)">
          {{ paths.database }}
        </button>
      </div>
    </div>
    <div class="setrow">
      <div class="lab"><div class="t">{{ t('about.events') }}</div></div>
      <div class="ctl wide">
        <button class="about-path mono" type="button" @click="reveal(paths.events)">
          {{ paths.events }}
        </button>
      </div>
    </div>

    <template #footer>
      <el-button size="small" @click="aboutOpen = false">{{ t('dlg.cancel') }}</el-button>
      <el-button size="small" type="primary" @click="copy">
        {{ copied ? t('about.copied') : t('about.copy') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.about-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px 12px;
}
.about-logo {
  width: 48px;
  height: 48px;
  border-radius: 11px;
  flex: none;
}
.about-name {
  font: 600 15px/1.3 var(--sans);
  color: var(--ink);
}
.about-source {
  margin-top: 3px;
  font: 12px/1.45 var(--sans);
  color: var(--ink-3);
}
.about-link {
  border: none;
  background: none;
  padding: 0;
  font: 12px/1.4 var(--sans);
  color: var(--accent);
  cursor: pointer;
}
.about-link:hover {
  text-decoration: underline;
}
.about-path {
  border: none;
  background: none;
  padding: 0;
  text-align: left;
  color: var(--ink-2);
  cursor: pointer;
  overflow-wrap: anywhere;
}
.about-path:hover {
  color: var(--accent);
  text-decoration: underline;
}
.about-paths-head {
  padding-bottom: 2px;
}
.mono {
  font-family: var(--mono);
}
</style>
