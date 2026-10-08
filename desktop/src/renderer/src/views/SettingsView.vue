<script setup lang="ts">
/**
 * Settings, following the prototype: a grouped list page -- grey canvas, white
 * cards, one hairline-inset row per setting.
 *
 * The controls are segmented rather than dropdowns, as in the prototype: there
 * are two or three mutually exclusive choices per row and no more, so a select
 * would hide them behind a click for no reason.
 *
 * Not ported yet: the desktop-integration group (notify on failure / on finish,
 * Dock badge, close-to-tray). Those switches are the tray wiring's business, and
 * a switch that changes nothing is worse than a switch that is not there.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { STATUS_IDS, VERIFY_KINDS } from '../contract'
import { useBoardStore } from '../stores/board'
import { useSettingsStore } from '../stores/settings'
import type { LanguageChoice, PollChoice, ThemeChoice } from '../../../preload/types'

const board = useBoardStore()
const settings = useSettingsStore()
const { t } = useI18n()

const serviceState = computed(() => t(`service.${board.service.state}`))
const contractLine = computed(() =>
  board.unknownWords.length ? t('settings.contractDrift') : t('settings.contractSynced')
)

/** The home directory reads better as `~` in a settings row. */
const workspaceLabel = computed(() => {
  const path = settings.settings.workspace ?? ''
  const short = path.replace(/^\/Users\/[^/]+/, '~')
  return short || '~/.taskproof'
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

function onLanguage(value: unknown): void {
  settings.setLanguage(value as LanguageChoice)
}
function onTheme(value: unknown): void {
  settings.setTheme(value as ThemeChoice)
}
function onPoll(value: unknown): void {
  settings.setPoll(value as PollChoice)
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
                <div class="t">{{ t('service.local') }}</div>
                <div class="d">{{ serviceState }}</div>
              </div>
              <div class="ctl">
                <span class="ro">{{ board.service.port ? `127.0.0.1:${board.service.port}` : '—' }}</span>
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
                <div class="t">{{ t('settings.taskproof') }}</div>
                <div class="d">{{ t('settings.taskproofDesc') }}</div>
              </div>
              <div class="ctl wide">
                <span class="ro">{{ settings.settings.taskproofPath || 'taskproof' }}</span>
              </div>
            </div>
          </div>
        </section>

        <section class="setgroup">
          <h4>{{ t('settings.about') }}</h4>
          <div class="setcard">
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
