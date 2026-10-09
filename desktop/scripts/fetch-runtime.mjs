#!/usr/bin/env node
/**
 * Assemble a self-contained, relocatable Python runtime next to our source so
 * the packaged app can start `python -m taskproof` with nothing installed on
 * the user's machine.
 *
 * The Python package is pure-stdlib, so we do not need pip or a virtualenv:
 * one working `python3` plus a copy of `src/taskproof` is enough. We therefore
 * download a pinned python-build-standalone build, verify it against a hard
 * coded sha256, prune everything we do not need, and prove the pruned tree can
 * still import the stdlib modules taskproof depends on and run the package.
 *
 * Everything is pinned on purpose — no `latest`, no version discovery — so two
 * machines building the same tag produce the same runtime.
 *
 *   node scripts/fetch-runtime.mjs --target mac-arm64
 *   node scripts/fetch-runtime.mjs            # host platform/arch
 *
 * Downloads go through the system `curl`, which honours the usual
 * https_proxy / HTTPS_PROXY environment variables and works without a proxy
 * too. Extraction uses the system `tar`. The script fails loudly on any
 * checksum mismatch or failing verification — it never silently ships an
 * installer without a working Python.
 */
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import {
  cpSync,
  createReadStream,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync
} from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = fileURLToPath(new URL('.', import.meta.url))
const desktopDir = resolve(here, '..')
const repoRoot = resolve(desktopDir, '..')
const buildDir = join(desktopDir, 'build')
const cacheDir = join(buildDir, 'cache')
const runtimeRoot = join(buildDir, 'runtime')
const srcPythonDir = join(repoRoot, 'src', 'taskproof')

const RELEASE = '20261003'
const VERSION = 'cpython-3.13.16+20261003'
const VARIANT = 'install_only_stripped'
const BASE_URL = `https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE}`

/**
 * The only four rows we ever download. `sizeMb` is the published size, kept
 * for the human-readable log; the sha256 is the contract and is enforced.
 */
const TARGETS = {
  'mac-arm64': {
    file: `${VERSION}-aarch64-apple-darwin-${VARIANT}.tar.gz`,
    sizeMb: 24.1,
    sha256: '9e01f63bbb08576cd9c8bc2d0564d098cb30c8453a0cd4bcf6aef458f6d2a147',
    python: ['bin', 'python3']
  },
  'mac-x64': {
    file: `${VERSION}-x86_64-apple-darwin-${VARIANT}.tar.gz`,
    sizeMb: 23.8,
    sha256: 'b4dad38ba6a344555ccb71a1b08caad0a6c0dda88c5803658bc95bd7f04e9f5c',
    python: ['bin', 'python3']
  },
  'win-x64': {
    file: `${VERSION}-x86_64-pc-windows-msvc-${VARIANT}.tar.gz`,
    sizeMb: 21.0,
    sha256: 'ec43f1a85c29f147d7ae2d13218c52c70b24a983a82ab22d6c607c0593060e10',
    python: ['python.exe']
  },
  'linux-x64': {
    file: `${VERSION}-x86_64-unknown-linux-gnu-${VARIANT}.tar.gz`,
    sizeMb: 33.5,
    sha256: '4595c5589fff7bf0cb158d9a88a797e0d791fa33830770fcb7bf3f4b104feeae',
    python: ['bin', 'python3']
  }
}

/** Prune targets, applied as a single recursive sweep of the staged tree. */
const PRUNE_DIR_NAMES = new Set(['tkinter', 'idlelib', 'ensurepip', 'pip', 'test', '__pycache__'])
const STAGING_PREFIX = '.runtime-staging-'

/** A failure we raise on purpose: printed without a stack, exit code 1. */
class FetchRuntimeError extends Error {
  constructor(message) {
    super(message)
    this.name = 'FetchRuntimeError'
  }
}

function fail(message) {
  throw new FetchRuntimeError(message)
}

function log(message) {
  console.log(`fetch-runtime: ${message}`)
}

function parseArgs(argv) {
  let target = null
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--target') {
      target = argv[i + 1]
      i += 1
    } else if (arg.startsWith('--target=')) {
      target = arg.slice('--target='.length)
    } else if (arg === '--help' || arg === '-h') {
      console.log(`usage: node scripts/fetch-runtime.mjs [--target <${Object.keys(TARGETS).join('|')}>]`)
      process.exit(0)
    } else {
      fail(`unknown argument: ${arg}`)
    }
  }
  return target
}

function defaultTarget() {
  const { platform, arch } = process
  if (platform === 'darwin') return arch === 'arm64' ? 'mac-arm64' : 'mac-x64'
  if (platform === 'win32') return 'win-x64'
  if (platform === 'linux') return 'linux-x64'
  return null
}

/** Run a child process to completion, throwing loudly on any failure. */
function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', ...options })
  if (result.error) fail(`failed to run \`${command}\`: ${result.error.message}`)
  if (result.status !== 0) fail(`\`${command} ${args.join(' ')}\` exited with ${result.status}`)
}

/** Recursively size a directory tree in bytes. */
function diskUsage(dir) {
  let total = 0
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) total += diskUsage(full)
    else if (entry.isFile()) total += statSync(full).size
  }
  return total
}

function formatBytes(bytes) {
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(1)} MB (${bytes} bytes)`
}

function sha256(file) {
  return new Promise((resolvePromise, rejectPromise) => {
    const hash = createHash('sha256')
    createReadStream(file)
      .on('error', rejectPromise)
      .on('data', (chunk) => hash.update(chunk))
      .on('end', () => resolvePromise(hash.digest('hex')))
  })
}

/** Download with `curl -fL`; curl handles proxies, redirects and retries. */
function download(url, dest) {
  log(`downloading ${url}`)
  run('curl', ['-fL', '--retry', '3', '--retry-delay', '2', '--retry-connrefused', '-o', dest, url])
}

/** Remove any staging directory a previous crashed run may have left behind. */
function sweepStaleStaging() {
  if (!existsSync(buildDir)) return
  for (const entry of readdirSync(buildDir, { withFileTypes: true })) {
    if (entry.isDirectory() && entry.name.startsWith(STAGING_PREFIX)) {
      rmSync(join(buildDir, entry.name), { recursive: true, force: true })
    }
  }
}

/**
 * Delete the fat we do not ship. Only directories/files that are never needed
 * to import sqlite3/tomllib/ssl/urllib or run taskproof are touched, so the
 * post-prune self-check below has real teeth.
 */
function prune(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (PRUNE_DIR_NAMES.has(entry.name) || entry.name.startsWith('config-')) {
        rmSync(full, { recursive: true, force: true })
        continue
      }
      if (entry.name === 'site-packages') {
        for (const child of readdirSync(full)) {
          if (child === 'pip' || child.startsWith('pip-')) {
            rmSync(join(full, child), { recursive: true, force: true })
          }
        }
      }
      prune(full)
    } else if (entry.name.endsWith('.a') || entry.name.endsWith('.pdb')) {
      rmSync(full, { force: true })
    }
  }
}

async function main() {
  const requested = parseArgs(process.argv.slice(2))
  const inferred = defaultTarget()
  const target = requested || inferred
  if (!target) fail(`cannot infer a target from ${process.platform}/${process.arch}; pass --target explicitly`)
  const spec = TARGETS[target]
  if (!spec) fail(`unknown target "${target}"; expected one of ${Object.keys(TARGETS).join(', ')}`)

  const url = `${BASE_URL}/${spec.file}`
  const archive = join(cacheDir, spec.file)

  mkdirSync(cacheDir, { recursive: true })
  sweepStaleStaging()

  // Download only when we do not already have a cached archive.
  if (existsSync(archive)) {
    log(`using cached ${archive}`)
  } else {
    download(url, archive)
  }

  const size = statSync(archive).size
  log(`downloaded ${spec.file} (${formatBytes(size)}; published ${spec.sizeMb} MB)`)

  const actual = await sha256(archive)
  if (actual !== spec.sha256) {
    fail(`sha256 mismatch for ${spec.file}\n  expected ${spec.sha256}\n  actual   ${actual}`)
  }
  log(`sha256 OK: ${actual}`)

  // Extract into a sibling of the final location so the move is an atomic
  // rename on the same filesystem.
  mkdirSync(runtimeRoot, { recursive: true })
  const staging = mkdtempSync(join(buildDir, STAGING_PREFIX))
  let moved = false
  try {
    log(`extracting into ${staging}`)
    run('tar', ['-xzf', archive, '-C', staging])

    const stagedPythonRoot = join(staging, 'python')
    if (!existsSync(stagedPythonRoot)) {
      fail(`archive did not contain a top-level python/ directory (looked in ${staging})`)
    }

    const before = diskUsage(stagedPythonRoot)
    prune(stagedPythonRoot)
    const after = diskUsage(stagedPythonRoot)
    log(`runtime size: before ${formatBytes(before)}, after ${formatBytes(after)} (saved ${formatBytes(before - after)})`)

    // Copy our source next to the interpreter so the staged tree is
    // self-contained; electron-builder maps ../src separately as well.
    if (!existsSync(srcPythonDir)) fail(`missing source package: ${srcPythonDir}`)
    cpSync(srcPythonDir, join(staging, 'src', 'taskproof'), { recursive: true })

    const pythonExe = join(stagedPythonRoot, ...spec.python)
    if (!existsSync(pythonExe)) fail(`expected interpreter at ${pythonExe}`)

    log('self-check: importing stdlib modules')
    run(pythonExe, ['-c', "import sqlite3,tomllib,json,ssl,urllib.request; print('ok')"])

    log('self-check: running taskproof')
    run(pythonExe, ['-m', 'taskproof', '--version'], {
      env: { ...process.env, PYTHONPATH: join(repoRoot, 'src') }
    })

    const dest = join(runtimeRoot, target)
    if (existsSync(dest)) rmSync(dest, { recursive: true, force: true })
    renameSync(staging, dest)
    moved = true
    log(`staged runtime at ${dest}`)
  } finally {
    // Never leave a half-built staging tree behind, even on failure.
    if (!moved) rmSync(staging, { recursive: true, force: true })
  }
}

main().catch((error) => {
  if (error instanceof FetchRuntimeError) {
    console.error(`fetch-runtime: ${error.message}`)
  } else {
    console.error(`fetch-runtime: ${error.stack || String(error)}`)
  }
  process.exit(1)
})
