import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { join } from 'path'
import * as settings from './settings'
import { ApiService, type LaunchSpec } from './service'
import type { DesktopSettings } from '../preload/types'

let mainWindow: BrowserWindow | null = null

function launchSpec(): LaunchSpec {
  const current = settings.get()
  // The path may be a bare executable or a command with arguments
  // ("python3 -m taskproof"), so split it rather than handing spawn a string
  // it would look up as a single file name.
  const parts = (current.taskproofPath || 'taskproof').trim().split(/\s+/)
  return {
    command: parts[0],
    // The global flag precedes the subcommand.
    args: [...parts.slice(1), '--workspace', current.workspace, 'api', '--port', '0'],
    workspace: current.workspace
  }
}

const api = new ApiService(launchSpec)

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 700,
    show: false,
    autoHideMenuBar: true,
    // Keep the OS traffic lights and inset them over our own mast, which
    // reserves 78px on the left for them. The prototype's three dots are a
    // browser mockup, so they are deliberately not ported.
    titleBarStyle: 'hiddenInset',
    // Matches the dark canvas, so there is no white flash before the renderer
    // paints.
    backgroundColor: '#1c1c1e',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow?.show())

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Never open a second Electron window for a link; hand it to the OS.
    void shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function registerIpc(): void {
  ipcMain.handle('tp:service:status', () => api.getStatus())
  ipcMain.handle('tp:service:restart', () => api.start())
  ipcMain.handle('tp:settings:get', () => settings.get())
  ipcMain.handle('tp:settings:set', (_event, patch: Partial<DesktopSettings>) => settings.set(patch))
  ipcMain.handle('tp:shell:open-path', async (_event, target: string) => {
    await shell.openPath(String(target))
  })
  ipcMain.handle('tp:app:version', () => app.getVersion())
}

api.onStatus((status) => {
  mainWindow?.webContents.send('tp:service:changed', status)
})

app.whenReady().then(async () => {
  app.setAppUserModelId('com.taskproof.desktop')
  registerIpc()
  createWindow()
  await api.start()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// The child server must not outlive the app, however the app ends.
app.on('before-quit', () => api.stop())
process.on('exit', () => api.stop())
