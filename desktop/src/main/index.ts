import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { mkdirSync } from 'fs'
import { join } from 'path'
import * as settings from './settings'
import { ApiService, type LaunchSpec } from './service'
import { runDoctor } from './doctor'
import { createProjectsClient, type ProjectsClient } from './projects'
import type {
  DesktopSettings,
  ProjectCreatePayload,
  ProjectPatch
} from '../preload/types'

// The app's display name is now "Taskproof", but Electron derives `userData`
// from the package name -- so a rename (or a bumped productName) would silently
// move the directory and orphan the user's settings.json. Pin it to the
// historical `.../Application Support/taskproof-desktop` path, before anything
// reads it, so upgrades keep the same file.
const userDataDir = join(app.getPath('appData'), 'taskproof-desktop')
mkdirSync(userDataDir, { recursive: true })
app.setPath('userData', userDataDir)

let mainWindow: BrowserWindow | null = null

/** The taskproof command, split into an executable and its leading arguments
 *  ("python3 -m taskproof" must not be treated as one file name). */
function commandParts(): string[] {
  return (settings.get().taskproofPath || 'taskproof').trim().split(/\s+/)
}

function launchSpec(): LaunchSpec {
  const current = settings.get()
  const parts = commandParts()
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
  // The About group's adapter lamps. The API has no adapter endpoint, so this
  // is the CLI's own self-check; it resolves null when it cannot answer.
  ipcMain.handle('tp:app:adapters', () => {
    const parts = commandParts()
    return runDoctor({
      command: parts[0],
      prefixArgs: parts.slice(1),
      workspace: settings.get().workspace
    })
  })

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
