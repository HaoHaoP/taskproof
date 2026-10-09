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
