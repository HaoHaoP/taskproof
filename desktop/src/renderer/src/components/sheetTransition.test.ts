/**
 * `SHEET_TRANSITION` exists so a sheet's close never gates on the renderer's
 * frame clock.
 *
 * `el-dialog` keeps its overlay mounted and only flips it to `display: none`
 * once the leave *transition* reports it is done. Vue's CSS transition hooks
 * resolve that off `requestAnimationFrame`, and Electron pauses that clock
 * while the window is occluded -- so a sheet the user has already closed can
 * leave its mask sitting over the page. `SHEET_TRANSITION` carries `css: false`,
 * which makes Vue apply the hide in the same tick. These tests pin that decision
 * (it is still used by the About sheet).
 */
import { describe, expect, it } from 'vitest'
import { SHEET_TRANSITION } from './sheetTransition'

describe('SHEET_TRANSITION', () => {
  it('turns the CSS hooks off so a close never waits for a frame', () => {
    expect(SHEET_TRANSITION.css).toBe(false)
  })

  it('still names the transition, which el-dialog needs for its object syntax', () => {
    expect(SHEET_TRANSITION.name).toBe('dialog-fade')
  })
})
