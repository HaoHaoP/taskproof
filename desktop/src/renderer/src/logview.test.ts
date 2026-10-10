/**
 * The log panel's pure reasoning. The SFC only arranges these results onto the
 * screen, so pinning them here covers the parts a real window would be slow and
 * flaky to check: ANSI stripping (including an unterminated sequence), the
 * case-insensitive local search, the highlight segmentation, the
 * "is the reader at the bottom" threshold, and the byte/line helpers the
 * notices are worded from.
 */
import { describe, expect, it } from 'vitest'
import {
  capToLastLines,
  countMatches,
  formatBytes,
  highlightSegments,
  matchLineIndexes,
  shouldStickBottom,
  stripAnsi
} from './logview'

describe('stripAnsi', () => {
  it('removes an SGR colour pair', () => {
    expect(stripAnsi('\x1b[31mred\x1b[0m')).toBe('red')
  })

  it('removes an unterminated sequence (a colour with no reset)', () => {
    expect(stripAnsi('\x1b[31mred')).toBe('red')
    // A sequence cut off before its final byte is still consumed.
    expect(stripAnsi('a\x1b[31')).toBe('a')
  })

  it('leaves plain text untouched', () => {
    expect(stripAnsi('no escapes here')).toBe('no escapes here')
  })

  it('drops an OSC title too', () => {
    expect(stripAnsi('\x1b]0;title\x07body')).toBe('body')
  })
})

describe('countMatches (case-insensitive, non-overlapping)', () => {
  it('counts regardless of case', () => {
    expect(countMatches('abABab', 'ab')).toBe(3)
  })

  it('counts CJK occurrences', () => {
    expect(countMatches('错误错误', '错误')).toBe(2)
  })

  it('does not overlap occurrences -- the browser find-in-page rule', () => {
    expect(countMatches('aaa', 'aa')).toBe(1)
  })

  it('treats an empty query as no match', () => {
    expect(countMatches('anything', '')).toBe(0)
  })
})

describe('matchLineIndexes', () => {
  it('reports the 0-based line of each hit, one per occurrence', () => {
    expect(matchLineIndexes('aa\na', 'a')).toEqual([0, 0, 1])
  })

  it('is empty for a blank query', () => {
    expect(matchLineIndexes('aa\na', '')).toEqual([])
  })
})

describe('highlightSegments', () => {
  it('splits a line into non-hit / hit / non-hit, preserving case', () => {
    expect(highlightSegments('foo BAR baz', 'bar')).toEqual([
      { text: 'foo ', hit: false },
      { text: 'BAR', hit: true },
      { text: ' baz', hit: false }
    ])
  })

  it('returns the whole line unhit when nothing matches', () => {
    expect(highlightSegments('nothing here', 'zzz')).toEqual([{ text: 'nothing here', hit: false }])
  })

  it('returns one unhit segment for an empty query', () => {
    expect(highlightSegments('nothing here', '')).toEqual([{ text: 'nothing here', hit: false }])
  })
})

describe('shouldStickBottom', () => {
  it('is false when the reader is far from the bottom', () => {
    expect(shouldStickBottom(0, 1000, 800)).toBe(false)
  })

  it('counts a position exactly at the threshold as sticking (inclusive)', () => {
    expect(shouldStickBottom(176, 1000, 800)).toBe(true)
  })

  it('is false one pixel past the threshold', () => {
    expect(shouldStickBottom(175, 1000, 800)).toBe(false)
  })

  it('is true when over-scrolled past the end', () => {
    expect(shouldStickBottom(250, 1000, 800)).toBe(true)
  })
})

describe('formatBytes', () => {
  it('stays in bytes below a kilobyte', () => {
    expect(formatBytes(512)).toBe('512 B')
  })

  it('uses binary units with one decimal, dropping a trailing .0', () => {
    expect(formatBytes(1024)).toBe('1 KB')
    expect(formatBytes(1536)).toBe('1.5 KB')
  })

  it('never prints a negative or non-finite count', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(-4)).toBe('0 B')
    expect(formatBytes(Number.NaN)).toBe('0 B')
  })
})

describe('capToLastLines', () => {
  it('keeps the tail and reports the trim', () => {
    expect(capToLastLines('a\nb\nc\nd', 2)).toEqual({ text: 'c\nd', truncated: true })
  })

  it('is a no-op while the text is within the cap', () => {
    expect(capToLastLines('a\nb', 5)).toEqual({ text: 'a\nb', truncated: false })
  })
})
