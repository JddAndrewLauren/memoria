# The M5 gate walk

M5 — The Manuscript Layer and the Authorship Piece (`plan/16-build-order.md`).
Issue #45. The gate, in the plan's own words:

> Import an existing chapter of prose as legacy manuscript. It gets an
> unconfirmed brief and a not-current tint; no model pass runs unasked.
>
> Write the piece's section brief, naming something with no entry. Open the
> supplied context: assembly reports what the scope resolved to, and the
> fallback to an unpromoted candidate is named there rather than passing in
> silence. Authorize a draft from the assembled context, then ask why a
> paragraph says what it says and walk the provenance to the session, the
> authorization and the evidence.
>
> Audit the section from its button. Settle one finding; the tint clears only
> through re-audit.

**This gate needs the author**, and the last section says exactly what is
left to them. What this walk proves is that the *machinery* behaves — every
mechanical clause of the gate, over a staged chapter, brief and session, in a
form that can be run, failed, fixed and re-run in about a minute. What it
cannot prove is anything about the real piece: the recall check ("anything
assembly missed that the author knows should have been caught") is a judgement
only the author of the archive can make, and #27 has not decided the piece.

## Who walks it, and how

`scripts/gate-m5.sh` walks it, in three core phases with a browser phase after
each, and writes down what it saw.

The manuscript layer's acts — the import, the brief and its assembly, the
authorization and the draft, the trace, the audit and its judgements — are
facts about files, commits and ledgers, so `gate/m5/records.py` walks them in
the core with this checkout's own `.venv` python. It imports the legacy
chapter under a guard that fails any socket or subprocess, writes the piece's
brief and assembles it, refuses two unauthorized drafts and writes the
authorized one, traces a paragraph both through `memoria.trace` and through
the MCP tool's rendering, answers every audit judgement by hand through
`audit_pending`/`audit_record`, and after the browser has settled a finding,
shows the section pending with cause `entry_changed`, re-audits it current,
and runs `memoria validate`. Each act asserts against bytes on disk, a return
value or a commit, and appends what it observed to the artifact.

What only a browser can answer is `ui/gate/m5-gate-walk.spec.ts`: that the
not-current tint is *painted* (a computed `box-shadow`, not a class name) on
the legacy chapter and the fresh draft; that the supplied-context surface
names the fallback verbatim, refreshes while open and stops when closed
(counted requests over a window longer than its interval); that a finding is
settled *from its button*, through the form the Review page now has; and that
settling did not clear the tint — the count of tinted paragraphs is read
before the settlement, required to be zero, and read again after. jsdom cannot
paint and cannot poll a server, which is why these are not vitest.

**Two clauses are walked in the core rather than on screen, by decision.**
The audit's "button" is the MCP pair `audit_pending`/`audit_record`: the PoC's
surfaces need no model driver (`poc-plan.md` §5, `SectionPage.tsx`'s own
note), and the on-screen button is deferred with Ask Memoria. `trace()` is an
MCP tool with no UI, and the walk asks it the way a session would.

The third layer is a person, and for this gate that layer is not optional —
see *What this walk does not prove*.

## The fixtures

| path | what it is |
|---|---|
| `gate/m5/legacy.md` | eight paragraphs of invented prose about the Skilling thread — the "existing chapter" the author imports |
| `gate/m5/session.jsonl` | two turns in Claude Code's own JSONL shape: T001 the author's, whose **middle** sentence authorizes the draft; T002 the assistant's acknowledgement |
| `gate/corpus/`, `gate/skilling.md` | the M3/M4 corpus and entry, reused unchanged |
| a `candidates` row | `CAN-0001`, label `Fastow`, under People — the row the extraction would have written for a surface form nobody promoted, inserted by `records.py` (gate/README.md: add the rows, not a larger corpus) |

The piece's brief names Skilling (an entry) and Fastow (a candidate with no
entry): "How the deck reached Skilling, and what Fastow did with it before the
Friday thread." The legacy chapter's brief names Skilling too, so its tint has
an entry to be not-current against.

## Setup

None, beyond the toolchains. The script builds its own throwaway repository
in a `mktemp -d`, as M4's does: seeds the subjects, normalizes `gate/corpus/`,
writes `gate/skilling.md`, commits the seeded state, rebuilds.

```bash
scripts/run.sh                             # once: installs both toolchains
cd ui && npx playwright install chromium   # once: the browser
scripts/gate-m5.sh                         # the walk, ~1 min, writes gate/last-run.md
scripts/gate-m5.sh --keep                  # and leaves the scratch repository to look at
```

## The walk

In the order the script runs them.

**Act 1 — the legacy import, and nothing runs unasked.** `import_chapter`
under the guard. Both briefs carry `unconfirmed: true`, `draft.md` is the
prose byte-for-byte, the count is a scalar, the staleness map reads every
paragraph `never_audited`, the memo table has the same row count as before,
HEAD did not move and no commit is Memoria's. The import is then checkpointed
by hand under a `CHG-` id, which is what `validate` reads as a human write.

**Act 2 — the brief, and assembly's report.** The piece's section is created
confirmed and checkpointed. A read of it is ledgered on the session, then
`assemble` runs: one entry resolved (`SUB-people/skilling`, named by its
terms, with a gathered set reported as anchors), one fallback (`CAN-0001`,
`Fastow`), one `assemble` line on the ledger, nothing durable. The resolution
is written into the artifact in full — the "resolution report recorded"
criterion.

**Act 3 — the draft, under authorization.** The session is derived from the
fixture and committed by hand. `write_draft` with no authorization is
`Refused`; with one covering only ¶3 it is `Refused` and names the scope it
does cover; no draft exists after either. Under an authorization covering the
section it is `Applied`: the commit is by `Memoria` and carries
`authorized-by: SES-…#T001` and `authorized-scope: SEC-0002 draft`, and no
`change-id`.

**Act 4 — why ¶3 says what it says.** `trace(SEC-0002 ¶3)`: one step, that
commit, authorized by that turn; the turn's text is served verbatim and the
authorizing sentence sits between two others in it; `assembled_from` starts
with the entry and goes on to the sources assembly served. The MCP tool
renders the same chain and ledgers one `trace` line. The control: the legacy
`SEC-0001 ¶1` traces to its `CHG-` id and stops, with no session.

**Steps 1–3, in the browser.** The legacy section shows the `unconfirmed
brief` badge, "8 of 8 paragraphs not current", eight painted paragraphs each
with a `never audited` row, and agrees with `/api/sections/SEC-0001`. The
piece's section shows no badge, 24 painted paragraphs, and an opener that
carries no digit. The supplied-context surface, opened from it, reads "1 brief
· 1 entry · 1 fallback · N sources served since", names the entry and the
fallback verbatim, shows no token, byte or percentage figure; one read
appended to the ledger appears in *Served since* without a click; after
navigating back, no request arrives in seven seconds.

**Act 5 — the audit, from its button.** `audit_pending(2, 1)` serves the
paragraphs with the People subject's own questions. Every task is answered by
hand through `audit_record` in rounds (a verdict is only asked for once its
engagement is recorded): engagement everywhere, clear everywhere but ¶3,
where the verdict is a three-way finding — the passage, the entry, the first
gathered source — the only shape whose resolutions are settlements. Review
serves it with the three `settle toward …` resolutions, 24 judgements current;
the legacy chapter is still entirely `never_audited`.

**Steps 4–6, in the browser.** The section reads "Every paragraph is current."
and the tinted count is read and required to be **zero** — the baseline. Review
shows the finding: ¶3, high confidence, raised by People, three chips, three
resolutions, `Settle` enabled. Settle is clicked; the form offers the set's
sides and the section's sessions; the entry is chosen, a proposition and a
reason typed, the session picked, the settlement recorded. The card reports
it on the entry as `CLM-0001`, the finding is gone, and the entry page shows
the settled line in its audit-visible body. Back on the section: 24 of 24
tinted, every one with a `not current · entry changed since ·
SUB-people/skilling` row — the settlement moved the entry, and nothing
pretended otherwise.

**Act 6 — current only through re-audit.** The entry carries one `[settled]`
line citing the bare session id and a claim beside it, committed by the author.
Every paragraph is pending with cause `entry_changed`, and `findings_in_scope`
is empty (silenced). A fresh all-clear batch through `audit_record` brings the
section current with no finding. The legacy chapter is still `never_audited`.

**Act 7 — validate.** `memoria validate` over the scratch repository: OK.

**Step 7, in the browser.** The section reads current with no tinted
paragraph; Review finds nothing to disagree with at 24 judgements current;
the legacy section is still 8 of 8 not current.

## What the walk found

Building it found two defects and one observation, in the order they appeared:

1. **The Review page's Settle button was dead.** It was rendered disabled with
   a tooltip saying settlements "arrive with #33", after #33 had landed;
   `settlements.settle` existed and nothing reached it — no route, no tool.
   The gate's "settle one finding" could not be performed from the surface.
   Fixed in the same PR: `POST /api/sections/{id}/settlements` through
   `memoria.review.settle_finding`, with the entry's staleness token served on
   the finding and presented back (409 when the entry moved), the sessions
   that touched the section offered as the settlement's provenance, and the
   button opening a form. Pinned by `tests/test_web_app.py` and
   `ui/src/routes/ReviewPage.test.tsx`.
2. **`trace()` reported an empty `assembled from` for a draft written from the
   assembled context.** The context manifest projected only `read` lines into
   `entries_resolved`/`records_loaded`, and the trace read only those; the
   `assemble` line — the entries and sources the draft was actually written
   from — was ignored. A session that assembled and wrote, without also
   reading, traced to nothing. Act 4 went red on the walk's first run. Fixed
   in `memoria.trace`: what assembly resolved is folded in, entries then
   records, sources named as citations. Pinned by
   `tests/test_trace.py::test_a_paragraph_written_from_assembled_context_traces_to_what_assembly_resolved`.
3. **Observation, not fixed (#205):** after a settlement every judgement against the
   entry is stale, so Review reads "No audit has been run on this section"
   until the re-audit. That is what `verdicts_current == 0` means to the
   surface, and it is the honest count — but the sentence is false for a
   section that was audited an hour ago. Filed as #205 rather than changed here; the two settlement placeholders that outlived #33 (`ReadOverlay.citing_settlements`, the entry view) are #204.

## Proving the driver

Each of the regressions this walk exists to catch was injected, seen to go red
at the step built for it, and reverted (`gate/README.md`, second trap):

| Injection | Went red at |
|---|---|
| `is_audit_visible` drops `[settled]` (a settlement no longer moves the entry's audit-visible body) | step 5 — the settled state never appeared: the review re-read served the section still current, the finding unsilenced; the route test's `(0, 2)` likewise |
| the settle path ignores the entry token | `tests/test_web_app.py::test_settling_with_a_stale_entry_token_is_a_409_and_writes_nothing` |
| `write_draft` omits the `authorized-by`/`authorized-scope` trailers | act 3 — the commit body carries no `authorized-by` |
| the supplied-context surface renders every fallback list as "None" | step 3 — the fallback text is not on the page |
| `import_chapter` opens a socket | act 1 — the guard raises “the legacy import touched the network or a process” |
| `trace()` ignores the `assemble` line (the defect as found) | act 4, on the first run — `assembled_from` empty |

## Result

_Pasted from a run's own artifact (`gate/last-run.md`). Replace this with the
current one when the walk is re-run; a step that failed is worth more here
than a clean report._


Walked by `scripts/gate-m5.sh`: the manuscript layer in the core, the tints,
the supplied context and the Settle click in Chromium at 1280×720, over a
scratch repository built from
`gate/corpus/` (3 records normalized, seeded at `5c50f61`)
and the staged session in `gate/m5/session.jsonl`. Memoria at
`9baa3b2`.

## What each step did

- **Act 1 — the legacy chapter is imported, and nothing ran unasked** — `import_chapter` under a guard that fails any socket or subprocess: `chapters/01/chapter.md` and `chapters/01/sections/01/section.md` both carry `unconfirmed: true`, `draft.md` is the 1097-byte prose byte-for-byte, the count is 8; the staleness map reads every one of the 8 paragraphs `never_audited` against `SUB-people/skilling`; the memo table still holds 0 row(s), HEAD did not move and no commit is Memoria's; the author's import checkpointed as `CHG-20260903-001`
- **Act 2 — the piece's brief, and assembly's report** — `SEC-0002` written confirmed as “How the deck reached Skilling, and what Fastow did with it before the Friday thread.” and checkpointed as `CHG-20260903-002`; `assemble` resolved the scope to 1 entry - `SUB-people/skilling` named by `skilling, Skilling`, gathered set of 2 source(s) reported as identifiers (src-000005-p1, src-000006-p1) - and 1 fallback: “Fastow” named no entry, so assembly fell back to the unpromoted candidate `CAN-0001` under `SUB-people`, its identity only; the resolution is one `assemble` line on the session's ledger and nothing durable
- **Act 3 — the draft is written under authorization** — `SES-20260903-1100` derived from the fixture (2 turns, T001 the author's); `write_draft` with no authorization was refused (“no authorization”), and with one covering only ¶3 was refused (“not covered: SES-20260903-1100#T001 authorizes SEC-0002 ¶3, not SEC-0002 draft”), leaving no draft; under an authorization covering the section it wrote 24 paragraphs, and commit `6ccbcb7` by `Memoria` carries `authorized-by: SES-20260903-1100#T001` and `authorized-scope: SEC-0002 draft` and no `change-id`
- **Act 4 — why ¶3 says what it says** — `trace(SEC-0002 ¶3)`: one step, commit `6ccbcb7` by `Memoria`, authorized by `SES-20260903-1100#T001` over `SEC-0002 draft`; the authorizing turn is served verbatim and the sentence that authorized - “Go ahead and draft the section from the context you assembled.” - sits between two others in it; assembled from `SUB-people/skilling` and then 2 source record(s) (SRC-000005 ¶1, SRC-000006 ¶1); the `trace` tool renders the same chain and ledgered one `trace` line on `SES-20260903-1100`; the legacy `SEC-0001 ¶1` traces to `CHG-20260903-001` and stops, with no session
- **Step 1 — the legacy chapter** — `SEC-0001` shows the `unconfirmed brief` badge and “8 of 8 paragraphs not current”; all 8 paragraphs are tinted (computed box-shadow “rgb(168, 118, 42) 3px 0px 0px 0px inset”), each with a “never audited · SUB-people/skilling” row; `/api/sections/SEC-0001` says the same
- **Step 2 — the piece's section** — `SEC-0002` has no unconfirmed badge; all 24 draft paragraphs are tinted never-audited; the “Supplied context” opener carries no count and no digit
- **Step 3 — the supplied context** — opened from the section: “1 brief · 1 entry · 1 fallback · 2 sources served since”; the working context names the entry (“named by skilling”, gathered set reported as identifiers, not loaded) and the fallback verbatim: ““Fastow” named no entry. Assembly fell back to the unpromoted candidate CAN-0001 under SUB-people — its identity only; nothing of it was loaded.”; no token, byte or percentage figure on the page; one read appended to the ledger appeared in “Served since” without a click (1 → 2 rows, 2 reads while open); after closing, no request in 7s
- **Act 5 — the audit, from its button** — `audit_pending(2, 1)` served the section's paragraphs with the People subject's own questions; 48 judgements recorded through `audit_record` in hand-written batches, every one accepted: engagement everywhere, clear verdicts everywhere but ¶3, where a three-way finding - the passage, `SUB-people/skilling`, `src-000005-p1` - states “The draft has Skilling reading the deck the night it went up; the thread has it revised twice before it reached him.”; Review serves it with the three `settle toward …` resolutions, 24 judgements current and 0 not; the legacy chapter's 16 judgements are still `never_audited` - the audit ran only where it was asked
- **Step 4 — the audit's results** — after the audit, `SEC-0002` reads “Every paragraph is current.” with 0 tinted paragraphs (the baseline step 6 compares against); Review shows 1 finding on ¶3, high confidence, raised by SUB-people, its three chips and three settle resolutions, and Settle is enabled
- **Step 5 — settled from its button** — clicked Settle on the ¶3 finding, chose the entry, wrote “the deck was revised twice before Skilling saw it” for “the thread is contemporaneous and the draft was from memory” in `SES-20260903-1100`, recorded; the card reports the settlement on `SUB-people/skilling` as `CLM-0001` in the page's “Settled this visit” list, which outlives the card; the finding is gone from Review and the summary asserts “0 findings” and “no judgements current” separately; the entry's audit-visible body shows the settled line
- **Step 6 — settling did not clear the tint** — back on `SEC-0002`: 24 of 24 paragraphs tinted where step 4 read 0, every one with a “not current · entry changed since · SUB-people/skilling” row - the settlement moved the entry, and nothing pretended the section was still current
- **Act 6 — settled, and current only through re-audit** — the browser's settlement is on `subjects/people/skilling.md` as “[settled] the deck was revised twice before Skilling saw it — SUB-people/skilling, chosen over SRC-000005 ¶1, 2026-09-03” citing `SES-20260903-1100`, committed by `M5 gate walk`, with `claims/CLM-0001.md` beside it; that moved the entry, so all 24 paragraphs were pending with cause `entry_changed` and the settled finding was silenced; 48 fresh judgements through `audit_record` brought the section current with no finding; the legacy chapter's 16 judgements are still `never_audited`
- **Act 7 — validate** — `memoria validate` over the scratch repository: OK - the AI draft carries its authorization, the settlement parses with its session, every `#T` citation resolves
- **Step 7 — current only through re-audit** — after the re-audit `SEC-0002` reads “Every paragraph is current.” with 0 tinted paragraphs, Review finds nothing to disagree with at 24 judgements current; the legacy `SEC-0001` is still 8 of 8 not current - no pass reached it unasked

### Verdict

**The machinery passed**, 2026-09-03, on a staged chapter, brief and session.
**The gate is not passed**: see below.

## What this walk does not prove, and what is the author's

The gate's acceptance criteria are about the *real* piece, and a staged one
cannot stand in for it. What remains, in the order it has to happen:

1. **Decide the piece** (#27): subject, length, the §1.12 check, dated. Its
   research already exists as durable records from M4's sessions; nothing
   below can start before this.
2. **Import a real chapter.** Any existing prose of the author's, through
   `legacy_import.import_chapter` from a session, and confirm on screen what
   the walk confirmed on the fixture: the badge, the tint, and no model pass.
   A chapter whose brief names nothing will show no tint — there is no entry
   to be not-current against — and if that reads wrong, it is a finding.
3. **Write the piece's brief**, naming what the piece is about, and open the
   supplied context. Record assembly's resolution in #45 as the walk recorded
   the fixture's. Then the check no script can make: **what did assembly
   miss** that you know should have been caught? Write it down — that is the
   recall evidence the issue asks for.
4. **Authorize a draft** from a real session and let the writing agent lay it
   down. Ask `trace()` why a paragraph says what it says, and walk it to the
   turn, the authorization and the evidence. Record the walk.
5. **Audit from a session** (`audit_pending`/`audit_record` through the model),
   settle one finding from Review's button, and confirm the tint returns and
   clears only after the re-audit — the same three readings step 4, step 6 and
   step 7 take.
6. **File every failure** as a regression test — the walk found two in the
   product on the staged piece and expects a real one to find more.
7. `memoria validate` over the real repository.

When that is done, paste the real piece's observations under *Verdict* above,
and close #45.
