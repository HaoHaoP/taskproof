# taskproof

A conveyor belt for AI coding agents.

It does not decide *what* to do. It guarantees that whatever gets dispatched is
**independently verified** and **recorded** — so you never have to trust an
agent's own claim that it finished.

**Status: design phase.** No implementation yet. See [`docs/DESIGN.md`](docs/DESIGN.md)
for the full design and the decision log.

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
taskproof board                      # dashboard
```

- Python, standard library only, `pipx install`-able
- SQLite for state (transactional claims, not lock files)
- JSONL audit stream, write-only, rotated monthly
- Pluggable adapters (codex / claude / gemini / opencode + any command)

## Non-goals

- No built-in LLM orchestration
- No agent-to-agent conversation layer
- No code generation or editing of its own
- No automated `git` write operations

## License

Apache-2.0. See [`LICENSE`](LICENSE).

---

<sub>Also available in [中文](README.zh-CN.md).</sub>
