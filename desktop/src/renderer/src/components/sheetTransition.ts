import type { TransitionProps } from 'vue'

/**
 * How the three project sheets (add / edit / remove) open and close.
 *
 * `el-dialog` never unmounts its overlay: the template renders
 * `<Transition>` around `<ElOverlay v-show="visible">`, so Vue only flips the
 * overlay to `display: none` once the *leave* transition reports that it is
 * done. Element Plus' default `dialog-fade` is a CSS animation, and Vue drives
 * that off the renderer's frame clock -- a `requestAnimationFrame` pair has to
 * fire before the leave even starts, and an `animationend` (or a timer) has to
 * fire before `v-show` is finally applied. Electron pauses that clock whenever
 * the window is occluded (`backgroundThrottling` defaults on), so a sheet the
 * user has already closed can keep its mask on screen, covering the table --
 * the write landed and the list re-read, but the page looks as if nothing
 * happened. Only the app's window being on top again unblocks the teardown.
 *
 * A transition with `css: false` carries no enter/leave CSS hooks at all, so
 * Vue applies the `v-show` flip in the same tick the model changes: the sheet
 * appears and disappears on the click, whatever the compositor is doing. The
 * `name` is kept only because Element Plus warns when an object-shaped
 * transition omits it.
 */
export const SHEET_TRANSITION: TransitionProps = { name: 'dialog-fade', css: false }
