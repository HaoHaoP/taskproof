/**
 * First-boot workspace bootstrap.
 *
 * A brand-new install has no `~/.taskproof`. The app used to leave that to the
 * CLI and hope: the API child starts fine against a missing directory, but the
 * registry row and the board then look broken. On first boot we create the
 * directory and a *minimal* `projects.toml` -- a `[defaults]` table plus a
 * commented `[[project]]` example -- and nothing else.
 *
 * Two hard rules, both from the card:
 *   - never create tasks and never write sample *data* (no fake projects);
 *   - never clobber an existing file -- bootstrap is create-only.
 */
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { join } from 'path'

/** `<workspace>/projects.toml`, matching the Python side's registry name. */
export function registryPath(workspace: string): string {
  return join(workspace, 'projects.toml')
}

/**
 * The smallest honest registry: `[defaults]` carries the concurrency cap and
 * the task timeout, and the only `[[project]]` is a commented-out example --
 * so a fresh workspace parses to zero projects, never a placeholder repo.
 */
export function minimalProjectsToml(): string {
  return `# taskproof project registry
#
# One [[project]] block per repository. Paths are absolute.
# \`group\` controls serialisation: only one task per group runs at a time.
#
# No projects yet: \`taskproof register <path>\` appends one.
# A commented, complete example: examples/projects.example.toml
# Field reference: docs/REGISTRY.md

[defaults]
# concurrency is deliberately unset: leaving it out lets taskproof pick a safe
# cap from this machine (cores / 4, clamped to 2..6). Pin it here to fix it.
timeout = 1800    # seconds before a task is judged stuck

# Example project entry -- uncomment and edit, or run \`taskproof register <path>\`:
# [[project]]
# id = "my-app"
# path = "/absolute/path/to/my-app"
# group = "my-app"
# verify = "npm run build"
# verify_kind = "build"
# forbidden_paths = [".git/", "dist/", "node_modules/"]
`
}

export interface EnsureWorkspaceResult {
  /** True when this call created the directory (i.e. it was a first boot). */
  createdDir: boolean
  /** True when this call wrote `projects.toml`. */
  wroteRegistry: boolean
}

/**
 * Create `workspace` (recursively) and seed `projects.toml` if it is missing.
 * Idempotent and non-destructive: an existing directory or file is left
 * untouched, so a second boot is a no-op and a hand-edited registry survives.
 */
export function ensureWorkspace(
  workspace: string,
  deps: {
    exists?: (p: string) => boolean
    mkdir?: (p: string) => void
    write?: (p: string, data: string) => void
  } = {}
): EnsureWorkspaceResult {
  const exists = deps.exists ?? existsSync
  const mkdir = deps.mkdir ?? ((p: string) => mkdirSync(p, { recursive: true }))
  const write = deps.write ?? ((p: string, data: string) => writeFileSync(p, data, 'utf8'))

  const createdDir = !exists(workspace)
  if (createdDir) mkdir(workspace)

  const reg = registryPath(workspace)
  if (!exists(reg)) {
    write(reg, minimalProjectsToml())
    return { createdDir, wroteRegistry: true }
  }
  return { createdDir, wroteRegistry: false }
}
