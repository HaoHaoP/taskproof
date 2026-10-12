# <CARD-ID> · <what this card does, in one line>

<!-- Copy this file, fill every section, delete the comments.
     An empty section is a card defect, not a style choice: a missing source-material
     line sends the worker guessing, a missing constraint invites it to wander.
     Keep the card under one root cause, one file range, one acceptance command. -->

## Root cause
- `path/to/file.py:88` — the one defect this card closes, stated as a fact.

## Source material
<!-- Absolute path + line range, and one line telling the worker to read it itself.
     Never paraphrase the operator's prototype/spec/design doc into your own words. -->
- prototype: `/absolute/path/to/prototype/viewer.html:1710-1735`
- spec: `/absolute/path/to/design/notes.md` section 3
- Read them yourself; do not ask me to restate them.

## Work
- Only `path/to/file.py` and `tests/test_...py`. Close the root cause above; change nothing else.

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
     It must be green on a clean tree before you fire, and it must be able to go red. -->

## Hard constraints
- Only the files named above; no `git add` / commit / push.
- No new dependencies, no build-config changes.
- <project-specific: no `npm install`, nothing under `~/.taskproof/`, …>

## Delivery
- The list of changed files.
- The failing run you saw before the fix.
- The raw output of the acceptance command.
- <one line per fact the next card or the operator needs>
