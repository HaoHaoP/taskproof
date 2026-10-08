/**
 * The three project sheets must not gate their close on the renderer's frame
 * clock.
 *
 * `el-dialog` keeps its overlay mounted and only flips it to `display: none`
 * once the leave *transition* reports it is done. Vue's CSS transition hooks
 * resolve that off `requestAnimationFrame`, and Electron pauses that clock
 * while the window is occluded -- so a sheet the user has already closed can
 * leave its mask sitting over the table, which is exactly the "the write did
 * nothing" report. `SHEET_TRANSITION` carries `css: false`, which makes Vue
 * apply the hide in the same tick. These tests pin that decision, and pin the
 * fact that all three dialogs (and only an object with a `name`) use it, so a
 * later edit cannot quietly put the CSS transition back on one of them.
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { SHEET_TRANSITION } from './sheetTransition'

const view = readFileSync(new URL('../views/ProjectsView.vue', import.meta.url), 'utf-8')

/** The opening tags of the view's `<el-dialog>`s, in source order. */
const dialogs = view.match(/<el-dialog\b[^>]*>/g) ?? []

describe('SHEET_TRANSITION', () => {
  it('turns the CSS hooks off so a close never waits for a frame', () => {
    expect(SHEET_TRANSITION.css).toBe(false)
  })

  it('still names the transition, which el-dialog needs for its object syntax', () => {
    expect(SHEET_TRANSITION.name).toBe('dialog-fade')
  })
})

describe('ProjectsView sheets', () => {
  it('renders exactly the add / edit / remove dialogs', () => {
    expect(dialogs).toHaveLength(3)
  })

  it('hands the frame-independent transition to all three', () => {
    for (const tag of dialogs) {
      expect(tag).toContain(':transition="SHEET_TRANSITION"')
    }
  })

  it('keeps each sheet bound to its store flag, width and class', () => {
    expect(dialogs[0]).toContain('v-model="projects.addOpen"')
    expect(dialogs[0]).toContain('width="580"')
    expect(dialogs[0]).toContain('class="sheet"')
    expect(dialogs[1]).toContain('v-model="projects.editOpen"')
    expect(dialogs[1]).toContain('width="640"')
    expect(dialogs[1]).toContain('class="sheet"')
    expect(dialogs[2]).toContain('v-model="projects.removeOpen"')
    expect(dialogs[2]).toContain('width="500"')
    expect(dialogs[2]).toContain('class="sheet"')
  })
})
