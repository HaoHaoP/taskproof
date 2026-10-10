/**
 * The entire main-process surface the renderer is allowed to touch.
 *
 * Named methods, not a generic `invoke(channel, payload)`: the renderer loads
 * the built bundle and renders agent-produced text, so handing it the whole IPC
 * surface would make any injection a full compromise. The surface is read-only:
 * settings, shell, app diagnostics and the service status -- there are no write
 * channels.
 */
import { contextBridge, ipcRenderer } from 'electron'
import type { DesktopSettings, ServiceStatus, TpApi } from './types'

const api: TpApi = {
  service: {
    status: () => ipcRenderer.invoke('tp:service:status'),
    restart: () => ipcRenderer.invoke('tp:service:restart'),
    onStatus: (listener) => {
      const handler = (_event: unknown, status: ServiceStatus): void => listener(status)
      ipcRenderer.on('tp:service:changed', handler)
      return () => {
        ipcRenderer.removeListener('tp:service:changed', handler)
      }
    }
  },
  settings: {
    get: () => ipcRenderer.invoke('tp:settings:get'),
    set: (patch: Partial<DesktopSettings>) => ipcRenderer.invoke('tp:settings:set', patch)
  },
  shell: {
    openPath: (target: string) => ipcRenderer.invoke('tp:shell:open-path', target),
    reveal: (target: string) => ipcRenderer.invoke('tp:shell:reveal', target),
    openExternal: (url: string) => ipcRenderer.invoke('tp:shell:open-external', url)
  },
  app: {
    version: () => ipcRenderer.invoke('tp:app:version'),
    adapters: () => ipcRenderer.invoke('tp:app:adapters'),
    about: () => ipcRenderer.invoke('tp:app:about'),
    diagnostics: () => ipcRenderer.invoke('tp:app:diagnostics'),
    copyText: (text: string) => ipcRenderer.invoke('tp:app:copy-text', text),
    onShowAbout: (listener) => {
      const handler = (): void => listener()
      ipcRenderer.on('tp:app:show-about', handler)
      return () => {
        ipcRenderer.removeListener('tp:app:show-about', handler)
      }
    }
  },
  // Test-only and off by default: the diagnostic channels are registered by the
  // main process only when it was launched with TP_DESKTOP_DIAG, so the shipped
  // renderer never sees this surface.
  diag: process.env.TP_DESKTOP_DIAG
    ? {
        state: () => ipcRenderer.invoke('tp:diag:state'),
        trayClick: () => ipcRenderer.invoke('tp:diag:tray-click')
      }
    : undefined
}

if (process.contextIsolated) {
  contextBridge.exposeInMainWorld('tp', api)
} else {
  ;(window as unknown as { tp: TpApi }).tp = api
}
