# taskproof

<p align="center"><img src="docs/assets/icon.png" width="128" alt="taskproof"></p>

A conveyor belt for AI coding agents.

It does not decide *what* to do. It guarantees that whatever gets dispatched is
**independently verified** and **recorded** — so you never have to trust an
agent's own claim that it finished.

**Status: stage 1 is usable, and the stage-2 desktop console is here.** The
engine, CLI, a static board, a local read-only REST API, and an Electron console
in `desktop/` are implemented. See [`docs/DESIGN.md`](docs/DESIGN.md) for the
full design and the decision log.

### Quick start

```bash
pipx install taskproof        # or, from a source checkout: pip install -e .
taskproof init
taskproof register /path/to/your/repo
taskproof run your-repo "fix the failing test"
taskproof board --open
```

[`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) runs that end to end on a throwaway
example — including the case where the agent reports success and the acceptance
command disagrees.

---

## Dispatching work

The usage this project is extracted from is a *discipline for the agent that
hands out the cards*, and it now ships in the repository as a skill:

```
skills/taskproof-dispatch/SKILL.md
```

It is written for the **orchestrating agent** — the one that plans the work,
registers the repositories, writes each card, and dispatches it to a worker.
Taskproof itself does not plan anything (see Non-goals); this skill is the
missing half: how to drive the tool without the failure modes the hard way.

It turns the lessons of this build into steps you can copy: register a project,
put a card in a file and pass it with `$(cat …)`, fire it with an explicit
`--adapter` and `--timeout`, then read state back with `taskproof tasks --all`
and `taskproof log <id>`. Above all it pins four things that were learned by
breaking them:

- **Serialisation is a property of the group, not a habit.** Different groups
  are meant to run in parallel up to the global cap; the only reason to serialise
  is "same group *and* overlapping files".
- **The real registry is never a test target.** UI verification runs against a
  throwaway profile and workspace under `/tmp`; a worker that deletes against the
  live `~/.taskproof/projects.toml` takes a user's project with it.
- **Never `pkill -f`.** A card is passed as process argv, so its text is in the
  dispatcher's own command line — `pkill -f` matches the dispatcher and kills the
  run (exit -15, no task, empty log). Kill by PID.
- **Review is not a self-report.** The main agent re-runs the acceptance command
  and makes its own objective assertion; "the worker said done" is not evidence.

## The problem

Every orchestration project on GitHub competes on *how many agents it can run*,
*how many CLIs it supports*, and *how pretty the UI is*. Almost none of them
talk about the thing that actually bites you in daily use:

**Agents lie.**

Real incidents from the workflow this project is extracted from:

| What the agent said | What actually happened |
|---|---|
| "Verified in browser, screenshots attached" | Event stream contained zero browser activity |
| (silently, beyond scope) | Attempted an HTTP login against a local app using a guessed weak credential |
| Task complete, result file written | The JSON had been wrapped in a markdown fence, so the structured parse failed and the run looked like it did nothing |
| Task complete | The acceptance command failed when run independently |

None of these are exotic. They are the normal failure mode of handing file-writing
work to an autonomous process.

## What taskproof is

A small, mechanical dispatch layer that wraps every agent invocation in
discipline:

- **Independent verification** — the agent's self-report never counts as success.
  The acceptance command from the project registry is run afterwards, by taskproof.
- **Protected paths** — a registry entry can declare paths an agent must not touch.
- **Structured result contract** — a defined output shape, with documented
  degradation for CLIs that cannot produce it.
- **Append-only audit trail** — every dispatch, verification, failure and retry is
  recorded, so "what happened yesterday" is a query, not a memory exercise.
- **Meaningful exit codes** — callers can distinguish "the agent failed" from
  "the agent succeeded but verification failed".
- **No LLM inside** — taskproof does not plan, decompose, or decide. Any agent
  (or a human, or a script) can drive it.

## Shape

```
taskproof run <project> "<task>"     # dispatch, then verify, then record
taskproof tasks / show / log         # inspect state
taskproof board                      # static dashboard snapshot
taskproof api --port 8787            # local read-only REST API for clients
```

- Python, standard library only, `pipx install`-able
- SQLite for state (transactional claims, not lock files)
- JSONL audit stream, write-only, rotated monthly
- Pluggable adapters (codex / claude / gemini / opencode + any command)

## The desktop console

`desktop/` is the stage-2 console: an **Electron + Vue 3** app (Element Plus,
UnoCSS, Pinia, vue-i18n) that renders the same loopback data as the static board,
but live. It is bilingual — zh-CN and en, following the system locale with an
English fallback.

The process model is the interesting part. The app spawns the local service
itself — `taskproof api --port 0` — reads the bound port from the child's stdout,
and terminates the child on exit. Data comes from that loopback, **read-only**
REST API; nothing leaves `127.0.0.1`.

Writes are the one opt-in surface. `taskproof api --port 0 --allow-write` mints a
**session-only token**, printed once to stdout and held in the process's memory —
never written to a file, argv, the environment, or a response, and never handed
to the renderer (the write path stays in the Electron main process). Every write
carries the `expected_hash` it read; if the file changed on disk the write is
refused with **409** and the current content is handed back, so a hand-edited
`projects.toml` is never silently overwritten.

## Registry

Everything taskproof may dispatch is declared in one TOML file in the workspace
(`~/.taskproof/projects.toml`): the path, the concurrency group, and the
acceptance command that has to pass afterwards.

```toml
[[project]]
id   = "my-app"
path = "/absolute/path/to/my-app"
group = "my-app"
verify = "npm run build"    # run by taskproof, after the agent exits
verify_kind = "build"       # check | build | none
```

`taskproof register <path>` appends an entry. See
[`examples/projects.example.toml`](examples/projects.example.toml) for a
commented starting point, and [`docs/REGISTRY.md`](docs/REGISTRY.md) for the
field reference and the list of hard errors.

## Safety and hygiene

- **Protected paths are fingerprinted, not just diffed.** Forbidden paths are
  snapshotted before and after a run, so a change inside `.git/` or an ignored
  build/dependency directory is caught too, not only what `git status` happens to
  report. A tree larger than 20000 entries is sampled, and the audit event records
  `snapshot_truncated: true`.
- **An asset scan runs before every push** (`tools/scan_assets.py`, wired through
  `core.hooksPath`). It ships generic **shape** rules only, so the scanner is
  never a no-op.
- **The organisation-specific words live outside the repository**
  (`~/.taskproof/asset-patterns.txt`, or `$TASKPROOF_ASSET_PATTERNS`). A scanner
  that embedded the names it protects would leak exactly those names.

## The enum contract

Status words, `verify_kind` values and exit-code meanings are one generated
artefact — [`contract/enums.json`](contract/enums.json) — produced from the
Python constants by `tools/gen_contract.py`. The TypeScript side imports it
instead of re-typing it; a status that exists in Python but not in the frontend
is a task that silently vanishes from the board. CI runs the check, so the two
languages cannot drift:

```bash
PYTHONPATH=src python3 tools/gen_contract.py --check
```

## Documentation

The docs ship in pairs, English and Simplified Chinese:

| English | 中文 |
|---|---|
| [`README.md`](README.md) | [`README.zh-CN.md`](README.zh-CN.md) |
| [`docs/DESIGN.md`](docs/DESIGN.md) | [`docs/DESIGN.zh-CN.md`](docs/DESIGN.zh-CN.md) |
| [`docs/REGISTRY.md`](docs/REGISTRY.md) | [`docs/REGISTRY.zh-CN.md`](docs/REGISTRY.zh-CN.md) |
| [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) | [`docs/WALKTHROUGH.zh-CN.md`](docs/WALKTHROUGH.zh-CN.md) |

The dispatch discipline is a skill, in [`skills/taskproof-dispatch/SKILL.md`](skills/taskproof-dispatch/SKILL.md).

## Icon

`docs/assets/icon.png` is a 256 px copy of the app icon, small enough to live in
the repository. The source was an AI-generated mark; the checkerboard that got
baked into the PNG was cut out, the artwork was laid on Apple's 824/1024 grid
(the mark occupies 824 of the 1024 px canvas so the rounded-corner margin is
correct), and `sips` produced the 256 px copy used at the top of this page.

## Non-goals

- No built-in LLM orchestration
- No agent-to-agent conversation layer
- No code generation or editing of its own
- No automated `git` write operations

## Exit codes

Exit codes are part of the contract for callers (scripts, agents, CI): they tell
you *why* a run ended without parsing stdout.

| Code | Meaning |
|---|---|
| 0  | success |
| 2  | registry problem (unknown project, missing/malformed registry, duplicate id) |
| 64 | usage error (bad flags, missing path, unknown task or adapter) |
| 70 | adapter (agent) failure — the CLI failed to run, or its result could not be parsed |
| 71 | verification or artifact self-check failure (acceptance command failed) |
| 75 | concurrency limit reached (same-group busy, or the global cap is full) |

## License

Apache-2.0. See [`LICENSE`](LICENSE).

---

<sub>Also available in [中文](README.zh-CN.md).</sub>
