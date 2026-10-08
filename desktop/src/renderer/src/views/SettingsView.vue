<script setup lang="ts">
/**
 * Settings, following the prototype: a grouped list page -- grey canvas, white
 * cards, one hairline-inset row per setting.
 *
 * The controls are segmented rather than dropdowns, as in the prototype: there
 * are two or three mutually exclusive choices per row and no more, so a select
 * would hide them behind a click for no reason.
 *
 * The desktop-integration switches only persist here (type + settings.json);
 * the tray, the Dock badge, the notifications and the login item that read them
 * are wired up in a later card -- but a switch that never reached the file would
 * be decoration, so these write through the main process like every other row.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { openAbout } from '../components/about'
import { STATUS_IDS, VERIFY_KINDS } from '../contract'
import { useBoardStore } from '../stores/board'
import { useSettingsStore } from '../stores/settings'
import type {
  AdapterStatus,
  LanguageChoice,
  LaunchMode,
  PollChoice,
  PortMode,
  ThemeChoice
} from '../../../preload/types'

const board = useBoardStore()
const settings = useSettingsStore()
const { t } = useI18n()

const contractLine = computed(() =>
  board.unknownWords.length ? t('settings.contractDrift') : t('settings.contractSynced')
)

/** The home directory reads better as `~` in a settings row. */
const workspaceLabel = computed(() => {
  const path = settings.settings.workspace ?? ''
  const short = path.replace(/^\/Users\/[^/]+/, '~')
  return short || '~/.taskproof'
})

/** `~/.taskproof/projects.toml`, the file the registry row opens. */
const registryPath = computed(() => {
  const ws = (settings.settings.workspace || '~/.taskproof').replace(/\/+$/, '')
  return `${ws}/projects.toml`
})

const languageOptions = computed(() => [
  { label: t('lang.system'), value: 'system' },
  { label: '中文', value: 'zh-CN' },
  { label: 'EN', value: 'en' }
])
const themeOptions = computed(() => [
  { label: t('theme.dark'), value: 'dark' },
  { label: t('theme.light'), value: 'light' },
  { label: t('theme.system'), value: 'system' }
])
const pollOptions = computed(() => [
  { label: t('settings.pollOn'), value: '2s' },
  { label: t('settings.pollOff'), value: 'off' }
])
const portModeOptions = computed(() => [
  { label: t('settings.portmodeAuto'), value: 'auto' },
  { label: t('settings.portmodeFixed'), value: 'fixed' }
])
const launchOptions = computed(() => [
  { label: t('settings.launchAuto'), value: 'auto' },
  { label: t('settings.launchManual'), value: 'manual' }
])

/**
 * The adapter lamps. `taskproof doctor --json` is the only honest source -- the
 * frozen REST API has no adapter endpoint -- and it answers null when it cannot
 * run, which the row shows as a dash rather than inventing a verdict.
 */
const adapters = ref<AdapterStatus[] | null>(null)
onMounted(async () => {
  const tp = window.tp
  if (!tp) return
  adapters.value = await tp.app.adapters()
})

function onLanguage(value: unknown): void {
  settings.setLanguage(value as LanguageChoice)
}
function onTheme(value: unknown): void {
  settings.setTheme(value as ThemeChoice)
}
function onPoll(value: unknown): void {
  settings.setPoll(value as PollChoice)
}
function onPortMode(value: unknown): void {
  settings.setPortMode(value as PortMode)
}
function onLaunch(value: unknown): void {
  settings.setLaunch(value as LaunchMode)
}
function onPort(value: unknown): void {
  const port = Number(value)
  // An empty or malformed box must not write 0; the file keeps the last good port.
  if (Number.isFinite(port) && port > 0) settings.setPort(port)
}
function onTaskproofPath(value: unknown): void {
  settings.setTaskproofPath(String(value))
}
function openRegistry(): void {
  void window.tp?.shell.openPath(registryPath.value)
}
</script>

<template>
  <div class="settings-view">
    <div class="panes grouped">
      <div class="setwrap">
        <h3>{{ t('settings.title') }}</h3>
        <p class="sub">{{ t('settings.sub') }}</p>

        <section class="setgroup">
          <h4>{{ t('settings.appearance') }}</h4>
          <div class="setcard">
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.language') }}</div>
              </div>
              <div class="ctl">
                <el-segmented
                  :model-value="settings.settings.language"
                  size="small"
                  :options="languageOptions"
                  @update:model-value="onLanguage"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.theme') }}</div>
                <div class="d">{{ t('settings.themeDesc') }}</div>
              </div>
              <div class="ctl">
                <el-segmented
                  :model-value="settings.settings.theme"
                  size="small"
                  :options="themeOptions"
                  @update:model-value="onTheme"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.poll') }}</div>
                <div class="d">{{ t('settings.pollDesc') }}</div>
              </div>
              <div class="ctl">
                <el-segmented
                  :model-value="settings.settings.poll"
                  size="small"
                  :options="pollOptions"
                  @update:model-value="onPoll"
                />
              </div>
            </div>
          </div>
        </section>

        <section class="setgroup">
          <h4>{{ t('settings.service') }}</h4>
          <div class="setcard">
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.portmode') }}</div>
                <div class="d">{{ t('settings.portmodeDesc') }}</div>
              </div>
              <div class="ctl">
                <el-segmented
                  :model-value="settings.settings.portMode"
                  size="small"
                  :options="portModeOptions"
                  @update:model-value="onPortMode"
                />
              </div>
            </div>
            <div v-if="settings.settings.portMode === 'fixed'" class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.port') }}</div>
                <div class="d">{{ t('settings.portDesc') }}</div>
              </div>
              <div class="ctl">
                <el-input
                  :model-value="String(settings.settings.port)"
                  type="number"
                  size="small"
                  style="width: 110px"
                  @update:model-value="onPort"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.taskproof') }}</div>
                <div class="d">{{ t('settings.taskproofDesc') }}</div>
              </div>
              <div class="ctl wide">
                <el-input
                  :model-value="settings.settings.taskproofPath"
                  size="small"
                  placeholder="/opt/homebrew/bin/taskproof"
                  @update:model-value="onTaskproofPath"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.workspace') }}</div>
                <div class="d">{{ t('settings.workspaceDesc') }}</div>
              </div>
              <div class="ctl">
                <span class="ro">{{ workspaceLabel }}</span>
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.launch') }}</div>
              </div>
              <div class="ctl">
                <el-segmented
                  :model-value="settings.settings.launch"
                  size="small"
                  :options="launchOptions"
                  @update:model-value="onLaunch"
                />
              </div>
            </div>
          </div>
        </section>

        <section class="setgroup">
          <h4>{{ t('settings.desktop') }}</h4>
          <div class="setcard">
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.notifyFail') }}</div>
              </div>
              <div class="ctl">
                <el-switch
                  :model-value="settings.settings.notifyFail"
                  @change="settings.setFlag('notifyFail', $event)"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.notifyDone') }}</div>
              </div>
              <div class="ctl">
                <el-switch
                  :model-value="settings.settings.notifyDone"
                  @change="settings.setFlag('notifyDone', $event)"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.dockBadge') }}</div>
              </div>
              <div class="ctl">
                <el-switch
                  :model-value="settings.settings.dockBadge"
                  @change="settings.setFlag('dockBadge', $event)"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.tray') }}</div>
                <div class="d">{{ t('settings.trayDesc') }}</div>
              </div>
              <div class="ctl">
                <el-switch
                  :model-value="settings.settings.tray"
                  @change="settings.setFlag('tray', $event)"
                />
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.autostart') }}</div>
              </div>
              <div class="ctl">
                <el-switch
                  :model-value="settings.settings.autostart"
                  @change="settings.setFlag('autostart', $event)"
                />
              </div>
            </div>
          </div>
        </section>

        <section class="setgroup">
          <h4>{{ t('settings.about') }}</h4>
          <div class="setcard">
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.aboutTaskproof') }}</div>
                <div class="d">{{ t('settings.aboutTaskproofDesc') }}</div>
              </div>
              <div class="ctl">
                <el-button size="small" @click="openAbout">
                  {{ t('about.open') }}
                </el-button>
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.version') }}</div>
              </div>
              <div class="ctl">
                <span class="ro">{{ settings.version || '0.1.0' }}</span>
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.adapters') }}</div>
                <div class="d">{{ t('settings.adaptersDesc') }}</div>
              </div>
              <div class="ctl">
                <div v-if="adapters && adapters.length" class="alamps">
                  <span
                    v-for="a in adapters"
                    :key="a.name"
                    class="alamp"
                    :class="{ bad: !a.installed }"
                    :title="a.detail"
                  >
                    <i></i>{{ a.name }}
                  </span>
                </div>
                <span v-else class="ro">—</span>
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.limits') }}</div>
                <div class="d">{{ t('settings.limitsDesc') }}</div>
              </div>
              <!-- No API or registry source for these yet: show a dash, not a number. -->
              <div class="ctl">
                <span class="ro">—</span>
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.token') }}</div>
                <div class="d">{{ t('settings.tokenDesc') }}</div>
              </div>
              <!-- The token itself lives only in the main process; never render it. -->
              <div class="ctl">
                <span class="ro">{{ t('settings.tokenValue') }}</span>
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.registry') }}</div>
                <div class="d">{{ registryPath }}</div>
              </div>
              <div class="ctl">
                <el-button size="small" @click="openRegistry">
                  {{ t('settings.openRegistry') }}
                </el-button>
              </div>
            </div>
            <div class="setrow">
              <div class="lab">
                <div class="t">{{ t('settings.contract') }}</div>
                <div class="d">{{ contractLine }}</div>
              </div>
              <div class="ctl">
                <span class="ro">
                  {{ STATUS_IDS.length }} {{ t('status.label') }} · {{ VERIFY_KINDS.join(' / ') }}
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
</style>
