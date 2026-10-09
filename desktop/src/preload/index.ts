/**
 * The entire main-process surface the renderer is allowed to touch.
 *
 * Named methods, not a generic `invoke(channel, payload)`: the renderer loads
 * the built bundle and renders agent-produced text, so handing it the whole IPC
 * surface would make any injection a full compromise. Registry writes are named
 * too, and the write token never crosses this boundary -- the main process
 * attaches it to the HTTP request itself.
 */
import { contextBridge, ipcRenderer } from 'electron'
import type {
  DesktopSettings,
  ProjectCreatePayload,
  ProjectPatch,
  ServiceStatus,
  TaskCreatePayload,
  TpApi
} from './types'

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
    : undefined,
  projects: {
    registry: () => ipcRenderer.invoke('tp:projects:registry'),
    probe: (path: string) => ipcRenderer.invoke('tp:projects:probe', path),
    create: (payload: ProjectCreatePayload) => ipcRenderer.invoke('tp:projects:create', payload),
    patch: (id: string, patch: ProjectPatch) => ipcRenderer.invoke('tp:projects:patch', id, patch),
    remove: (id: string) => ipcRenderer.invoke('tp:projects:remove', id)
  },
  tasks: {
    create: (payload: TaskCreatePayload) => ipcRenderer.invoke('tp:tasks:create', payload),
    advance: (id: string) => ipcRenderer.invoke('tp:tasks:advance', id),
    cancel: (id: string) => ipcRenderer.invoke('tp:tasks:cancel', id),
    remove: (id: string) => ipcRenderer.invoke('tp:tasks:remove', id),
    patchQueueSeq: (id: string, queueSeq: number | null) =>
      ipcRenderer.invoke('tp:tasks:patch-queue-seq', id, queueSeq)
  }
}

if (process.contextIsolated) {
  contextBridge.exposeInMainWorld('tp', api)
} else {
  ;(window as unknown as { tp: TpApi }).tp = api
}
