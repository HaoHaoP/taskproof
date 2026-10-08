import { defineConfig, presetWind3 } from 'unocss'

export default defineConfig({
  // Layout utilities only. The status colour system lives in tokens.css keyed on
  // [data-status] -- it must not depend on which utility classes a template
  // happens to use, or the 24 call sites would drift apart again.
  presets: [presetWind3()],
  theme: {}
})
