/**
 * Owns the local API process.
 *
 * The app spawns `taskproof api --allow-write --port 0` and learns two things
 * from the child's stdout:
 *
 *   taskproof api listening on http://127.0.0.1:<port>
 *   taskproof api token <token>
 *
 * The first gives the port; the second is the session write token, which stays
 * in this process. Both lines share one pipe, so they are read off the same
 * stream. The child is killed on quit -- a desktop app must not leave stray
 * servers behind on the user's machine.
 */
import { spawn, type ChildProcess } from 'child_process'
import type { ServiceStatus } from '../preload/types'

const LISTENING = /listening on http:\/\/[\d.]+:(\d+)/
/** The token line is `taskproof api token <token>`; the token itself has no spaces. */
const TOKEN = /taskproof api token (\S+)/
const START_TIMEOUT_MS = 10_000

export interface LaunchSpec {
  command: string
  args: string[]
  workspace: string
}

type Listener = (status: ServiceStatus) => void

/** Resolves with the bound port, or rejects if the server never reports one. */
function readPort(child: ChildProcess, timeoutMs = START_TIMEOUT_MS): Promise<number> {
  return new Promise((resolve, reject) => {
    let buffer = ''
    const timer = setTimeout(() => {
      reject(new Error(`no port reported within ${timeoutMs}ms`))
    }, timeoutMs)

    const settle = (fn: () => void): void => {
      clearTimeout(timer)
      child.stdout?.off('data', onData)
      child.off('exit', onExit)
      child.off('error', onError)
      fn()
    }

    const onData = (chunk: string): void => {
      buffer += chunk
      const match = buffer.match(LISTENING)
      if (match) settle(() => resolve(Number(match[1])))
    }
    const onExit = (code: number | null): void => {
      settle(() => reject(new Error(`the local service exited with code ${code}`)))
    }
    const onError = (error: Error): void => {
      settle(() => reject(error))
    }

    child.stdout?.setEncoding('utf8')
    child.stdout?.on('data', onData)
    child.once('exit', onExit)
    child.once('error', onError)
  })
}

export class ApiService {
  private child: ChildProcess | null = null
  private token: string | null = null
  private status: ServiceStatus = { state: 'stopped', port: null, workspace: '', detail: '' }
  private readonly listeners = new Set<Listener>()
  private stderrTail = ''

  constructor(private readonly launch: () => LaunchSpec) {}

  getStatus(): ServiceStatus {
    return this.status
  }

  /**
   * The session write token, or null before the child has printed it. Kept
   * here on purpose: the renderer never sees this value.
   */
  getToken(): string | null {
    return this.token
  }

  onStatus(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private emit(next: Partial<ServiceStatus>): void {
    this.status = { ...this.status, ...next }
    for (const listener of this.listeners) listener(this.status)
  }

  async start(): Promise<ServiceStatus> {
    this.stop()
    const spec = this.launch()
    this.stderrTail = ''
    this.token = null
    this.emit({ state: 'starting', port: null, workspace: spec.workspace, detail: '' })

    let child: ChildProcess
    try {
      child = spawn(spec.command, spec.args, { stdio: ['ignore', 'pipe', 'pipe'] })
    } catch (error) {
      this.emit({ state: 'failed', detail: String(error) })
      return this.status
    }
    this.child = child

    // The token line shares the port line's stream and arrives right after it.
    // Keep a listener attached so it is captured whenever it shows up, without
    // coupling the port handshake to it. The buffer guards against the line
    // being split across two `data` chunks.
    let tokenBuffer = ''
    child.stdout?.setEncoding('utf8')
    child.stdout?.on('data', (chunk: string) => {
      tokenBuffer = (tokenBuffer + chunk).slice(-200)
      const match = tokenBuffer.match(TOKEN)
      if (match) this.token = match[1]
    })

    child.stderr?.setEncoding('utf8')
    child.stderr?.on('data', (chunk: string) => {
      // Keep only the tail: enough to explain a failure, not a log store.
      this.stderrTail = (this.stderrTail + chunk).slice(-400)
    })

    try {
      const port = await readPort(child)
      this.emit({ state: 'ready', port, detail: `pid ${child.pid ?? '?'}` })
    } catch (error) {
      const detail = String((error as Error).message ?? error)
      this.emit({ state: 'failed', port: null, detail: this.stderrTail || detail })
      if (this.child === child) {
        child.kill()
        this.child = null
      }
      return this.status
    }

    child.once('exit', (code, signal) => {
      if (this.child !== child) return // replaced on purpose; ignore this one
      this.child = null
      this.token = null
      this.emit({
        state: code === 0 ? 'stopped' : 'failed',
        port: null,
        detail: `exited ${code ?? signal ?? '?'}${this.stderrTail ? `: ${this.stderrTail}` : ''}`
      })
    })

    return this.status
  }

  stop(): void {
    const child = this.child
    this.child = null
    this.token = null
    if (!child || child.killed) return
    child.kill()
    this.emit({ state: 'stopped', port: null, detail: '' })
  }
}
