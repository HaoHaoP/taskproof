import type { TpApi } from './types'

declare global {
  interface Window {
    /** Absent when the renderer is opened in a plain browser (dev fallback). */
    tp?: TpApi
  }
}

export {}
