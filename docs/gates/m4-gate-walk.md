# The M4 gate walk

M4 — Sessions and the Record Extractor (`plan/16-build-order.md`). Issue #34.
The gate, in the plan's own words:

> Hold a real research session on the piece's subject. Muse about an
> interpretation; it lands `[open]`. Decide something; the decision cites your
> exact turn, and clicking it lands on the sentence in which you decided.
>
> Hand-edit a badged statement. The next pass flags it human-touched; when
> evidence later conflicts with it, the conflict arrives as a Memoria note and
> your text is unchanged.

**This gate needs the author**, and the last section says exactly what is
left to them. What this walk proves is that the *machinery* behaves — every
mechanical clause of the gate, over a staged session, in a form that can be
run, failed, fixed and re-run inside a minute. What it cannot prove is
curator restraint on a genuine conversation, because a conversation held in
order to test restraint does not have the shape that fools the extractor
(#34's own words).

## Who walks it, and how

`scripts/gate-m4.sh` walks it, in two halves, and writes down what it saw.

The record extractor's three acts — the musing, the decision, the hand edit
and its note — are facts about files and commits, so `gate/m4/records.py`
walks them in the core with this checkout's own `.venv` python: it derives
the staged session, records the musing and the decision, refuses the
assistant's musing offered as a decision, seeds the badged statement, later
hand-edits it, flags it, lets a conflict arrive, and runs `memoria validate`.
Each act asserts against bytes on disk or a return value and appends what it
observed to the artifact.

The one clause only a browser can answer — *clicking it lands on the sentence
in which you decided* — is `ui/gate/m4-gate-walk.spec.ts`: real Chromium,
real `window.scrollY`, real `getBoundingClientRect`. `SectionPage.test.tsx`
covers the mechanism in jsdom (the chip opens the panel, the decided sentence
is the one marked, no route changed) and runs on every `npm test`; the walk
is where "on screen" and "kept my place" become observable.

The third layer is a person, and for this gate that layer is not optional —
see *What this walk does not prove*.

## The session

`gate/m4/session.jsonl`: four turns in Claude Code's own JSONL shape, about
the same invented Skilling thread `gate/corpus/` holds.

| Turn | Role | What it is for |
|---|---|---|
| T001 | Author | a musing — *"Maybe the deck went up unchanged because…"* — the thing that must land `[open]` |
| T002 | Assistant | the assistant's own musing, in decision-shaped words — the restraint control: offered to `record_decision`, it must be refused |
| T003 | Author | a three-sentence turn whose **middle** sentence is the decision — so "lands on the sentence" is a real question and not "the turn is the sentence" |
| T004 | Assistant | an acknowledgement, so the decision is not the last thing said |

The session's ledger (`events.jsonl`) records one served read of the
manuscript section, which is what makes the Section view's Decisions card
compose from it (`memoria.section.sessions_that_touched`).

## Setup

None, beyond the toolchains. The script builds its own throwaway repository
in a `mktemp -d`: seeds the subjects, normalizes `gate/corpus/`, writes
`gate/skilling.md`, commits the seeded state, rebuilds; then `records.py`
adds a book, a chapter and a 24-paragraph section (long enough that the page
scrolls), checkpoints them under a `CHG-` id, and derives the session.

```bash
scripts/run.sh                             # once: installs both toolchains
cd ui && npx playwright install chromium   # once: the browser
scripts/gate-m4.sh                         # the walk, ~30s, writes gate/last-run.md
scripts/gate-m4.sh --keep                  # and leaves the scratch repository to look at
```

## The walk

In the order the script runs them.

**Act 0 — derive.** `derive-session` over the fixture; four turns, the
transcript's own headings say who spoke each one. Committed by hand, as the
author.

**Act 1 — the musing lands `[open]`.** `record_question(T001)` writes
`[open] Maybe the deck went up unchanged…` citing `#T001` into
`questions.md`, and nothing in that file is `[author]`. Then the control:
`record_decision(T002)` — the assistant's musing — is refused, the refusal
names the assistant's turn and points at `record_question`, and
`decisions.md` does not exist.

**Act 2 — the decision cites its turn.** `record_decision(T003)` writes
`DEC-0001` as `[author] Let's keep it ambiguous…` citing `#T003`. The act
then reads that citation back through `read(ref)` and checks the decision's
sentence is *in* the served turn, between two other sentences.

**Act 3, first half — a statement to edit.** `record_statement` appends an
`[inferred]` statement with `SRC-` provenance to `subjects/people/skilling.md`,
committed as the Curator.

**Steps 1–4, in the browser.** The Section view shows `DEC-0001` in its
Decisions card with a `SES-…#T003` chip, and the musing in Open questions
with a `#T001` chip — and nowhere among the decisions. The reader is scrolled
part way down the page (the offset is read *before* the click and required
to be non-zero); the chip opens the slide-over and the URL does not change.
The panel's text is what `/api/read?ref=SES-…#T003` served — the whole turn,
not the decision alone — and exactly one sentence is marked, it reads the
decision word for word, and it sits inside the viewport. The panel closes,
`window.scrollY` is the pre-click offset, the URL is unchanged, and a
sentinel set on `window` before the click survived.

**Act 3, second half — the hand edit and the note.** The author edits the
`[inferred]` statement's words in place and commits by hand. `human_touched.
flag()` — the next pass — reports the statement flagged. The entry's bytes
are read *now*, before anything else happens. `revise_statement` is then
offered conflicting `SRC-` evidence: it returns a Memoria note, not a
rewrite; the file's bytes up to and including the author's edited statement
are identical before and after; the note follows it and ends *The author
text has been left unchanged*; and the note's commit, by the Curator, touched
that one file.

**Act 4 — validate.** `memoria validate` over the scratch repository: OK.

**Step 5, in the browser.** The entry page's audit-visible body shows the
hand-edited statement word for word; the Memoria notes region shows the
Curator's conflict and the closing line; none of the note is in the
audit-visible body.

## Proving the driver

Each of the regressions this walk exists to catch was injected, seen to go
red at the step built for it, and reverted (`gate/README.md`, second trap):

| Injection | Went red at |
|---|---|
| the chip navigates to a route instead of opening the panel | step 2 — the dialog never appears |
| the sentence mark inverted, so every sentence *but* the decision is marked | step 3 — `toHaveCount(1)` on the marks fails |
| `revise_statement` ignores the human-touched flag and rewrites the statement | act 3 — the outcome is a `StatementRecord`, not a note |

Two traps the walk itself fell into while being built, both the walk's
own and both worth naming for M5: a `git add -A` in the driver tracked the
index database and a log file, and the dirty-tree rule — correctly — then
refused every write; and a hand commit of manuscript files without the
checkpoint's `change-id` trailer is, to `validate`, an unauthorized AI
write. Logs now live beside the scratch repository, commits are path-scoped,
and the manuscript is checkpointed.

## Result

_Pasted from a run's own artifact (`gate/last-run.md`). Replace this with the
current one when the walk is re-run; a step that failed is worth more here
than a clean report._

Walked by `scripts/gate-m4.sh`: the record extractor in the core, the
click-through in Chromium at 1280×720, over a scratch repository built from
`gate/corpus/` (3 records normalized, seeded at `6652471`)
and the staged session in `gate/m4/session.jsonl`. Memoria at
`df5148b`.

### What each step did

- **Act 0 — the session is derived** — the manuscript checkpointed as `CHG-20260903-001`; `SES-20260903-1000` derived from the fixture JSONL: 4 turns, T001 and T003 the author's, T002 the assistant's; the section `SEC-0001` is in the session's ledger
- **Act 1 — the musing lands `[open]`** — `questions.md` holds `[open] Maybe the deck went up unchanged because nobody below Skilling dared to touch it.` citing `SES-20260903-1000#T001`, and nothing in it is badged `[author]`
- **Act 1 — the assistant's musing is refused as a decision** — `record_decision` on T002 refused: “SES-20260903-1000#T002 is the Assistant's turn, not the author's - a decision needs identifiable author evidence (part 06 §9.2); record this as an open item with record_question instead”; `decisions.md` does not exist
- **Act 2 — the decision cites its turn** — `DEC-0001` written `[author]` citing `SES-20260903-1000#T003`; `read(SES-20260903-1000#T003)` serves the author's turn and the decision's sentence is in it, between two other sentences
- **Act 3 — a badged statement exists to hand-edit** — `[inferred] The deck appears to have reached Skilling without anyone below him editing it.` appended to `subjects/people/skilling.md` citing `SRC-000004 ¶1`, committed as the Curator
- **Step 1 — the Section view** — `DEC-0001` is in the Decisions card citing `SES-20260903-1000#T003`; the musing is in Open questions citing `SES-20260903-1000#T001` and nowhere among the decisions
- **Step 2 — the citation opens the panel** — scrolled the reader to y=96px, clicked `SES-20260903-1000#T003`; the slide-over opened on that turn and the URL did not change
- **Step 3 — the exact sentence** — the panel drew the same text `/api/read?ref=SES-20260903-1000#T003` served (224 chars, three sentences); exactly one sentence is marked, it reads “Let's keep it ambiguous whether Skilling read the deck until the Friday thread.”, and it sits inside the viewport at y=93px
- **Step 4 — the reader's place** — panel opened and closed without moving the page; `window.scrollY` is still the 96px step 2 clicked from, the URL is unchanged, and the pre-click sentinel on `window` survived, so the section underneath was never remounted
- **Act 3 — the hand edit is flagged human-touched** — commit `56baa75` by `M4 gate walk` changed the statement; the next pass examined 2 non-Curator commit(s) and flagged `[inferred] The deck reached Skilling without anyone below hi…` on `SUB-people/skilling`
- **Act 3 — the conflict arrives as a Memoria note** — `revise_statement` with conflicting evidence `SRC-000004 ¶2` returned a Memoria note, not a rewrite; the first 250 bytes of `subjects/people/skilling.md` - the author's edited statement included - are identical before and after, the note follows it and ends “The author text has been left unchanged.”, and the note's commit by `Memoria` touched `subjects/people/skilling.md` only
- **Act 4 — validate** — `memoria validate` over the scratch repository: OK - every `#T` citation resolves and every assertion badge carries original-material provenance
- **Step 5 — the entry after the note** — the audit-visible body shows the author's hand-edited statement, word for word; the Memoria notes region shows the Curator's conflict (“A later message in the thread has the deck revised twice before it went up.”) ending “The author text has been left unchanged.”, and none of the note is in the audit-visible body

### Verdict

**The machinery passed**, 2026-09-03, on a staged session. **The gate is not
passed**: see below.

## What this walk does not prove, and what is the author's

The gate's acceptance criteria are about a *real* research session, and a
staged one cannot stand in for it. What remains, in the order it has to
happen:

1. **Decide the piece** (#27): subject, length, the §1.12 check, dated. The
   gate's sessions are that piece's research sessions, and nothing below can
   start before this.
2. **Hold the session** in Claude Code with the Memoria MCP server up, so
   the reads are ledgered under a `SES-` id. Muse; decide something; do not
   hold it *in order to* test the extractor.
3. **Curate it** — `/curation`. Derive the transcript from the session's
   JSONL, commit it, and let the pass record what happened. Quote the
   `[open]` musing, as written, in #34.
4. **Click the decision** on the Section view and confirm it lands on the
   sentence you decided in. If the page is not one the session touched,
   that is a finding.
5. **Hand-edit a badged statement**, run `curation_flag` (or the next
   `/curation`), and let a later conflict produce the note. Confirm your
   text is unchanged.
6. **File every extractor misbehaviour** as a regression test — the walk
   found none in the product on the staged session, which is the expected
   result of a staged session and says nothing about a real one.
7. `memoria validate` over the real repository.

When that is done, paste the real session's observations under *Verdict*
above, and close #34.
