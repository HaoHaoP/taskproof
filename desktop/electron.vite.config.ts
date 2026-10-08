import { resolve } from 'path'
import { defineConfig } from 'electron-vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'

export default defineConfig({
  main: {},
  preload: {},
  renderer: {
    resolve: {
      alias: {
        '@renderer': resolve('src/renderer/src'),
        // The enum contract is generated from the Python constants and lives at
        // the repository root, outside this package, so both languages read the
        // same artefact.
        '@contract': resolve('../contract')
      }
    },
    server: {
      // ...which means the dev server has to be allowed to read one level up.
      fs: { allow: [resolve('..')] }
    },
    plugins: [vue(), UnoCSS()]
  }
})
