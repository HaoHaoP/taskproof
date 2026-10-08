/**
 * The entire main-process surface the renderer is allowed to touch.
 *
 * Named methods, not a generic `invoke(channel, payload)`: the renderer loads
 * the built bundle and renders agent-produced text, so handing it the whole IPC
 * surface would make any injection a full compromise. Registry writes are not
 * here on purpose -- they go through the main process later, so the local write
 * token never reaches this side of the boundary.
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
    openPath: (target: string) => ipcRenderer.invoke('tp:shell:open-path', target)
  },
  app: {
    version: () => ipcRenderer.invoke('tp:app:version')
  }
}

if (process.contextIsolated) {
  contextBridge.exposeInMainWorld('tp', api)
} else {
  ;(window as unknown as { tp: TpApi }).tp = api
}
