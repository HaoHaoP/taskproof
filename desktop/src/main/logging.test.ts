/**
 * Renderer diagnostics, driven against a real temp directory.
 *
 * `logging.ts` is deliberately electron-free (only `fs`/`path`), so there is
 * nothing to mock: each case runs the real file IO in a throwaway directory and
 * asserts what actually landed on disk -- which is the whole point of a path
 * whose only job is to survive a renderer failure.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdtempSync, mkdirSync, readFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  appendBounded,
  formatRendererLine,
  shouldRecordConsoleLevel
} from './logging'

let dir = ''

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'tp-logging-'))
})

afterEach(() => {
  rmSync(dir, { recursive: true, force: true })
})

describe('formatRendererLine', () => {
  it('produces a single line and folds real newlines into a literal \\n', () => {
    const line = formatRendererLine('console', 'boom\r\nat foo (a.js:1)\nnext', new Date())
    expect(line).not.toContain('\n')
    expect(line).not.toContain('\r')
    expect(line.endsWith(' console boom\\nat foo (a.js:1)\\nnext')).toBe(true)
    // `<local ISO> <kind> <text>`, offset included.
    expect(line).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} console /)
  })

  it('truncates very long text and marks it', () => {
    const line = formatRendererLine('console', 'x'.repeat(5000), new Date())
    expect(line.endsWith('x…(truncated)')).toBe(true)
    // 4000 kept + the marker.
    expect(line.endsWith(''.padEnd(4000, 'x').slice(-10) + '…(truncated)')).toBe(true)
  })
})

describe('shouldRecordConsoleLevel', () => {
  it('records only error level, in either form', () => {
    expect(shouldRecordConsoleLevel(3)).toBe(true)
    expect(shouldRecordConsoleLevel('error')).toBe(true)
    expect(shouldRecordConsoleLevel(2)).toBe(false)
    expect(shouldRecordConsoleLevel('warn')).toBe(false)
  })
})

describe('appendBounded', () => {
  it('appends records, one per line', () => {
    const file = join(dir, 'renderer-errors.log')
    expect(appendBounded(file, 'first')).toBe(true)
    expect(appendBounded(file, 'second')).toBe(true)
    expect(readFileSync(file, 'utf8')).toBe('first\nsecond\n')
  })

  it('keeps only whole trailing records once the file would exceed the limit', () => {
    const file = join(dir, 'bounded.log')
    // limit 10 bytes fits two 4-byte records ("aaaa\n" x2 = 10), not three.
    for (let i = 0; i < 3; i++) appendBounded(file, 'aaaa', 10)
    const content = readFileSync(file, 'utf8')
    // Head dropped at a line boundary; the tail is complete and <= limit.
    expect(content).toBe('aaaa\naaaa\n')
    expect(Buffer.byteLength(content, 'utf8')).toBeLessThanOrEqual(10)
    expect(content.startsWith('aaa')).toBe(true)
    expect(content.endsWith('aaaa\n')).toBe(true)
  })

  it('creates a missing parent directory', () => {
    const file = join(dir, 'nested', 'deeper', 'out.log')
    expect(appendBounded(file, 'hello')).toBe(true)
    expect(readFileSync(file, 'utf8')).toBe('hello\n')
  })

  it('returns false instead of throwing when the target is unwritable', () => {
    // A directory where the file should be: the write fails, and that failure
    // must be swallowed, not thrown at the caller.
    const asDir = join(dir, 'not-a-file')
    mkdirSync(asDir)
    expect(appendBounded(asDir, 'nope')).toBe(false)
  })
})
