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

## Install

Two ways in: the desktop console if you do not write code, the command line if
you do.

### Desktop console

Download the installer for your platform from the
[GitHub Releases](https://github.com/HaoHaoP/taskproof/releases) page:

- macOS arm64 (Apple silicon) — `.dmg`
- Windows x64 — `.exe`
- Linux x64 — `.AppImage` / `.deb`

The installers are **not signed and not notarised**:

- **macOS is arm64 only** (no Intel or Rosetta build): on first launch,
  right-click the app → Open, or run
  `xattr -d com.apple.quarantine /Applications/Taskproof.app`.
- **Windows 10+**: SmartScreen shows a warning on first launch.

Minimum versions are macOS 11+, Windows 10+, or a current mainstream Linux
distribution. Each installer **ships its own Python runtime**, so there is
nothing to `pip install` — but it does need a system **`git`** for worktrees and
the protected-path gate. Without git the settings page says so, and everything
else keeps working.

### Command line

```bash
pipx install git+https://github.com/HaoHaoP/taskproof
```

Or download the wheel from the same Release and install the local file:

```bash
pipx install ./taskproof-0.1.0-py3-none-any.whl
```

Or run from a source checkout:

```bash
pip install -e .
```

**There is no `taskproof` package on PyPI.** Do not look for it there; use one of
the three installs above.

## Run a task

```bash
taskproof init
taskproof register /absolute/path/to/your/repo
taskproof run <project> "fix the failing test"
```

`run` is the whole lifecycle in one line: it **dispatches** the card to a
pluggable adapter (codex / claude / gemini / opencode, or `custom:<cmd>`), then
**independently runs the acceptance command** from the registry once the agent
exits, and finally **records** every step in the audit ledger. The agent's own
"done" is never the verdict.

`taskproof tasks` lists what is in flight; `taskproof show <id>` and
`taskproof log <id>` read one card back.

The desktop console shares the same ledger. On first launch it creates
`~/.taskproof` as an **empty workspace** — a `[defaults]` table and a commented
example, with **no sample projects and no sample tasks** — and the board's empty
state points you at the Projects page (or `taskproof register <path>`). Because
the console and the CLI read the same `~/.taskproof`, either one sees the other's
cards.

[`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) runs this end to end on a throwaway
example — including the case where the agent reports success and the acceptance
command disagrees.

---

## Dispatching work

The usage this project is extracted from is a *discipline for the agent that
hands out the cards*, and it now ships in the repository as a skill:

```
skills/taskproof-dispatch/SKILL.md
skills/taskproof-dispatch/SKILL.zh-CN.md
```

It is the **operating manual for an AI coding agent** — the orchestrating one
that plans the work, registers the repositories, writes each card, and dispatches
it to a worker. Taskproof itself does not plan anything (see Non-goals); this
skill is the missing half: how to drive the tool without the failure modes the
hard way. Both languages ship: `SKILL.md` (English) and `SKILL.zh-CN.md`
(简体中文).

The rules in it are not invented; each is a lesson from breaking something.
`pkill -f` is the classic one, for instance: a card is passed as process argv, so
the pattern also matches the dispatcher itself and kills the run — exactly the
kind of practical rule the skill exists to record. It turns the
lessons of this build into steps you can copy: register a project,
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

## The concurrency cap

The global cap is workspace-level and is always reported as a **value plus where
it came from**, never a bare number. It has three sources, in precedence order:

1. `run --cap N` — a one-off for this dispatch only, never persisted;
2. `[defaults] concurrency` in the registry;
3. auto-detected from the machine.

The auto fallback is deliberately conservative — one slot is a whole extra
coding agent:

```
cap = clamp(2, cores // 4, 6)     # at most one slot per four cores
if RAM < 8 GiB: cap = 2           # a small box cannot afford cores // 4
if the core count is unknown: cap = 3
```

Inspect the effective value and its source:

```bash
taskproof config --show
```

Change the persisted value, comment-preserving:

```bash
taskproof config --concurrency N
```

`run --cap N` overrides it for one dispatch only. **Lowering the cap is not
retroactive**: it never touches a card already running — the CLI prints the cards
that now exceed the new cap and leaves the decision to you.

## Terminal states and the two gates

Two terminal states are deliberately different:

- **`blocked`** — a boundary breach: the run touched a path the registry forbids.
  The acceptance may even have passed; the gate is what stopped it.
- **`failed`** — the acceptance ran and went red, or the adapter itself failed;
  the work went wrong.

Both are cleared by `accept`, which is a human registration, not a fresh verdict:

```bash
taskproof accept <id>                 # blocked: a note is optional
taskproof accept <id> --note "why"    # failed: a note is required
```

`accept` **never re-runs acceptance and never rewrites the recorded verdict** —
the run's own facts stay authoritative. Closing a `failed` card requires a note,
because that is a human sign-off and the reason has to survive in the ledger.
`taskproof rerun <id>` starts a fresh card from a terminal one and links the two
both ways (`rerun_of` / `rerun_as`).

On the board, `blocked` gets its own **Needs review** column, kept out of the
failure column.

## The desktop console

`desktop/` is the stage-2 console: an **Electron + Vue 3** app (Element Plus,
UnoCSS, Pinia, vue-i18n) that renders the same loopback data as the static board,
but live. It is bilingual — zh-CN and en, following the system locale with an
English fallback.

The process model is the interesting part. The app spawns the local service
itself — `taskproof api --port 0` — reads the bound port from the child's stdout,
and terminates the child on exit. Data comes from that loopback, **read-only**
REST API; nothing leaves `127.0.0.1`.

The REST surface is **read-only**. Every mutation lives in the CLI — registering
a project, editing its registry entry, dispatching, cancelling, accepting and
removing. The API itself only serves reads: it mints no session token and exposes
no write endpoint, so a write-shaped request to an old path is a plain **404**.

What the console does today:

- **Columns** — running / verifying / done / cancelled / needs review / not
  passing. A column header can be hidden with the `?hide=` query parameter.
- The **finished columns fold** to the most recent cards, with a bar to reveal
  the rest.
- A **"acceptance passed"** badge on a blocked card whose acceptance went green.
- **Writes are CLI-only.** The console is a viewer over the read-only API:
  dispatch, accept and registry edits all go through `taskproof`, never the UI.
- A settings page that shows the **effective cap and where it came from**, plus
  the resolved launcher (bundled runtime / `taskproof` on PATH / a custom
  command).
- A **tray icon**, a **Dock badge** (the not-passing count) and a
  **launch-at-login** switch.

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

## Development

Run the CLI from a source checkout:

```bash
pip install -e .
taskproof --version
```

Or, without installing:

```bash
PYTHONPATH=src python3 -m taskproof doctor
```

Two test suites, both green at the time of writing:

- **Python** — `PYTHONPATH=src python3 -m unittest discover -s tests` (448 tests).
- **Desktop** — `cd desktop && npm install && npm test` (258 tests). `npm run
  build` runs the type-check and a production build of all three targets.

CI runs three checks: the asset scan (`tools/scan_assets.py`), the enum-contract
consistency check (`PYTHONPATH=src python3 tools/gen_contract.py --check`), and
the desktop build + tests.

## Known limitations

- **Unsigned and not notarised.** macOS shows a Gatekeeper prompt on first launch
  (right-click → Open, or clear the quarantine bit); Windows shows a SmartScreen
  warning.
- **macOS is arm64 only.** There is no Intel build and no Rosetta path.
- **The gate needs `git`.** Without a system `git`, worktrees and the
  protected-path gate are unavailable; the settings page says so and everything
  else runs as usual.
- **The board fetches at most 2000 rows at a time.** At that ceiling it shows
  **"fetch limit reached"** rather than implying it has everything.
- **Windows and Linux installers are built by CI's native runners.** A local
  machine can only build the macOS package.

## Documentation

The docs ship in pairs, English and Simplified Chinese:

| English | 中文 |
|---|---|
| [`README.md`](README.md) | [`README.zh-CN.md`](README.zh-CN.md) |
| [`docs/DESIGN.md`](docs/DESIGN.md) | [`docs/DESIGN.zh-CN.md`](docs/DESIGN.zh-CN.md) |
| [`docs/REGISTRY.md`](docs/REGISTRY.md) | [`docs/REGISTRY.zh-CN.md`](docs/REGISTRY.zh-CN.md) |
| [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) | [`docs/WALKTHROUGH.zh-CN.md`](docs/WALKTHROUGH.zh-CN.md) |

The dispatch discipline is a skill, in [`skills/taskproof-dispatch/SKILL.md`](skills/taskproof-dispatch/SKILL.md) (English) and [`skills/taskproof-dispatch/SKILL.zh-CN.md`](skills/taskproof-dispatch/SKILL.zh-CN.md) (简体中文).

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
