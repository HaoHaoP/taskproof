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

  it('names the acceptance-passed badge and the accept action everywhere', () => {
    expect(at(en, 'card.acceptancePassed')).toBeTruthy()
    expect(at(zhCN, 'card.acceptancePassed')).toBeTruthy()
    expect(at(en, 'task.accept')).toBeTruthy()
    expect(at(zhCN, 'task.accept')).toBeTruthy()
    expect(at(en, 'task.confirmAccept.title')).toBeTruthy()
    expect(at(zhCN, 'task.confirmAccept.title')).toBeTruthy()
    // The stale-copy a 409 (no longer blocked) shows.
    expect(at(en, 'task.notice.stale')).toBeTruthy()
    expect(at(zhCN, 'task.notice.stale')).toBeTruthy()
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
