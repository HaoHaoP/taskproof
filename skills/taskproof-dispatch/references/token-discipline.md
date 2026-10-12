# Dispatch economy

Detail behind iron rules 7–11 of [`../SKILL.md`](../SKILL.md). Read it once before you write a card. The point of the whole file is that the main agent spends its context on **judging**, not on re-doing what the machine already did or on restating what the operator already wrote.

## 1. Review: what counts as already proven

The run's own step ⑦ executes the lane's `verify` command with the card's working directory and records the outcome in the ledger (`verify_cmd`, `verify_exit`, `verify_summary`, plus the event stream). That is a machine result **about the code** — not a self-report, and not something you have to reproduce. So split the questions by who can answer them:

| Question | Answered by | What you do |
|---|---|---|
| Does the registered command still pass? | the machine, step ⑦ | read `taskproof show <id>` |
| Was the command run at all? | the machine | `verify_cmd == SKIPPED` → exception 1 below |
| Does the command cover what the card demands? | you | at card-writing time, see section 1.2 |
| Did the worker stay inside the card? | you | read the diff |
| Is it right in a real runtime? | you | one command, one number: re-run the card's `check-*.mjs` / read one value / compare bytes |
| Did a delete keep what should have survived? | you | inventory before and after |
| Is it what the operator meant? | the operator | ask, once, with a recommendation |

**That row has a ceiling — it is not a licence to explore.** Two tiers:

- **Closing tier (you do it):** re-run the card's script, read one value off the page, compare
  bytes/fingerprints — the ceiling is "one command, one number", then report.
- **Exploratory tier (fold it into a card first; do not build it up in-session):** root-causing, hitting the
  intranet backend, hooking XHR, clicking through pages — the first move is to **freeze the probe into the
  project's `check-*.mjs` and put it in the card** (the worker shows red→green; you only re-run that one
  command), or to write a "to-verify list" into the project's progress file before deciding what to fire.
  When it needs a logged-in session, prefer the operator's test token so the worker can run the script.
- **Stop gate:** more than ~10 tool calls, or ~15 minutes, on the same question with no verdict → stop:
  write a card, write a backlog line, or go to the operator (section 4, "don't loop with yourself").

Two facts about the ledger worth knowing before you read it:

- **SKIPPED is not a pass.** A lane with no `verify`, or a card fired with `--no-verify`, records `SKIPPED` — and the card still lands `done`, because nothing failed. Only you can catch that.
- **`blocked` and `failed` are different verdicts.** `blocked` (a forbidden-path breach) did **not** run step ⑦ at all; `failed` means the acceptance really ran and went red.

Re-run `taskproof verify <id>` for exactly three reasons:

1. **SKIPPED** — nothing was exercised. You are the only check there is.
2. **Coverage gap** — the card demands something the command cannot see: a rendered number, a file that must *not* exist, an exit code on a 404 path, a deleted thing staying deleted. Add that assertion yourself, as one command producing one number.
3. **Suspected false green** — a check that structurally cannot fail. Known specimens in this project: `npx eslint <view>` over a path listed in `.eslintignore` (prints "File ignored because of a matching ignore pattern" and exits 0); a test that only asserts a source string (a `toContain('@command="fn(key)"')` assertion cannot see a compile-time problem); `npm run build` succeeding while the target emitted nothing. Each of these has already cost a real card.

A **red** result is the mirror case, and it gets a second look by default: re-run it 2–3 times in the same tree before you accept it as a defect — a machine running several lanes makes polling/timeout tests flaky, and one such false red has cost a whole rework cycle. When it really is red, fix it in the tree rather than re-firing the whole card.

### 1.2 Write the acceptance command so it can actually go red

The review only gets cheaper if the command is load-bearing. So:

- one command, one judgement: `exit 0` means the card's demands are met;
- name the specific test or target when the card closes one root cause (section 3), rather than the whole universe;
- keep it identical to `verify` in the registry — a card whose acceptance command says something else is a defect;
- run it by hand once on a clean tree before firing: it must be **green** there. A command that is red on a clean tree makes every card on that lane fail, and a command that is green before the card ever fires was never checking the card.

## 2. Source material: attach by path, never by paraphrase

The card body *is* the worker's prompt — it is passed as one argv element. So anything you can point at, point at:

````
## 素材（自己读，不要我复述）
- 原型：/absolute/path/to/prototype/viewer.html:1710-1735
- 设计口径：/absolute/path/to/design/taskgroup.md 第 3 节
- 上次的真实输出：/absolute/path/to/logs/board.html
````

Rules:

- absolute path **plus line range**; a path that only exists in your head is a paraphrase;
- one explicit line — *read it yourself, do not ask me to restate it*;
- the worker can read outside the repository: the codex adapter runs `-C <workdir> --sandbox workspace-write`, which restricts **writes**, not reads;
- when the material is a picture the worker cannot see, describe only what the pixels decide (dimensions, colours, spacing) and cite the `file:line` of the component it must match;
- **do not** re-explain the design in your own words "to be safe". That is where precision dies, and it costs twice: once to compress it, once to repair the misreading;
- keep the material somewhere stable — the project's own `docs/` or `prototypes/` — not in `/tmp`, which another task is free to clean.

## 3. TDD in the card

Two shapes, chosen by whether the work changes behaviour.

**Behaviour change or bug fix → the test is named in the card.** The acceptance command names one test per root cause:

```bash
cd /absolute/path/to/repo && python -m unittest tests.test_cli.TestDispatch.test_refuses_full_cap -v && python -m unittest discover -s tests
```

Why it is shaped like that: taskproof judges by exit code, so "this test must fail first" cannot itself be the acceptance (writing it as `! cmd` is a riddle the worker will solve wrongly). Naming the test makes its **existence** machine-decided — a test that was never written is a red run, not a silent pass — and the name tells the operator which root cause the card closed. The worker's delivery then pastes **the failing run it saw before the fix**; you are checking that a red existed, not re-deriving it.

**No behaviour change → a separate test-only card.** Writing tests for code that already exists, or netting a refactor before it, is its own card: acceptance is the new tests green plus the whole suite green, and the hard constraint is "no production file may change" — state that in the card and back it with `forbidden_paths` where the lane allows. Name the `tdd` skill by path (`~/.codex/skills/tdd/SKILL.md`) so the worker does not guess what TDD means to you.

Do **not** split every card into "test card then code card": that is two dispatches, two reviews and two commits for one root cause. Split only when the test work stands on its own.

## 4. Closure rework, backlog, and the human gate

The failure mode this section exists to stop: the main agent finishes a card, notices three more things, and dispatches three more cards — each burning context, review time and a commit boundary, none of them asked for. The rule that gives it a boundary: **a card is either a closure rework or an operator decision.**

- **Closure rework — free, once.** Acceptance went red, or the diff does not actually close the root cause. Diagnose it yourself first: the card may have been wrong, not the worker. One more card on that same root cause needs no permission. If it goes red the same way a second time, stop and put the question to the operator instead of firing a third.
- **Backlog — everything else.** A second bug, a smell elsewhere, a missing test, a nicer refactor, an inconsistency you tripped over: one line into the `backlog.md` next to that project's cards — `what · where (file:line) · why it is not this card`. No card, no dispatch. Bring the whole file to the operator in one batch, with a recommendation per line.
- **Human gate.** Any card that is not a closure rework needs the operator's explicit nod. Ask one question at a time, each with a recommendation — a form with several questions in it tends to come back unanswered.
- **Human-first by default.** These should never become a card at all: visual feel ("does it look right"), product trade-offs, data-accuracy questions, "is this what I meant". Start the service, hand over the URL plus one line saying what to look at, and let the answer decide whether a card exists. It costs one message and saves a whole dispatch round-trip.
- **No loop with yourself.** "Verify → decide something is wrong → dispatch" repeating more than once on the same subject is the runaway, not diligence. The second time it happens, write it down and go to the operator.

## 5. Model downgrade

Two levels, decided per card.

**Level 1 — `--reasoning none`, and `--model <cheap>` when a cheap model is configured.** Legal when the card is enumerable and machine-checkable:

- documentation mirroring (a zh file and its en counterpart must say the same thing)
- one-off renames, path substitutions, reference sweeps
- mechanical reformatting, list and manifest generation, counting
- copying the shape of an output that already exists (a table row, a JSON field, a config block)

Two questions decide it: can you write the acceptance command without re-reading the code twice? And if the worker fails, is the failure legible from the diff alone? Two yeses → downgrade. Anything needing judgement across files (architecture, a gate's semantics, UI geometry) stays on the normal model.

**Level 2 — a local model**, reached with `custom:<cmd>` pointing at a local server, or a local provider in the codex config. Same subset as level 1, plus:

- **its own exclusive `group`** — a local server serialises anyway, so an exclusive lock makes that explicit instead of showing up as a mysteriously slow lane;
- never inside a parallel wave: one lane, one card at a time, other lanes idle;
- start with one trial card of the documentation-mirroring kind, and read its diff before you trust the lane with anything else.

State of this machine: `--reasoning none` works today. A local **chat** model is not ready — LM Studio's `http://127.0.0.1:1234/v1/models` serves only `text-embedding-nomic-embed-text-v1.5`. When one is loaded, wire the lane, then run the trial card.

## 6. Writing cards cheaply

- Fill `../templates/card.md` / `../templates/card.zh-CN.md`; do not free-write a long briefing. A card that needs three paragraphs of background is a card that has not decided what it wants.
- One root cause, one file range, one acceptance command, one commit boundary.
- No prose the worker cannot act on: no "please be careful", no history of the investigation, no summary of the conversation so far.
- Keep the constraints you will actually check; each one costs the worker a read, and the rest is noise that invites it to wander.
- Keep the card file inside the project's cards directory, so the paths in the card and the worker's working directory are talking about the same tree.
