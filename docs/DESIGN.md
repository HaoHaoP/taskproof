# Design

> Output of the initial design session: 11 decisions plus hard constraints.
> Status: **design settled, not implemented.**

## One line

A conveyor belt for AI coding agents: it does not decide what to do, it only
guarantees that what was dispatched gets verified and recorded.

## Origin

Extracted from a private workflow that ran for a few weeks: a small bash
dispatcher (~330 lines), a project registrar that probes a repository and derives
its acceptance command, a structured-result contract, an append-only task ledger,
and a dashboard. Roughly 60 tasks ran through it, which surfaced the failure
modes this project is built around.

## Why it is worth existing

Comparable projects (golutra ★3.8k, CAO ★1.4k by AWS, cezar ★516, agetor ★88)
compete on orchestration breadth and UI. Their READMEs barely mention:

**Agents lie.**

Observed:

```
agent claimed "verified in browser / screenshot taken"   -> no browser activity in the event stream
agent went out of scope                                  -> attempted an HTTP login with a guessed credential
agent's JSON result wrapped in a markdown fence          -> structured parse failed, run looked empty
agent reported success                                   -> acceptance command failed when run independently
```

The mechanisms that answer this — **verification independent of self-report,
protected paths, a structured result contract, an append-only audit trail,
meaningful exit codes** — are this project's core asset. It is not another
orchestrator; it is a dispatch layer that does not trust the worker.

## Positioning

```
Purely mechanical, no LLM — it does not decide "what to do", only guarantees
                            "dispatched => verified, and recorded"
Callable by anything       — Hermes / Claude Code / a human at a terminal share one CLI
```

The dividing line against "bound to one agent" tools: no orchestration brain
required, and it does not pretend to be one.

## Non-goals

```
No built-in LLM orchestration (no decomposition, no failure diagnosis, no retry policy)
No multi-agent conversation layer
No code generation or editing
No automated git write operations (commit / push are never automated)
```

## Stack

```
Language    Python, single package, standard library only, Python 3.11+
            (sqlite3 / subprocess / json / http.server / argparse / tomllib)
Install     pipx install taskproof
License     Apache-2.0 (patent grant included, corporate-friendly; deliberately
            not AGPL — this tool's value depends on being adopted)
Repo        a standalone repository, strictly isolated from any employer code
```

## Storage

```
SQLite  — primary state store
  claims, task state and dashboard queries all read it
  transactions replace lock files (a crashed process no longer leaves a stale lock)
  retention and archiving live in code, not in a human's calendar

events.jsonl — audit stream
  one line appended per operation, WRITE-ONLY, never consulted for logic
  rotated monthly, older files gzipped
  purpose: audit, plus "read it once tomorrow morning and know where things stand"
```

Key design point: JSONL carries no query responsibility, so the
"two sources of truth" problem cannot arise. (The predecessor kept a ledger and
a separate card registry that drifted, which is how a dashboard ends up showing
"running" for a task that finished hours ago.)

**Config and state are separated**: the project registry is a TOML file (human
editable, version-controllable in the user's own repo). Only runtime state goes
into SQLite. TOML rather than YAML because the standard library ships `tomllib`
(Python 3.11+) while YAML would pull in a dependency.

## Data model

```sql
tasks
  id            TEXT PK     t-20261007-001
  project       TEXT        registry id
  group         TEXT        concurrency group
  brief         TEXT        task description
  status        TEXT        queued|running|verifying|done|failed|blocked|timeout|cancelled
  adapter       TEXT        codex|claude|gemini|opencode|custom:<cmd>
  model         TEXT
  reasoning     TEXT
  attempt       INTEGER
  exit_code     INTEGER
  pid           INTEGER
  pgid          INTEGER     adapter's own process group (cancel signals this)
  queue_seq     INTEGER     explicit queue order; set only while queued
  workdir       TEXT
  result_path   TEXT
  verify_cmd    TEXT
  verify_exit   INTEGER
  files_changed INTEGER
  created_at    TEXT
  started_at    TEXT
  finished_at   TEXT

events
  id INTEGER PK, task_id TEXT, ts TEXT, event TEXT, payload TEXT(JSON)  -- same origin as JSONL

claims                          -- concurrency guard, with expiry-based reclamation
  scope      TEXT PK            group:<g> | global
  task_id    TEXT
  pid        INTEGER
  claimed_at TEXT
  expires_at TEXT               -- a dead process is reclaimed automatically
```

## Adapter contract

An adapter is one command template plus one result-parsing convention.

```
Built in   codex / claude / gemini / opencode
Fallback   custom:<cmd>          any command
Contract
  in    workdir / brief / model / reasoning / sandbox mode
  out   (1) structured  — when the CLI can emit a schema-constrained result
        (2) degraded    — scrape stdout under a documented convention
        (3) failure     — exit code plus the last N lines
Documented traps: markdown-fenced JSON, self-declared "verified", scope violations
```

## Concurrency and timeouts

Carried over from the predecessor, defaults configurable:

```
Same-group serial    only one task per group runs at a time
Global cap           default 3 concurrent tasks
Hard timeout         default 1800s; on expiry the task is judged stuck and
                     THAT task's process is killed
Over-limit behaviour exit immediately (no queueing); the caller decides when to retry
Process safety       only processes taskproof started are ever killed
```

## Exit codes

```
0    success
2-3  registry problem
64   usage error
70   adapter (agent) failure
71   verification or artifact self-check failure
75   concurrency limit reached
```

## The forbidden-path gate

The gate answers one question: *did this run move a path the registry protects?*
It must answer it without trusting the agent and without blaming it for the
world's noise. Two design rules follow.

**The signal is a difference, not a snapshot.** The gate records the protected
state before the adapter starts and compares it after the adapter exits. A
present-tense snapshot is wrong on its face: a repository can be dirty when the
run begins — a Finder `.DS_Store`, an untracked scratch directory, a
half-finished build — and a current-state check reports all of it as the
adapter's work on *every* run. Only a path whose state differs between the two
snapshots belongs to this run.

**One signal per rule, chosen by what is being protected.** A rule's `kind`
selects its probe, and the audit event carries that `kind` so a reader can tell
which one fired:

```
file       git-status difference OR size:mtime_ns fingerprint difference
           the historical signal; catches content edits, additions, removals
git        HEAD / symbolic-ref / refs / stash state (the `.git/` probe)
           catches commits, history rewrites, branch/tag moves, stashes
presence   file-set membership only
           catches files added or removed; ignores a content-only rewrite
```

`presence` is the deliberate trade of sensitivity for precision. A dev server
rewriting an existing build artifact changes its content but not the file set,
and the user never touched the tree — so the gate stays quiet. The cost is real
and documented: under `presence`, rewriting an existing file is **not** a
violation. A repository that needs that case caught uses the default `file`
rule for the path instead.

Untyped rules keep the historical meaning, so existing registries do not change
behaviour: a bare path is a `file` rule, and the historical bare `.git/` rule
keeps its git-state meaning. The type prefix is `file:` / `git:` / `presence:`.

## CLI surface

```
taskproof init                          initialise a workspace (db, sample registry)
taskproof register <path> [--dry-run]   probe a repo and register it
taskproof projects                      list registered projects
taskproof run <project|path> "<brief>"  dispatch (primary command)
          [--adapter X] [--model X] [--reasoning X]
          [--read-only] [--worktree] [--no-verify] [--verify-only]
taskproof tasks [--status S] [--project P] [--limit N]
taskproof show <task-id>                single task detail
taskproof log <task-id>                 event stream
taskproof verify <task-id>              re-run acceptance
taskproof cancel <task-id>              stop a task (SIGTERM -> SIGKILL its own tree)
taskproof rm <task-id>                  delete a terminal task's record, events and kept worktree
taskproof board [--open | --serve PORT | --out FILE]
taskproof api --port N [--allow-write]  local REST (consumed by the stage 2 frontend)
taskproof doctor                        environment self-check
taskproof gc                            archive and rotate
```

`--worktree` runs the task in a fresh checkout *beside* the repo
(`<repo parent>/<repo name>-wt-<task-id>`). It is removed when the run finishes
clean; if it still has changes it is kept, printed as
`worktree kept: ... (N files changed)`, recorded as a `worktree` event, and
deleted later by `taskproof rm <task-id>`.

Human-readable output follows the locale; `--json` for machines.

## Frontend and phasing

```
stage 1  engine + CLI + local REST API + minimal static dashboard
         the minimal dashboard exists only to validate the data model;
         the REST boundary is fixed here so stage 2 replaces only the rendering layer
stage 2  Vue 3 + Vite frontend -> Electron shell (no embedded Python runtime)
later    whether to embed the Python runtime in the Electron bundle is a pure
         packaging decision and does not affect the architecture
```

After Electron, the repository is bilingual (Python + TypeScript); CI, release
process and contributor onboarding are designed for two artifacts.

### Stage 2: the desktop app

The static dashboard is **frozen**: it keeps working as a `file://` snapshot and
is not developed further. Stage 2 builds a separate Electron application in
`desktop/` that consumes the same loopback REST API. That API stays read-only by
default; only an explicit `--allow-write` opens a session-token-gated write
surface (project create / edit / delete, plus task control: dispatch / cancel /
remove / queue-seq edit) on top of it. The Python package gains
only the small changes described below; everything else is additive.

**Stack.** TypeScript, Vue 3 (`<script setup>`), electron-vite
(main / preload / renderer), Pinia, vue-router (hash mode — production loads
over `file://`), Element Plus, UnoCSS, vue-i18n, electron-builder. Dev-run only
for v1; no packaged installer yet.

**Process model.** Electron owns the server: it spawns `taskproof api --port 0`,
reads the bound port from the child's stdout, and terminates the child on exit.
The Python-side changes are these: today `api` defaults to 8787 and blocks
without printing the port, and it has no write surface.

```
taskproof api --port 0     bind an ephemeral port, print one flushed line with
                           the actual port, then serve (read-only)
taskproof api --port 0 --allow-write
                           also print a second line with a session-only token
                           and enable token-gated registry writes
```

**Matrix column model.** Columns express *which stage of the pipeline a task has
reached*; the reason a task did not pass is a property of the card, not a stage.
The board therefore has five columns — queued, running, verifying, done, and
*not passing* — where the last one holds every abnormal terminal state
(`failed`, `blocked`, `timeout`, `cancelled`), each keeping its own colour and
glyph.

Hard rule, inherited from the Python board: **an unknown status is always
rendered, never dropped.** The Python board already folds unknown statuses into
`failed` for the same reason ("a new lifecycle state can never silently hide a
task"); the frontend carries the equivalent guard.

**Enum contract.** Status words, `verify_kind` values and exit-code meanings are
one artefact in the repository (`contract/enums.json`, generated from the Python
constants and checked in). TypeScript imports it; CI regenerates and diffs, so
the two languages cannot drift.

**Component boundaries.** Route components are containers — they own fetching
(polling the REST API) and state; presentational components take props and emit
events, and never touch a store or the network. The task drawer is part of the
route (`/matrix/:taskId`), so it is owned by the page container instead of
being rendered at app level.

**Cross-process boundary.** Preload exposes a small, named API (`window.tp`:
settings / service / projects / shell) — not a generic
`invoke(channel, payload)`. Writes to the registry go through the main process,
so the **local write token never reaches the renderer**; the main process also
performs the compare-before-save (mtime/hash) that detects external edits.

**Settings.** A single `settings.json` in Electron's `userData`, held by the
main process as the source of truth and exposed to the renderer over IPC.
Main-process items (port, taskproof path, workspace, launch, tray,
notifications, dock badge, autostart) and renderer items (theme, language) live
in the same file.

**Internationalisation.** zh-CN + en, following the system locale and falling
back to **en**. Only UI chrome is translated; task briefs and summaries are user
data and are never translated.

## Repository and compliance

```
Employer asset hygiene (hard constraint)
  No internal project names, no internal hostnames or IPs, no acceptance commands
  from private repositories, no credential fragments — including in examples.

  The scan is tools/scan_assets.py. Enable the gate once per clone:
      git config core.hooksPath .githooks

  The organisation-specific words live OUTSIDE the repository
  (~/.taskproof/asset-patterns.txt, or $TASKPROOF_ASSET_PATTERNS): a scanner that
  shipped them would leak exactly what it is meant to protect. The rules that do
  ship describe shapes only, so the scan is never a no-op.

Automated git writes: never.
```

## Stage 1 completion criteria

```
1  After pipx install, on a clean repository: init -> register -> run -> verify
   -> the task appears on the dashboard
2  Adapters: codex works, custom:<cmd> works, interface is stable (the rest may follow)
3  SQLite state store + JSONL audit (monthly rotation; JSONL is never read for logic)
4  Concurrency guard implemented with transactions (no lock files), with expiry reclamation
5  Verification independent of self-report; protected paths enforced; exit codes aligned
6  Minimal static dashboard + REST API (list tasks, task detail, event stream)
7  Tests covering the core paths (concurrency guard / verification verdict /
   result parsing / archive rotation)
8  Docs: README (EN + zh-CN), example registry, a from-zero walkthrough
9  Employer-asset scan: zero hits
```

## Open questions

```
Positioning / differentiator — "land it first, find the angle later"
Embedded Python runtime      — after stage 2, driven by demand
Multi-user / remote auth     — out of scope for now
Splitting into several repositories (core / adapters / desktop) — possible later;
   a single repository for now
```

## Appendix: prior art surveyed

```
3.8k  golutra/golutra                      Rust   multi-agent platform, richest UI
2.1k  catlog22/Claude-Code-Workflow         TS    JSON-driven multi-agent framework
1.4k  awslabs/cli-agent-orchestrator (CAO)  Py    AWS; coordinates multiple coding CLIs
1.3k  bradAGI/awesome-cli-coding-agents     Py    curated index of this space
563   catlog22/maestro-flow                 TS    intent-driven workflow orchestration
559   aannoo/hcom                          Rust   agents messaging/watching/spawning each other
530   mco-org/mco                           Py    CLI-first parallel cross-verification
516   open-mercato/cezar                    TS    orchestrator + ADE, VPS-deployable
419   dsifry/metaswarm                     Shell  18 personas + 9-phase workflow
88    alamops/agetor                        TS    local-first kanban + per-task git worktree
0     anthhub/codex-dispatch               Shell   dispatches tasks to parallel Codex workers
```

Naming survey: the ten most fitting English words (foreman / steward / warden /
attest / gauntlet / verdict / notary / overseer / proven / proofrun) are all
already taken on PyPI. `taskproof` is available, with only 13 same-named GitHub
repositories.
