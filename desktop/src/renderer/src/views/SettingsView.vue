<script setup lang="ts">
/**
 * Settings is a grouped list page, so it uses the grey canvas with white cards
 * (macOS's content-page vs grouped-page distinction). Read-only this round:
 * the write path to projects.toml and the local write token come later.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { STATUS_IDS, VERIFY_KINDS } from '../contract'
import { useBoardStore } from '../stores/board'
import { useSettingsStore } from '../stores/settings'

const board = useBoardStore()
const settings = useSettingsStore()
const { t } = useI18n()

const serviceState = computed(() => t(`service.${board.service.state}`))
const contractLine = computed(() =>
  board.unknownWords.length ? t('settings.contractDrift') : t('settings.contractSynced')
)
</script>

<template>
  <div class="settings-view">
    <div class="panes grouped">
      <h2>{{ t('settings.title') }}</h2>

      <section class="group">
        <h3>{{ t('settings.appearance') }}</h3>
        <div class="card">
          <label class="row">
            <span class="label">{{ t('settings.theme') }}</span>
            <el-select
              :model-value="settings.settings.theme"
              size="small"
              style="width: 150px"
              @update:model-value="(value) => settings.setTheme(value)"
            >
              <el-option value="dark" :label="t('theme.dark')" />
              <el-option value="light" :label="t('theme.light')" />
              <el-option value="system" :label="t('theme.system')" />
            </el-select>
          </label>
          <label class="row">
            <span class="label">{{ t('settings.language') }}</span>
            <el-select
              :model-value="settings.settings.language"
              size="small"
              style="width: 150px"
              @update:model-value="(value) => settings.setLanguage(value)"
            >
              <el-option value="system" :label="t('lang.system')" />
              <el-option value="zh-CN" label="中文" />
              <el-option value="en" label="English" />
            </el-select>
          </label>
        </div>
      </section>

      <section class="group">
        <h3>{{ t('settings.service') }}</h3>
        <div class="card">
          <div class="row">
            <span class="label">{{ t('service.local') }}</span>
            <span class="value mono">{{ serviceState }} · {{ board.service.port ?? '—' }}</span>
          </div>
          <div class="row">
            <span class="label">{{ t('settings.workspace') }}</span>
            <span class="value mono">~/.taskproof</span>
          </div>
          <div class="row">
            <span class="label">{{ t('settings.taskproof') }}</span>
            <span class="value mono">{{ settings.settings.taskproofPath || 'taskproof' }}</span>
          </div>
        </div>
      </section>

      <section class="group">
        <h3>{{ t('settings.about') }}</h3>
        <div class="card">
          <div class="row">
            <span class="label">{{ t('settings.version') }}</span>
            <span class="value mono">{{ settings.version || '0.1.0' }}</span>
          </div>
          <div class="row">
            <span class="label">{{ t('settings.contract') }}</span>
            <span class="value mono">
              {{ STATUS_IDS.length }} {{ t('status.label') }} · {{ VERIFY_KINDS.join(' / ') }} ·
              {{ contractLine }}
            </span>
          </div>
        </div>
      </section>
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
/* Grouped page: grey canvas, white cards. */
.panes.grouped {
  flex: 1;
  overflow: auto;
  padding: 22px 26px 40px;
  background: var(--bg-grouped);
}
h2 {
  margin: 0 0 18px;
  font: 600 17px/1.2 var(--sans);
  color: var(--ink);
}
.group {
  max-width: 720px;
  margin-bottom: 22px;
}
h3 {
  margin: 0 0 7px 2px;
  font: 500 11.5px/1 var(--sans);
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--ink-4);
}
.card {
  background: var(--panel);
  border: 1px solid var(--rule);
  border-radius: var(--r-card);
  overflow: hidden;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 42px;
  padding: 7px 14px;
  border-bottom: 1px solid var(--rule-2);
}
.row:last-child {
  border-bottom: none;
}
.label {
  font-size: 13px;
  color: var(--ink);
}
.value {
  font-size: 11.5px;
  color: var(--ink-4);
}
.mono {
  font-family: var(--mono);
}
</style>
