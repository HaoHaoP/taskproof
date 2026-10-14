#!/usr/bin/env node
/**
 * Build the desktop renderer and stage it as the Python package's web board.
 *
 * `taskproof board` serves the *same* Vue renderer the Electron console shows,
 * so there is one rendering layer with two hosts instead of two look-alikes that
 * drift. That only holds if the artefacts shipped inside the wheel are exactly
 * what the renderer source produces, so this script:
 *
 *   1. runs the existing `electron-vite build` (no second Vite config);
 *   2. prints every file it is about to delete, then empties *only*
 *      `src/taskproof/web/` and copies `out/renderer/**` back into it;
 *   3. writes a `.gz` sibling for every text asset larger than 1 KiB so the
 *      server can hand a pre-compressed body to the browser without shelling
 *      out to a compressor at request time.
 *
 * The result is committed on purpose: a source checkout is pipx-installed with
 * `--editable`, so the browser board tracks the renderer immediately, and the
 * wheel carries the same bytes. Like `contract/enums.json`, CI rebuilds it and
 * fails if `git diff` is non-empty, because drift here means the browser board
 * and the desktop console are no longer the same code.
 *
 *   node scripts/build-web.mjs
 *
 * Everything is deterministic: no timestamps in file contents, sorted copies,
 * and `.gz` siblings produced by the pinned pure-JS compressor `fflate` (see
 * package.json), which writes a fixed gzip header (mtime 0, no filename), so the
 * compressed bytes depend only on the input.
 *
 * Determinism has to hold across machines, not just within one build tree, and
 * the built-in `zlib` cannot give that: Node bundles a different zlib release in
 * every version, and even the same version can compress differently on different
 * platforms. Compressing with the built-in `zlib` therefore produced different
 * `.gz` bytes on the CI runner than on a developer's machine, which made the
 * "committed board equals a fresh rebuild" check below go red on any machine
 * whose zlib differed from the one that produced the committed assets. `fflate`
 * is pure JavaScript and version-locked, so the same input compresses to the
 * same bytes everywhere.
 */
import { spawnSync } from 'node:child_process'
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync
} from 'node:fs'
import { extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'fflate'

const here = fileURLToPath(new URL('.', import.meta.url))
const desktopDir = resolve(here, '..')
const repoRoot = resolve(desktopDir, '..')
const rendererDir = join(desktopDir, 'out', 'renderer')
const webDir = join(repoRoot, 'src', 'taskproof', 'web')

/** Text asset types worth shipping a `.gz` sibling for. */
const TEXT_EXTENSIONS = new Set(['.js', '.css', '.html', '.svg', '.json', '.map'])
/** Only compress resources larger than this; small files gain nothing. */
const GZIP_THRESHOLD = 1024

/** A failure we raise on purpose: printed without a stack, exit code 1. */
class BuildWebError extends Error {
  constructor(message) {
    super(message)
    this.name = 'BuildWebError'
  }
}

function fail(message) {
  throw new BuildWebError(message)
}

function log(message) {
  console.log(`build-web: ${message}`)
}

/** Run a child process to completion, throwing loudly on any failure. */
function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', ...options })
  if (result.error) fail(`failed to run \`${command}\`: ${result.error.message}`)
  if (result.status !== 0) fail(`\`${command} ${args.join(' ')}\` exited with ${result.status}`)
}

/** Resolve electron-vite's JS entry from its package.json (works cross-platform). */
function electronViteEntry() {
  const pkgPath = join(desktopDir, 'node_modules', 'electron-vite', 'package.json')
  if (!existsSync(pkgPath)) {
    fail('electron-vite is not installed; run `npm ci` in desktop/ first')
  }
  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'))
  const bin = typeof pkg.bin === 'string' ? pkg.bin : pkg.bin && pkg.bin['electron-vite']
  if (!bin) fail('could not find the electron-vite executable in its package.json')
  return join(desktopDir, 'node_modules', 'electron-vite', bin)
}

/** Files under `dir`, as paths relative to it, sorted for a stable listing. */
function filesUnder(dir) {
  const found = []
  const walk = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const full = join(current, entry.name)
      if (entry.isDirectory()) walk(full)
      else found.push(relative(dir, full))
    }
  }
  if (existsSync(dir)) walk(dir)
  return found.sort()
}

/** Refuse to delete anything but the board directory, however this is invoked. */
function assertIsWebDir() {
  const expected = join('src', 'taskproof', 'web')
  if (webDir !== join(repoRoot, expected)) {
    fail(`refusing to clear ${webDir}: expected it to be ${join(repoRoot, expected)}`)
  }
}

function buildRenderer() {
  log('building the renderer (electron-vite build)')
  run(process.execPath, [electronViteEntry(), 'build'], { cwd: desktopDir })
  if (!existsSync(rendererDir)) fail(`electron-vite did not produce ${rendererDir}`)
}

function stage() {
  assertIsWebDir()
  const stale = filesUnder(webDir)
  const webLabel = relative(repoRoot, webDir)
  if (stale.length === 0) {
    log(`nothing to clear in ${webLabel}`)
  } else {
    log(`clearing ${webLabel} (${stale.length} file(s)):`)
    for (const file of stale) console.log(`    - ${file}`)
  }
  rmSync(webDir, { recursive: true, force: true })
  mkdirSync(webDir, { recursive: true })
  cpSync(rendererDir, webDir, { recursive: true })
  log(`copied ${relative(repoRoot, rendererDir)} -> ${webLabel}`)
}

function gzipTextAssets() {
  let written = 0
  for (const rel of filesUnder(webDir)) {
    const full = join(webDir, rel)
    if (!TEXT_EXTENSIONS.has(extname(rel).toLowerCase())) continue
    if (statSync(full).size <= GZIP_THRESHOLD) continue
    // fflate writes a fixed (zero) mtime and no filename and is pure JS, so the
    // bytes depend only on the input and stay identical on every machine --
    // important for the CI diff. (the built-in `zlib` would vary by version/platform.)
    writeFileSync(`${full}.gz`, gzipSync(readFileSync(full), { level: 9, mtime: 0 }))
    written += 1
  }
  log(`wrote ${written} gzip sibling(s) for text assets over ${GZIP_THRESHOLD} B`)
}

function main() {
  buildRenderer()
  stage()
  gzipTextAssets()
  log('done')
}

try {
  main()
} catch (error) {
  if (error instanceof BuildWebError) {
    console.error(`build-web: ${error.message}`)
  } else {
    console.error(error.stack || String(error))
  }
  process.exit(1)
}
