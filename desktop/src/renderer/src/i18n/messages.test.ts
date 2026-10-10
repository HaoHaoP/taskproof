/**
 * Card 39 reshaped two settings sections and renamed one drawer heading. These
 * pins are cheap: deleting a message key leaves a translator lookup that renders
 * the raw key path, which no type catches (vue-i18n messages are `any`). So the
 * keys we *removed* are asserted absent in both locales, and the one we renamed
 * is asserted present with exactly one wording.
 */
import { describe, expect, it } from 'vitest'
import en from './en'
import zhCN from './zh-CN'

const locales = { en, 'zh-CN': zhCN } as const

/** Keys the card deleted outright; none may survive in either locale. */
const removed = ['settings.token', 'settings.tokenDesc', 'settings.tokenValue', 'drawer.claimNote']

function at(messages: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((node, part) => {
    if (node && typeof node === 'object') return (node as Record<string, unknown>)[part]
    return undefined
  }, messages)
}

describe('card 35 message keys (the needs-review lane)', () => {
  it('names the blocked column its own key, distinct from the status word', () => {
    expect(at(en, 'column.blocked')).toBe('Needs review')
    expect(at(zhCN, 'column.blocked')).toBe('待复核')
    // The status word itself is untouched -- two purposes, two keys.
    expect(at(en, 'status.blocked')).toBe('Blocked')
    expect(at(zhCN, 'status.blocked')).toBe('阻塞')
  })

  it('names the acceptance-passed badge in both locales', () => {
    // The accept *action* (and its confirm / stale copy) is gone; only the
    // read-only badge the card still shows survives.
    expect(at(en, 'card.acceptancePassed')).toBeTruthy()
    expect(at(zhCN, 'card.acceptancePassed')).toBeTruthy()
  })
})

describe('card 39 message keys', () => {
  it('drops the write-token section and the drawer claim note everywhere', () => {
    for (const [name, messages] of Object.entries(locales)) {
      for (const key of removed) {
        expect(at(messages as Record<string, unknown>, key), `${name}:${key}`).toBeUndefined()
      }
    }
  })

  it('renames the drawer heading to a self-report with one wording', () => {
    expect(at(en, 'drawer.claim')).toBe('Worker self-report')
    expect(at(zhCN, 'drawer.claim')).toBe('worker 自述')
  })
})

describe('card 47 message keys (launch source + git honesty)', () => {
  it('names each launch source once, in both locales', () => {
    expect(at(en, 'settings.source.setting')).toBe('Custom')
    expect(at(zhCN, 'settings.source.setting')).toBe('自定义')
    expect(at(en, 'settings.source.bundled')).toBe('Bundled runtime (shipped with the app)')
    expect(at(zhCN, 'settings.source.bundled')).toBe('随包运行时（应用自带）')
    expect(at(en, 'settings.source.path')).toBe('taskproof on PATH')
    expect(at(zhCN, 'settings.source.path')).toBe('PATH 上的 taskproof')
    expect(at(en, 'settings.source.python3')).toBe('python3 -m taskproof')
    expect(at(zhCN, 'settings.source.python3')).toBe('python3 -m taskproof')
  })

  it('labels the effective-command / argv / git rows in both locales', () => {
    for (const key of ['settings.launchSource', 'settings.launchArgv', 'settings.git']) {
      expect(at(en, key), `en:${key}`).toBeTruthy()
      expect(at(zhCN, key), `zh:${key}`).toBeTruthy()
    }
  })

  it('states the missing-git truth, verbatim, in both locales', () => {
    expect(at(en, 'settings.gitMissing')).toBe(
      "git not detected: the gate's worktrees and out-of-scope checks are unavailable; everything else runs as usual."
    )
    expect(at(zhCN, 'settings.gitMissing')).toBe(
      '未检测到 git：闸门的作业树（worktree）与越界判断不可用，其余功能照常运行'
    )
  })

  it('guides the empty board toward registering a project', () => {
    expect(at(en, 'empty.hint')).toContain('register')
    expect(at(zhCN, 'empty.hint')).toContain('register')
  })
})

describe('card 45 message keys (the cap-reached note)', () => {
  it('adds the cap-reached note in both locales', () => {
    expect(at(en, 'board.capReached')).toBe('fetch limit reached')
    expect(at(zhCN, 'board.capReached')).toBe('已到取回上限')
  })

  it('leaves the existing capped warning and continue button wordings alone', () => {
    expect(at(en, 'board.capped')).toBe('only the most recent {n} — older rows are not fetched yet')
    expect(at(zhCN, 'board.capped')).toBe('仅取回最近 {n} 条 · 更早的还没取到')
    expect(at(en, 'board.continue')).toBe('Fetch earlier')
    expect(at(zhCN, 'board.continue')).toBe('继续取回')
  })
})

describe('card 54 message keys (the log tab)', () => {
  it('names the two drawer tabs in both locales', () => {
    expect(at(en, 'drawer.tab.overview')).toBe('Overview')
    expect(at(zhCN, 'drawer.tab.overview')).toBe('概览')
    expect(at(en, 'drawer.tab.log')).toBe('Log')
    expect(at(zhCN, 'drawer.tab.log')).toBe('日志')
  })

  it('pins every log-panel wording, in both locales', () => {
    expect(at(en, 'log.empty')).toBe('No output yet')
    expect(at(zhCN, 'log.empty')).toBe('暂无输出')
    expect(at(en, 'log.omitted')).toBe('{n} omitted before this point')
    expect(at(zhCN, 'log.omitted')).toBe('已省略前 {n}')
    expect(at(en, 'log.search.placeholder')).toBe('Search loaded content')
    expect(at(zhCN, 'log.search.placeholder')).toBe('搜索已加载内容')
    expect(at(en, 'log.search.scope')).toBe('Search scope: {n} loaded')
    expect(at(zhCN, 'log.search.scope')).toBe('搜索范围：已加载 {n}')
    expect(at(en, 'log.search.none')).toBe('No matches')
    expect(at(zhCN, 'log.search.none')).toBe('无匹配')
    expect(at(en, 'log.search.prev')).toBe('Previous match')
    expect(at(zhCN, 'log.search.prev')).toBe('上一个命中')
    expect(at(en, 'log.search.next')).toBe('Next match')
    expect(at(zhCN, 'log.search.next')).toBe('下一个命中')
    expect(at(en, 'log.jumpBottom')).toBe('Back to bottom ({n} new lines)')
    expect(at(zhCN, 'log.jumpBottom')).toBe('回到底部（{n} 行新）')
    expect(at(en, 'log.copy')).toBe('Copy')
    expect(at(zhCN, 'log.copy')).toBe('复制')
    expect(at(en, 'log.copied')).toBe('Copied')
    expect(at(zhCN, 'log.copied')).toBe('已复制')
    expect(at(en, 'log.refresh')).toBe('Refresh')
    expect(at(zhCN, 'log.refresh')).toBe('刷新')
    expect(at(en, 'log.truncated')).toBe('Only the last {n} lines are kept (earlier lines dropped)')
    expect(at(zhCN, 'log.truncated')).toBe('仅保留最后 {n} 行（更早的已丢弃）')
  })
})

/**
 * Card 59 made the desktop console read-only. Every write-surface key -- the
 * whole `task.*` control namespace, the project add / edit / remove labels and
 * their error copy, and the dialog Save button -- must be gone from BOTH
 * locales, while the handful of keys the read-only overview still renders stay.
 */
describe('card 59 message keys (read-only console)', () => {
  // Flat, dotted project keys (vue-i18n matches the whole string first), so they
  // are read straight off the object rather than by path traversal.
  const removedProj = [
    'proj.add',
    'proj.edit',
    'proj.remove',
    'proj.actions',
    'proj.register',
    'proj.detect',
    'proj.detect.run',
    'proj.detect.d',
    'proj.path',
    'proj.path.d',
    'proj.path.locked',
    'proj.id.locked',
    'proj.aliases',
    'proj.group',
    'proj.group.d',
    'proj.verify',
    'proj.verify.d',
    'proj.verify.none',
    'proj.verifykind',
    'proj.forbidden',
    'proj.forbidden.d',
    'proj.schema',
    'proj.schema.d',
    'proj.schema.default',
    'proj.schema.none',
    'proj.probe',
    'proj.add.hint',
    'proj.edit.hint',
    'proj.remove.q',
    'proj.remove.hint',
    'proj.conflict',
    'proj.reload',
    'proj.keep',
    'proj.writing',
    'proj.detecting',
    'proj.error.conflict',
    'proj.error.invalid',
    'proj.error.forbidden',
    'proj.error.notfound',
    'proj.error.network'
  ]

  it('drops the whole write surface from both locales', () => {
    for (const [name, messages] of Object.entries(locales)) {
      const m = messages as Record<string, unknown>
      // The dispatch / control namespace is gone outright.
      expect(at(m, 'task'), `${name}:task`).toBeUndefined()
      for (const key of removedProj) {
        expect(m[key], `${name}:${key}`).toBeUndefined()
      }
      // The dialog Save button went with the dialogs (Cancel stays for About).
      expect(at(m, 'dlg.save'), `${name}:dlg.save`).toBeUndefined()
    }
  })

  it('keeps the keys the read-only overview still renders', () => {
    for (const [name, messages] of Object.entries(locales)) {
      const m = messages as Record<string, unknown>
      expect(m['proj.group.default'], `${name}:proj.group.default`).toBeTruthy()
      expect(at(m, 'probe.passed'), `${name}:probe.passed`).toBeTruthy()
      expect(at(m, 'probe.failed'), `${name}:probe.failed`).toBeTruthy()
      expect(at(m, 'probe.none'), `${name}:probe.none`).toBeTruthy()
    }
  })
})
