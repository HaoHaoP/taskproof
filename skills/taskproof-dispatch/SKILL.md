---
name: taskproof-dispatch
description: Use when a main agent dispatches coding cards to worker agents through taskproof and must follow the dispatch discipline — register projects, fire cards in parallel by default, read status and logs, kill by PID, and re-verify results objectively instead of trusting the worker.
---

# Dispatch work with taskproof

`taskproof` does not decide *what* to do; it only guarantees that work it dispatched is **independently verified** and **recorded**.
This skill is the operating manual for the **main agent** (the one that dispatches): one card at a time, every card carries a root cause and acceptance criteria, and after firing you re-verify yourself instead of trusting the worker's self-report.

Commands are always a single copy-pasteable line. Example paths are always written `/absolute/path/to/repo`.

## 0. Iron rules

1. One card does one thing; the card body must name the root cause as **file:line**, never "go find it yourself".
2. Put the acceptance command in the card body, and keep it consistent with `verify` in the registry.
3. The worker only implements and **does not commit**; `git add` / commit / push are the main agent's job.
4. Same group is serial, different groups are parallel — the criteria are in section 6; everything else is **parallel by default**.
5. **Kill by PID**, never `pkill -f` (section 7).
6. For UI verification use only a one-off profile under `/tmp` plus a one-off workspace; **never write to the real registry** (section 8).
7. The main agent **re-runs acceptance itself** and makes its own objective assertions; the worker's self-report is not a conclusion (section 9).

## 1. Register a project

```bash
taskproof init
taskproof register /absolute/path/to/repo
taskproof register /absolute/path/to/repo --id my-repo --group my-repo
taskproof --json register /absolute/path/to/repo --dry-run
```

`register` probes the repository and appends a `[[project]]` entry (`--dry-run` probes only and writes nothing; `--json` is a root-level switch and must come **before** the subcommand). The registry defaults to `~/.taskproof/projects.toml`; `--workspace <dir>` points it elsewhere.

Fields are defined by `docs/REGISTRY.md`:

| Field | Required | Default | Notes |
|---|---|---|---|
| `id` | yes | — | Unique; a duplicate is a hard error |
| `path` | yes | — | Must be an absolute path |
| `group` | no | `"default"` | Concurrency group, see section 6 |
| `aliases` | no | `[]` | Aliases, accepted wherever an id is accepted |
| `verify` | no | — | Acceptance command, run by taskproof after the agent exits |
| `verify_kind` | no | `"none"` | `check` / `build` / `none` |
| `forbidden_paths` | no | `[]` | Prefixes the agent must not touch; a trailing `/` covers the whole directory tree |
| `result_schema` | no | `"default"` | `default` / `none` / an absolute path to a JSON Schema |

Semantics to remember:

- `group` is a **serialisation key, not a label**. One task per group runs at a time; different groups run in parallel up to `[defaults] concurrency`. Omitting `group` lands you in `default`, so everything that omits it piles into one lane.
- A missing `verify` is not "passed", it is **SKIPPED**.
- `forbidden_paths` is checked after the run, and does not rest on `git status` alone — `.git/` and ignored build output count too; touching them fails the task.
- The gate ignores Python byte-code (`__pycache__` segments, `.pyc` / `.pyo`) because it is a byproduct of running the tool, not authored work — but that is not a licence to litter. **When you run Python inside a card's worktree, use `python3 -B` (or `export PYTHONDONTWRITEBYTECODE=1`)**, or build data with the main-tree / pipx package instead of importing from the worktree. Belt and suspenders, not a replacement for the gate.
- A type prefix is not an exception: `presence:` adds a *weaker* observation for its own rule and never cancels a `file` or directory rule that also covers the path. In particular `presence:t/__pycache__/` does **not** exempt byte-code from a `t/` rule.
- One repository can be registered under several entries: e.g. `taskproof` pointing at the repository root and `taskproof-desktop` at the `desktop/` subdirectory, so cards in different directories can fire at the same time.

## 2. Write the card to a file

The card body lives in a file and is passed with `$(cat ...)` at fire time — this avoids shell escaping and keeps the card reusable and archivable.

````bash
mkdir -p /tmp/cards
cat > /tmp/cards/tp-card19.md <<'CARD'
# TP-card19 · 一句话说明这张卡做什么

## 根因
- `src/taskproof/cli.py:88` 在 X 情况下返回了错误的退出码。

## 要做的事
- 只改 `src/taskproof/cli.py`，修掉上面这一处。

## 验收
```bash
cd /absolute/path/to/repo && python -m pytest -q
```

## 硬约束
- 只改上面点名的文件；不 `git add` / commit / push。

## 交付
- 改动文件清单 + 验收命令的真实输出。
CARD
````

## 3. Look at in-flight state before firing

```bash
taskproof tasks --all
taskproof --json tasks --all
```

`tasks --all` ignores the cwd scope and lists every project; `--json` is for machines. Before firing, check how many are running; if you are within the concurrency cap, send the independent work out together.

## 4. Fire

```bash
taskproof run my-repo --adapter codex --timeout 1800 "$(cat /tmp/cards/tp-card19.md)"
```

- `--adapter`: `codex` / `claude` / `gemini` / `opencode` / `custom:<cmd>`.
- `--timeout`: seconds; overrides `[defaults] timeout` in the registry.
- Card in a file, passed with `$(cat ...)`: saves escaping, and makes backup and re-runs easy.

## 5. Check status and read logs

```bash
taskproof tasks --all
taskproof --json tasks --all
taskproof show <task-id>
taskproof log <task-id>
taskproof log <task-id> --follow
```

`log` prints the task's full event stream; `--follow` follows it all the way to the terminal state.

## 5.1 Human sign-off: `accept`

`accept <id>` is how a human closes a card the pipeline stopped on its own. It is a **registration, not a verdict**.

- It never re-runs acceptance and never rewrites `verify_*`: the acceptance result stays authoritative and the registration rides alongside it.
- `blocked` (a forbidden-path breach): `accept <id>` clears it, note optional — green acceptance -> `done`, red or skipped -> `failed`.
- `failed` (acceptance went red, or the adapter failed): `accept <id> --note "…"` clears it to `done`, but the note is **required** — an empty or missing note is refused (CLI `rc != 0`, HTTP `400`). The note records *why* the failure was judged a false red; it is not a substitute for the run's own `verify_*`.
- `done` / `timeout` / `cancelled` and every non-terminal state are refused.

## 6. Parallel scheduling: parallel by default

**Parallel is the default — do not serialise out of habit.** Before firing:

1. Look at `group` first: **tasks in different groups should be fired at the same time**. Registering one repository under several entries exists for exactly this — as long as the file ranges do not overlap, dispatching them together is safe and is the main lever for cutting total time.
2. The **global cap** is workspace-level and is always shown together with its **effective value and where it comes from** — `auto` (machine-detected), `toml` (`[defaults] concurrency`), or `cli` (a one-off `run --cap N`). Ask with `taskproof config --show` (or `taskproof doctor`) instead of assuming a number: a fresh workspace carries no key and auto-detects `clamp(2, cores // 4, 6)`, or 2 when RAM < 8 GB. Count how many are running with `taskproof tasks --all` first; if you are within the cap, fire the independent work together, and do not blindly fire until the slots are full. Change the persisted value with `taskproof config --concurrency N` (comment-preserving, non-retroactive); raise it for a single dispatch with `run --cap N`.
3. **Park new cards by default: `taskproof run --park`** (bare `--park` appends at the tail wave = current max `queue_seq` + 1; `--park=N` pins wave `N`). Cards that share a `queue_seq` are **one wave**, and a wave advances only once every lower-numbered wave has drained. **One group still runs at most one task at any moment**: a same-group card that is refused (exit 75) **falls back to `queued` and is never dropped**, then is retried on a later tick. **Who advances the queue is your choice**: the resident `taskproof queue` daemon (unattended continuous push) or a human `taskproof advance <id>`. Prefer `advance` when you need to keep the per-card commit boundary — the resident daemon starts the next card before the previous one is committed, and the two cards' diffs will blur together.
4. The only legitimate way to run within one group in parallel: register another project entry pointing at a **worktree**, give it a different group name, and pass `--worktree` at run time; do this **only for cards whose file ranges do not overlap** — the main agent merges both diffs back into the main tree afterwards in one batch.
5. Therefore **there is exactly one criterion for serialising: the same group and overlapping file ranges**. Every other case should run in parallel.
6. Batch the main agent's own rhythm too: collect reviews and commits and do them together; do not let "wait for me to commit" become the metronome for the whole chain.

## 7. Killing processes: by PID

```bash
taskproof --json tasks --all      # find the task's pid
kill <pid>
```

**Never `pkill -f`.** The card body is passed to `taskproof run` as argv, so any string that appears in the card (for example `--remote-debugging-port=9333`) is on the firing process's own command line, and `pkill -f` kills the fire along with it — the symptom is exit -15, no task created, an empty log.

## 8. UI verification: a one-off profile + a one-off workspace

A dispatched UI card must be verified in a one-off environment that writes state to `/tmp`, never to the real registry:

```bash
taskproof --workspace /tmp/tp-verify-$$ init
taskproof --workspace /tmp/tp-verify-$$ register /absolute/path/to/repo --id verify-repo --group verify-repo
```

**Never write `~/.taskproof/projects.toml`.** A real delete/change test destroys the user's registry entries — in this development a worker once ran a delete test against the real registry and removed one of the user's projects.

## 9. Main agent review checklist

A worker reporting done, or verification showing PASSED, does not count. The main agent walks every line itself:

- [ ] **Re-run the acceptance command yourself** and paste the real output (aligned with the one in the card body).
- [ ] **Make your own objective assertions**: for a real window use something like `document.elementFromPoint(...)`; for a real file use `ls -l`, `python -c "from PIL import Image; ..."`; never accept the worker's written conclusion.
- [ ] `git add` **only the files this card names**; do not wrap unrelated changes in.
- [ ] Confirm the worker did not commit (commits are the main agent's job).
- [ ] Batch reviews and commits; do not turn them into a synchronisation point per task.

## 10. References

- Registry fields and hard errors: [`docs/REGISTRY.md`](../../docs/REGISTRY.md)
- Design decisions: [`docs/DESIGN.md`](../../docs/DESIGN.md)
- A full from-zero-to-one-dispatch walkthrough: [`docs/WALKTHROUGH.md`](../../docs/WALKTHROUGH.md)
- Exit codes: 0 success / 2 registry problem / 64 usage error / 70 adapter failure / 71 verification failure / 75 concurrency limit
