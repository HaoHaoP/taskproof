# Visual cards

Detail behind iron rules 12–14 of [`../SKILL.md`](../SKILL.md). Read it before you write a card whose result a human will *look at* — layout, colour, size, position, visibility, copy.

The failure this file exists to prevent: a card that describes a **symptom**, gets accepted by a machine that can only check "it builds", and comes back as a rejection. Sixteen cards can pass with `verify exit=0` while the operator rejects fifteen of them, one round trip each. The worker was not the problem; the acceptance criteria were. A verifier is only as good as its criteria, and "it compiles and these DOM nodes exist" cannot see a look.

## 1. Which cards this applies to

A card is a **visual card** when its result is something a human reads with their eyes. Structural or logic work (a parser, a query, an IO layer) is not, even when it lives in a `.vue` file. When a card is both — a grid component that must also look right — split it: the logic card first, the visual card after.

## 2. Two mandatory headers

```
region: header-buttons
口径: /absolute/path/to/docs/prototype/prototype-口径.md#按钮规格
```

- `region:` — a stable slug for **one file plus one visual area**, not per element and not per project (`header-buttons`, `grid-toolbar`). It is the unit the convergence budget counts and the unit the staleness check keys on, so "this region's previous card" has to have exactly one answer.
- `口径:` — a pointer into the store: absolute path, plus an anchor or a line range. Anchor by heading where the store is markdown; line range where it is code.

## 3. The three checks before firing

Any one failing means **do not fire** — fix the store and the card first.

1. The file named by `口径:` exists.
2. The anchor or line range resolves, and the text there is what the card claims it is.
3. The store has been **written since this region's previous card**.

Check 3 is the one that looks pedantic and is not. The real failure is not a missing store — it is a store that stopped being maintained. Once it goes stale, the next card stops citing it and starts describing symptoms again, and every card after that is built on the previous card's render instead of on a spec. A store nobody writes to is worse than no store.

## 4. What counts as a reference

Exactly four kinds:

- a **prototype line range** — `prototype.html:1028-1066`;
- an **existing implementation's line range** — `release-1.2:web/src/project/views/index/params/index.vue:1-11`;
- a **signed-off comparison page** — see section 7;
- a **screenshot the operator circled**, plus the values measured from it.

The operator's own words are **not** a reference, and neither is your summary of them.

**One card, one source.** When a card would cite three (this prototype for colour, that branch for behaviour, the current tree for position), you reconcile them **before writing the card**: walk each element against each source, write the contradiction and its resolution into the store, and let the card cite the single source that came out on top. The most expensive card in the record is the one that carried all three and closed with "if you find a contradiction, stop and report" — that is a card defect, not a safety net. It hands the judgement back to the worker, which is the one party that cannot make it.

## 5. The status truth table

A visual card carries a table, not a paragraph.

| state | element A | element B | element C |
|---|---|---|---|
| tab 1 / view | shown — `params/index.vue:6` | hidden | shown, `right: 0` |
| tab 1 / edit | shown | shown | shown |
| tab 2 / view | hidden | hidden | shown |

Rows are every state that can exist — tab × edit/view × selected/none × with-data/without. Columns are the elements. Cells say shown, hidden, or position, plus the `file:line` that decides it.

An empty cell is an **unspecified state**, and an unspecified state comes back as a rework. If the cell cannot be filled from a reference, it is a look-and-feel question (section 7), not a gap to leave.

## 6. The red-to-green probe

Every visual card names one assertion that runs in a real browser, is **red before the fix** and green after. It measures numbers, not appearances — element count, `getComputedStyle` values, `offsetWidth`, `elementFromPoint`, class names, `aria-expanded`, `location.hash`.

Whatever genuinely cannot be moved to the machine side is written into the card as **"human eye"** — explicitly, in one line. An honest gap beats a fake check, and a probe that can only pass is a rubber stamp.

## 7. The comparison page

A **look-and-feel question** is one the operator cannot answer in words — they will know it when they see it. Any one of three signals makes an item one:

- their answer is "like X", "hard to say", "your call";
- this region has already had a card rejected;
- no reference of the four kinds can be named.

On any signal, the next action is **not a card**. Build a comparison page: one self-contained HTML file for the whole region (not one per question), the project's real colours and sizes at 1:1, toggles for every row of the status truth table, and two to four candidates side by side where they differ. The operator circles what is right; the page, a screenshot, and a measured-values table go into the store; cards then cite it.

Build it by hand, in the main agent. One page per region is cheaper than one card round trip, and it converts a text channel into a shared one: the operator's eyes and the worker's code read the same file instead of a description of it.

## 8. The convergence budget

Three consecutive visual cards in one region whose root cause is "the operator rejected the previous card's output" → **stop firing**. Build the comparison page, get it signed off, then resume. Two is too early (a fix that legitimately needs two rounds gets cut off); no budget at all is how a region burns a day.

taskproof stores the `region:` label and counts; the judgement stays with the main agent — the tool does not decide what is converging.

## 9. Revisiting the coordination pattern

This discipline is what lets the work stay **orchestrator-subagent**: a coordinator that dispatches bounded cards, workers that start fresh each time, a machine verifier that runs the acceptance command, and the accumulated context living in the **tree** (branches, worktrees, the store) rather than in a worker's context window. Workers stay replaceable, downgradable and auditable; the tree is what remembers.

Reconsider only when workers need each other's **intermediate findings** — not final output — to do their job, and compensating by hand (cherry-picks, restating one worker's discovery in the next card) starts to dominate. That is the point at which a shared store between agents earns its cost: it buys you out of that translation, and bills you in concurrent writes, duplicate work, and termination conditions. Until then this file is the cheaper half of the same idea.
