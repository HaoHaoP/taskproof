import { resolve } from 'path'
import { defineConfig } from 'vitest/config'

/**
 * Pure-logic tests only. Layout is verified against a real window; what is
 * worth testing here is the reasoning the UI depends on -- the status/column
 * mapping, the never-hide rule, locale fallback, formatting.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@renderer': resolve(__dirname, 'src/renderer/src'),
      '@contract': resolve(__dirname, '../contract')
    }
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts']
  }
})
