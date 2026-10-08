# taskproof

A conveyor belt for AI coding agents.

It does not decide *what* to do. It guarantees that whatever gets dispatched is
**independently verified** and **recorded** — so you never have to trust an
agent's own claim that it finished.

**Status: stage 1 is usable.** The engine, CLI, a static board and a local
read-only REST API are implemented. See [`docs/DESIGN.md`](docs/DESIGN.md) for
the full design and the decision log.

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
