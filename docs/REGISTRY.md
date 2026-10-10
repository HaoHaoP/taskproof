# Project registry

The registry is the only configuration file taskproof reads. It is TOML, it
describes *which repositories may be dispatched and how each is verified*, and
it lives in the workspace:

```
~/.taskproof/projects.toml        default; the workspace is configurable
```

`examples/projects.example.toml` is a working starting point. This document is
the reference; that file is the tour.

## Two layers: project and taskgroup

An entry is one of two things:

* a **project** (`[[project]]`) — a repository / filter unit: an `id`, a default
  `path`, and `aliases`. It is *not* dispatchable on its own.
* a **taskgroup** (`[[taskgroup]]`, "道") — one lane tasks are dispatched onto:
  an `id`, an owning `project`, a `path` (defaulting to the project's), aliases,
  the acceptance command and the result contract.

A project groups the history of everything done in one repository; a taskgroup
is the unit a run targets. A taskgroup's `group` is its **concurrency lock
name**; it defaults to the taskgroup `id`, so one task per lane runs at a time.
Two lanes may set the same `group` to serialize with each other, including
across projects and registry entries.

## Structure

```toml
[defaults]
concurrency = 3      # global cap on simultaneously running tasks
timeout     = 1800   # seconds before a running task is judged stuck and killed

# The repo: one identity, one default path.
[[project]]
id      = "my-app"
path    = "/absolute/path/to/my-app"
aliases = ["app"]

# A single lane. Its path is inherited from the project.
[[taskgroup]]
id     = "my-app"
project = "my-app"
# group = "my-app"      # optional; this is the default
verify = "npm run build"
verify_kind = "build"
```

`[defaults]` is optional; both keys take the values shown above when omitted.

A project can own **several lanes** — a subdirectory, a second checkout, a
docs build that shares the repo. Each lane carries its own acceptance command,
and its `path` overrides the project default when present:

```toml
[[project]]
id   = "api-service"
path = "/absolute/path/to/api-service"

[[taskgroup]]
id      = "api-service"
project = "api-service"
verify  = "mvn -q -DskipTests compile"

[[taskgroup]]
id      = "api-service-docs"
project = "api-service"
path    = "/absolute/path/to/api-service/site"   # a subdirectory
verify  = "npm test"
```

## `[[project]]` fields

| Field | Required | Default | Notes |
|---|---|---|---|
| `id` | yes | — | Unique. Duplicate ids are a hard error. |
| `path` | yes | — | Must be **absolute**. The default path for its lanes. |
| `aliases` | no | `[]` | Alternative names accepted wherever an id is accepted. |
| `group` | no | the block `id` | Only meaningful on a compatibility lane block (one that also carries a lane field). The implicit lane's lock name is preserved from the old file. |
| `verify` / `verify_kind` / `forbidden_paths` / `result_schema` | no | — | Not project fields. Any of them on a `[[project]]` block switches on the compatibility rule below. |

## `[[taskgroup]]` fields

| Field | Required | Default | Notes |
|---|---|---|---|
| `id` | yes | — | Unique. Every command may refer to a lane by it; the lock defaults to it. |
| `project` | no | the taskgroup `id` | Owning project. Omitted ⟺ the lane stands up a same-named project. |
| `path` | no | the project `path` | Must be **absolute**. Overrides the project default. |
| `aliases` | no | `[]` | Alternative names accepted wherever the id is accepted. |
| `group` | no | the taskgroup `id` | Concurrency lock name. Lanes with the same value serialize, including across projects or registry entries. |
| `verify` | no | — | The acceptance command, run by taskproof **after** the agent exits. |
| `verify_kind` | no | `"none"` | `check` / `build` / `none`. Anything else is a hard error. |
| `forbidden_paths` | no | `[]` | Prefix-matched paths the agent must not touch. Each entry may carry a `file:` / `git:` / `presence:` type; untyped entries are `file`. |
| `result_schema` | no | `"default"` | `"default"`, `"none"`, or an absolute path to a JSON Schema. |
| `auto_registered` | no | `false` | Written by `taskproof register`; not meant to be edited by hand. |

## Reading a flat, older file (zero migration)

A `[[project]]` block that carries any lane field — `verify`, `verify_kind`,
`forbidden_paths`, or `result_schema` — is read as **two** declarations:

* a project `id = <block id>` with the block's `path` and `aliases`, and
* a taskgroup `id = <block id>`, `project = <block id>`, inheriting the path and
  carrying the lane fields.

So a registry written before the split keeps working, byte for byte and without
editing: every block that used to be a dispatchable entry becomes a project plus
a same-named lane, and `taskproof run <old id> "…"` still resolves. A
`[[project]]` block *without* any lane field is a bare filter-only project (0
lanes) and is not dispatchable until a lane hangs off it.

The old `group` key is carried through to the implicit lane. If it is missing
or empty, the lane's `group` is its id. Two old blocks that shared a `group`
therefore still share one lock; use a distinct `group` on either block to make
them independent.

## Resolution order

`by_id` / `require` (and therefore `run`, `accept`, `tasks --project`, …) match
in this order:

1. a **taskgroup** `id`, then a taskgroup `alias`;
2. a **project** `id`, then a project `alias` — this resolves only when the
   project has **exactly one** lane. A project with several lanes is a hard
   error that lists its lanes, so a bare project id is never silently
   mis-dispatched;
3. a path: an exact match against a lane path, then a project path.

Path inference from the working directory (`resolve_scope`) keeps its old
behaviour: cwd matches a lane when it is that lane's path **or a descendant**,
and the **deepest** matching lane path wins, so a nested checkout beats its
parent repository. When two lanes match at the same depth the choice is
ambiguous and refused, naming the candidates.

## Semantics worth spelling out

**A lane's lock is its `group`, which defaults to its id.** One task per lock
runs at a time; different locks run in parallel up to `concurrency`. Two lanes
may deliberately share a `group`; this is useful when they point at the same
checkout or another shared resource. A `group` key on a legacy `[[project]]`
block is preserved for the same reason.

**A missing `verify` is SKIPPED, never "passed".** With no acceptance command,
`verify_kind` is forced to `none` and verification is recorded as skipped. This
is deliberate: "we did not check" and "we checked and it passed" must never look
the same in the audit trail.

**The acceptance command is not the agent's claim.** `verify` runs in the lane
path after the agent process has exited. Nothing the agent says about its own
work counts as evidence.

**A missing custom schema is a hard error.** A `result_schema` path that does
not exist stops the run instead of silently falling back to the default —
falling back would change the result contract behind your back.

**Forbidden paths are judged on a before/after difference, and each rule
picks its signal.** A rule ending in `/` covers the directory and everything
below it; a rule without the trailing slash must match that exact path. A
violation fails the task even when the agent reported success.

The gate takes a snapshot before the adapter runs and again after it exits, and
only the **difference** counts. A path that was already dirty or untracked
before the run — a Finder `.DS_Store`, a leftover build artifact, a directory a
human left behind — stays in both snapshots and is never attributed to the
adapter. The error payload's `kind` names the signal that fired.

**Syntax.** A rule is either a bare path (the legacy spelling) or a
`<type>:<path>` pair. The recognized types are:

| Type | Meaning | Fires on |
|---|---|---|
| `file` (default) | fingerprint + git-diff | a path under the rule appears, disappears or changes content — the historical behaviour, unchanged |
| `git` | repository state (HEAD / refs / stash) | a commit, history rewrite, branch switch, tag or stash |
| `presence` | file-set membership only | a file under the rule is added or removed |

```toml
forbidden_paths = [
  ".git/",             # untyped: keeps its historical git-state meaning
  "protected/",        # untyped: the historical file fingerprint signal
  "file:protected/",   # explicit form of the line above
  "git:.git/",         # explicit form of the .git line above
  "presence:web/dist/",# dev-server / HMR output: content rewrites are ignored
]
```

Untyped rules stay byte-for-byte compatible with the previous release: they
behave exactly as `file:` rules did (and the special untyped `.git/` rule keeps
its git-state meaning, as described below). Because the prefix uses a colon,
protect a literal path that itself begins with `file:`/`git:`/`presence:` by
spelling it with an explicit extra prefix, e.g. `file:presence:notes.txt`.

**Which signal to use.** `presence:` exists for trees that a background process
writes to without the agent's involvement — Vite/Webpack HMR rewriting
`dist/**`, `node_modules/.cache/**` — and for directories where the agent is
only forbidden from adding or deleting files. Its trade-off: a content-only
rewrite of a file that already existed is **not** a violation. If you also need
to catch content edits, use the default `file:` signal for that path.

The default `file` signal deliberately does not rest on the `git status` change
list alone. git reports nothing inside `.git/`, and it omits every ignored path
— which is what build output and dependency directories are. Measured: with
`forbidden_paths = ["dist/"]` and `dist/` in `.gitignore`, an adapter wrote
`dist/app.js` and the run was recorded as `done`. So declared `file` paths are
also fingerprinted before and after the run, which covers ignored paths and
everything else; the git difference and the fingerprint difference are OR-ed.

A rule that targets the repository's `.git` directory is special-cased: its
state (HEAD, refs and stash) is compared instead of its bookkeeping files, so a
read-only `git status` index refresh is not a violation while commits, resets,
branch/tag changes and stashes still are: the probe reads HEAD, the symbolic
branch, every `refs/heads`, `refs/remotes` and `refs/tags` entry, and the stash
list. One limit worth knowing: a protected tree larger than 20000 entries is
sampled, and the audit event records `snapshot_truncated: true` when that
happens.

## Hard errors

Each of these stops the run with exit code 2:

```
registry file not found
invalid TOML
[defaults] is not a table
a [[project]] or [[taskgroup]] entry is not a table
a project is missing id or path
a taskgroup is missing id
a taskgroup names a project that does not exist
a taskgroup with no project has no path
path is not absolute
duplicate project id / duplicate taskgroup id
verify_kind is not one of check / build / none
result_schema is neither "default", "none", nor an absolute path
result_schema file not found
a bare project id resolves to several lanes
```

## Editing it

The file is configuration: commit it to your own repository if that suits you.
`taskproof register <path>` appends a `[[taskgroup]]` and is the intended way to
add a lane, but hand-editing is fine — the file is read on every run.

Runtime state never lands here. Tasks, events and verdicts live in the SQLite
store; the audit stream is JSONL.

## REST surface

The local API is **read-only**. Every mutation lives in the CLI
(`taskproof register`, `taskproof config`, `run`, `accept`, `cancel`, `rm`);
the server exposes no write endpoint and mints no session token. A write-shaped
request to a path that used to be a write endpoint is a plain `404`.

The endpoints the frontend reads:

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{"ok", "version", "concurrency"}` |
| `GET /api/summary` | `{"summary", "concurrency"}` |
| `GET /api/registry` | `{"path", "hash", "mtime"}`; `hash` is the lowercase SHA-256 of the raw bytes |
| `GET /api/projects` | `{"projects": [ … ]}` — **one row per lane** (taskgroup) plus its task tallies; each row also carries the owning `project` id |
| `GET /api/tasks` | `{"tasks": [ … ], "count"}`; filters `?status=`, `?project=`, `?limit=` |
| `GET /api/tasks/<id>` | one task detail with its events |
| `GET /api/tasks/<id>/events` | `{"task_id", "events"}` |
| `GET /api/tasks/<id>/log` | a log window (tail, or forward from `?offset=`) |

## Registry writes

`projects.toml` is edited by the CLI, never the API. `taskproof config` calls
`registry.set_default`; `taskproof register` appends a new `[[taskgroup]]` block
(use `--project` to hang it off an existing project, or omit it and the lane
stands up its own). Under the hood the registry's writers (`append_taskgroup` /
`update_project` / `delete_project`) refuse a stale `expected_hash` with
`RegistryConflictError` rather than silently overwriting a hand-edited file.
`update_project` and `delete_project` operate on **either** block kind.

### Surgical rewrite

Writes are done at the byte level, never by re-serialising the parsed TOML —
that would discard the handwritten comments and any keys `registry.load` does
not understand. Instead the whole file text is read, `[[project]]` /
`[[taskgroup]]` block boundaries are found by line, and only lines inside the
target block are added, changed or removed; every other byte is preserved.
Deleting a block also removes the comment lines directly above it (no blank line
in between) and leaves comments that are separated by a blank line, so a
neighbouring block's note is never taken along. After editing, the candidate is
re-parsed with `tomllib` and re-loaded, and only then written atomically (a temp
file in the same directory followed by `os.replace`). A candidate that fails to
parse or validate never reaches the real file.
