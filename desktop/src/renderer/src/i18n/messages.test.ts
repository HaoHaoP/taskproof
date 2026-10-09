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
