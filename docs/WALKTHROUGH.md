# From zero

A complete pass over taskproof on a throwaway example. Every command below was
run as written and the output is copied from that run.

The example is deliberately LLM-free: a shell script stands in for the agent, so
nothing here needs an API key or a coding CLI. That also makes the second half
honest, because the thing it demonstrates -- an "agent" that reports success
without doing the work -- is what taskproof exists to catch.

## 1. Install

```bash
pipx install taskproof
```

From a checkout instead:

```bash
pip install -e .
```

## 2. Create a workspace

```bash
taskproof init
```

```
initialised workspace: /tmp/tp-walkthrough/workspace
  registry: /tmp/tp-walkthrough/workspace/projects.toml  (no projects yet)
next:
  taskproof register <path>         # probe and register a repository
  taskproof run <project> "<task>"  # dispatch, verify, record
  taskproof board --open            # live dashboard (serves + opens a browser)
  taskproof board --out board.html  # static snapshot (does not auto-refresh)
  registry format                   # examples/projects.example.toml
```

The workspace defaults to `~/.taskproof`; `--workspace` (or `TASKPROOF_HOME`)
moves it.

The registry is created with the `[defaults]` table and no projects. Nothing here
is a placeholder pointing at a path that does not exist -- entries arrive through
`register` (next section), so `taskproof projects` is empty until you add one.

## 3. Register a repository

```bash
taskproof register /tmp/tp-walkthrough/demo-library --group demo
```

```
project: demo-library  (/tmp/tp-walkthrough/demo-library)
group:   demo
verify:  (none inferred — set one by hand)
hint:    you may add an AGENTS.md to describe the repo to agents
```

`register` probes the repository and appends an entry. It does **not** invent an
acceptance command: a guessed one would make verification look stronger than it
is, so when it cannot infer a command it says so instead of picking one.

## 4. Declare the acceptance command

This is the part that decides what "done" means. In the workspace's
`projects.toml`:

```toml
[defaults]
concurrency = 3   # global cap on simultaneous tasks
timeout = 1800    # seconds before a task is judged stuck

[[project]]
id = "demo-library"
path = "/tmp/tp-walkthrough/demo-library"
group = "demo"
verify = "sh check.sh"
verify_kind = "check"
result_schema = "none"
```

`verify` is run by taskproof **after** the agent process has exited, in the
project path. Nothing the agent says about its own work is evidence.
`result_schema = "none"` turns structured output off: an arbitrary command has no
schema convention, so it would degrade to plain text anyway.

The field reference is in [`REGISTRY.md`](REGISTRY.md).

```bash
taskproof projects
```

```
ID                   GROUP          PROBE   TASKS ACTV FAIL LAST ACTIVITY             VERIFY
demo-library         demo           -           0    0    0 —                         sh check.sh
  path: /tmp/tp-walkthrough/demo-library
```

## 5. Dispatch a task

`custom:<command>` runs any command as the agent. Here a script stands in for a
real one:

```bash
taskproof run demo-library "add an add() function to src/lib.py" --adapter "custom:sh fix.sh"
```

```
t-20261008-001  done  demo-library
```

Exit code 0. Notice what decided that: not the script's opinion of itself, but
`sh check.sh`, which taskproof ran afterwards on its own.

## 6. Watch it lie

Same project, an "agent" that reports success and changes nothing:

```bash
taskproof run demo-library "make the acceptance command pass" \
  --adapter "custom:echo All done! Tests pass, verified in browser."
```

```
taskproof: acceptance command failed (exit 1)
  hint: output: FAIL: add() is missing
```

Exit code **71**. That is "the agent ran fine but verification failed", which is
deliberately a different outcome from "the agent failed" (70) -- callers can tell
the two apart without parsing output.

## 7. Inspect

```bash
taskproof tasks --all
```

```
作用域: 全部 1 个项目（来自 --all）

# demo-library (2 个任务)
    ID                 STATUS     PROJECT          BRIEF
    t-20261008-001     done       demo-library     add an add() function to src/lib.py
    t-20261008-002     failed     demo-library     make the acceptance command pass
```

```bash
taskproof show t-20261008-001
```

```
id:       t-20261008-001
project:  demo-library
status:   done
adapter:  custom:sh fix.sh
brief:    add an add() function to src/lib.py
verify:   sh check.sh (exit 0)
workdir:  /tmp/tp-walkthrough/demo-library
```

```bash
taskproof log t-20261008-001
```

```
started        {"project": "demo-library", "group": "demo", "adapter": "custom:sh fix.sh", ...}
result_schema  {"enabled": false, "path": null, "note": "structured result disabled ..."}
adapter        {"exit_code": 0, "degraded": true, "summary": "wrote src/lib.py"}
verify         {"status": "PASSED", "ran": true, "exit_code": 0, "note": "", "output_tail": "ok"}
done           {"verify": "PASSED", "files_changed": 1, "summary": "wrote src/lib.py"}
```

Timestamps trimmed for width. The stream is append-only, and the verdict on the
last two lines was written by taskproof, not reported by the agent.

## 8. Re-run acceptance

```bash
taskproof verify t-20261008-002
```

```
t-20261008-002  verify: FAILED  exit=1
```

## 9. The dashboard and the API

```bash
taskproof board --open             # live board, blocks, serves on 8787
taskproof board --out board.html   # standalone snapshot, no auto-refresh
taskproof api --port 8787          # read-only REST for clients
taskproof api --port 0             # bind a free port and print it
```

`api --port 0` prints exactly one line before it starts serving:

```
taskproof api listening on http://127.0.0.1:61071
```

That line is how the desktop app in `desktop/` learns which port it was given.

## Things that surprise people

**`custom:` never spawns a shell.** The template is split with shell-style
quoting and the placeholders are substituted per token, so nothing is
re-interpreted afterwards:

```
custom:sh fix.sh                 # fine: two argv elements
custom:sh -c printf '...' > x    # the > is passed as a literal argument
```

Put the logic in a script rather than trying to write shell in the template.

**A silent command is a failed adapter.** There is no structured-output
convention for an arbitrary command, so taskproof parses whatever it printed. If
it printed nothing there is nothing to parse, and the run ends as an adapter
failure (70). Have the command say something.

**`--json` is a global flag** and goes *before* the subcommand:
`taskproof --json tasks --all`, not `taskproof tasks --all --json`.

**A failed run is not a rollback.** A dispatch that ends in failure has already
modified the working tree; the exit code tells you the outcome, not what is on
disk now. That is what `forbidden_paths` and `--worktree` are for.

**`verify_kind = "none"` records SKIPPED, never "passed"** — see
[`REGISTRY.md`](REGISTRY.md).

---

<sub>Also available in [中文](WALKTHROUGH.zh-CN.md).</sub>
