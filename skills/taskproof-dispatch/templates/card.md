# <CARD-ID> · <what this card does, in one line>

<!-- Copy this file, fill every section, delete the comments.
     An empty section is a card defect, not a style choice: a missing source-material
     line sends the worker guessing, a missing constraint invites it to wander.
     Keep the card under one root cause, one file range, one acceptance command.
     A card whose result a human will look at is a VISUAL CARD — see
     ../references/visual-cards.md. It fills region, ONE reference header, the status
     truth table and the red-to-green probe, and it may not fire without a valid
     reference. A card that is not visual fills no headers at all. -->

region:   <region slug, e.g. header-buttons; optional with 参照物:, `none` = not counted>
口径:     <reference is a STORE (mutable — you owe it a write-back): /abs/path.md#anchor>
参照物:   <reference is IMMUTABLE: /abs/prototype.html:1028-1066, or screenshot:/abs/shot.png>
<!-- 口径: and 参照物: are alternatives — fill exactly ONE of the two, delete the other. -->

## Root cause
- `path/to/file.py:88` — the one defect this card closes, stated as a fact.
- <!-- visual card only: the root cause is the DELTA between what renders now and the
     reference. The operator's own words go into the store, never into the card. -->

## Source material
<!-- Absolute path + line range, and one line telling the worker to read it itself.
     Never paraphrase the operator's prototype/spec/design doc into your own words. -->
- prototype: `/absolute/path/to/prototype/viewer.html:1710-1735`
- spec: `/absolute/path/to/design/notes.md` section 3
- Read them yourself; do not ask me to restate them.
- <!-- visual card only, exactly one: --> reference: `…` (prototype range | existing
  implementation range | signed-off comparison page | circled screenshot + measured values)

## Status truth table
<!-- Visual card only; otherwise write "not applicable".
     Rows = every state that can exist (tab × edit/view × selected/none × with-data/without).
     Columns = the elements. Cells = shown / hidden / position + the file:line that decides it.
     An empty cell is an unspecified state and comes back as a rework. -->

| state | element A | element B | element C |
|---|---|---|---|
| | | | |

## Red-to-green probe
<!-- Visual card only. One assertion, real browser, RED before the fix, green after.
     It measures numbers, not appearances: element counts, getComputedStyle values,
     offsetWidth, elementFromPoint, class names, aria-expanded, location.hash. -->
- red before the fix: `<command / probe>`
- human eye (cannot be moved to the machine): <one line, be honest>

## Work
- Only `path/to/file.py` and `tests/test_...py`. Close the root cause above; change nothing else.

## Docs the card makes false
<!-- Always filled in on a behaviour card: which sentences, in which file:line, stop being true
     once this lands? Name them, and let the worker fix them in the same card (list those files
     in the allowed-to-change line under Work). Write "none" when there are none. Cross-feature
     diagrams that need a redraw can wait for one final pass — but "none" and "never thought
     about it" are not the same answer. -->
- `docs/REGISTRY.md` gains a row (both languages, never just one)

## Test
<!-- Behaviour change or bug fix: one test per root cause, named in the acceptance
     command below. No behaviour change: say so, mark this a test-only card, and make
     "no production file may change" a hard constraint. -->
- new test: `tests.test_cli.TestDispatch.test_refuses_full_cap`

## Acceptance
```bash
cd /absolute/path/to/repo && python -m unittest tests.test_cli.TestDispatch.test_refuses_full_cap -v && python -m unittest discover -s tests
```
<!-- One command; exit 0 means the card is met. Identical to `verify` in the registry.
     It must be green on a clean tree before you fire, and it must be able to go red.
     A card that MUST write files adds a did-it-land check, so "nothing changed, verify
     green" cannot pass: git diff --quiet -- <file> && exit 1 -->

## Hard constraints
- Only the files named above; no `git add` / commit / push.
- No new dependencies, no build-config changes.
- <project-specific: no `npm install`, nothing under `~/.taskproof/`, …>

## Delivery
- The list of changed files.
- The failing run you saw before the fix.
- The raw output of the acceptance command.
- <!-- visual card only: --> for every colour/size you set, the line in the reference it came from.
- <one line per fact the next card or the operator needs>
