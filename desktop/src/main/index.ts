import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { join } from 'path'
import * as settings from './settings'
import { ApiService, type LaunchSpec } from './service'
import { createProjectsClient, type ProjectsClient } from './projects'
import type {
  DesktopSettings,
  ProjectCreatePayload,
  ProjectPatch
} from '../preload/types'

let mainWindow: BrowserWindow | null = null

function launchSpec(): LaunchSpec {
  const current = settings.get()
  // The path may be a bare executable or a command with arguments
  // ("python3 -m taskproof"), so split it rather than handing spawn a string
  // it would look up as a single file name.
  const parts = (current.taskproofPath || 'taskproof').trim().split(/\s+/)
  return {
    command: parts[0],
    // The global flag precedes the subcommand; `--allow-write` belongs to `api`
    // and opens the token-protected write surface.
    args: [...parts.slice(1), '--workspace', current.workspace, 'api', '--allow-write', '--port', '0'],
    workspace: current.workspace
  }
}

const api = new ApiService(launchSpec)

/**
 * The write client, rebuilt whenever the service comes up on a new port or a
 * new token. Everything that talks HTTP-with-a-token goes through here; the
 * renderer only ever sees the named IPC methods below.
 */
let writeClient: ProjectsClient | null = null
let writeKey = ''

function projects(): ProjectsClient {
  const port = api.getStatus().port
  const token = api.getToken() ?? ''
  const key = `${port}:${token}`
  if (!writeClient || writeKey !== key) {
    writeClient = createProjectsClient({
      baseUrl: port ? `http://127.0.0.1:${port}` : '',
      token
    })
    writeKey = key
  }
  return writeClient
}

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

  // Registry writes. Each answers with a typed result; the token and the
  // expected_hash handshake stay in this process.
  ipcMain.handle('tp:projects:registry', () => projects().registry())
  ipcMain.handle('tp:projects:probe', (_event, path: string) => projects().probe(String(path)))
  ipcMain.handle('tp:projects:create', (_event, payload: ProjectCreatePayload) =>
    projects().create(payload)
  )
  ipcMain.handle('tp:projects:patch', (_event, id: string, patch: ProjectPatch) =>
    projects().patch(String(id), patch)
  )
  ipcMain.handle('tp:projects:remove', (_event, id: string) => projects().remove(String(id)))
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
