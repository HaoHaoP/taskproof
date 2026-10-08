import { describe, expect, it } from 'vitest'
import { resolveLocale } from './locale'

describe('locale resolution', () => {
  it('follows the system locale', () => {
    expect(resolveLocale('system', 'zh-CN')).toBe('zh-CN')
    expect(resolveLocale('system', 'zh-Hans-CN')).toBe('zh-CN')
    expect(resolveLocale('system', 'en-GB')).toBe('en')
  })

  it('falls back to en, never to an empty locale', () => {
    for (const system of ['de-DE', 'ja-JP', 'fr', '', 'xx']) {
      expect(resolveLocale('system', system)).toBe('en')
    }
  })

  it('lets an explicit choice win over the system', () => {
    expect(resolveLocale('zh-CN', 'en-US')).toBe('zh-CN')
    expect(resolveLocale('en', 'zh-CN')).toBe('en')
  })
})
