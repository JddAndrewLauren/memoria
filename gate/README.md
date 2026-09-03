# Gate walks, and how they are driven

A **gate walk** is the once-per-milestone demonstration that the milestone
actually happened — a person, or an agent, following the path end to end in a
real browser and coming away with something a reader can check. The walks
themselves are written down in `docs/gates/`; this directory holds what a
scripted walk needs to run, and this file is the pattern the next one should
copy.

It is not part of the standing gate. `scripts/test.sh` — pytest plus vitest,
no browser — is what runs every time, and `CLAUDE.md` keeps it that way on
purpose. A gate walk is reached deliberately, by name.

## Running the walks

```bash
scripts/gate-m3.sh                 # writes gate/last-run.md
scripts/gate-m3.sh --keep          # and leaves the scratch repository behind
scripts/gate-m3.sh --artifact /tmp/walk.md
scripts/gate-m4.sh                 # the same flags; ~30s, most of it the ui build
scripts/gate-m5.sh                 # the same flags; ~1 min, three core phases, three browser phases
```

The M3 walk is about four seconds, of which the walk itself is two. It needs `.venv` and
`ui/node_modules` (run `scripts/run.sh` once), and a Chromium for Playwright
(`cd ui && npx playwright install chromium`).

## The pattern, in four parts

**1. A scratch repository, built from scratch, thrown away.** The walk seeds
subjects, normalizes a corpus, writes an entry, commits it and rebuilds an
index — and then, during the walk, *writes to it and commits again*. None of
that may happen in the checkout you are working in. `scripts/gate-m3.sh`
builds the whole thing in a `mktemp -d`, which is why the M3 gate doc no
longer has a Cleanup section: there is nothing left to clean up.

**2. A corpus small enough to run twice.** `gate/corpus/` is three invented
Enron-shaped messages. They normalize in 0.2s and rebuild in about a second,
so the walk is something an agent can loop on while fixing what it found. The
four-custodian Enron slice is the honest corpus and takes ~50 minutes to
normalize and over an hour to rebuild, which makes a check nobody runs twice
and therefore nobody runs. Fidelity is bought back elsewhere: the corpus keeps
the defects that matter (the ZL stray header line, a quoted reply the
converter must excise, a message that mentions nobody the entry is about, so
that gathering is seen to *select*).

**3. Assertions that only a browser can make.** This is the whole reason a
gate walk is not another vitest file. jsdom has no `scrollIntoView` and every
measurement it takes reads 0, so `ui/src/routes/EntryPage.test.tsx` can prove
that the page underneath never navigated — the *mechanism* behind keeping
your place — and never that the place was kept. `ui/gate/m3-gate-walk.spec.ts`
asserts real `window.scrollY`, real viewport geometry, and a sentinel on
`window` that a remount would have destroyed. Anything a jsdom test could
have asserted belongs in the vitest suite instead, where it runs every time.

Three traps a walk has to be built against, each of which produces a green
tick over a broken app:

- *The vacuous assertion.* "The scroll position did not change" is `0 === 0`
  on a page that never scrolled. The M3 spec asserts the page scrolled to a
  non-zero offset **before** it checks the offset survived.
- *The unproven driver.* A walk that has never been seen to fail proves
  nothing. The M3 spec was checked by injecting the regression it exists to
  catch — a citation chip that navigates instead of opening the slide-over —
  and confirming step 4 goes red before the fix was reverted.
- *The baseline sampled too late.* The subtler cousin of the first, found by
  a second agent walking the gate. Step 6 read the scroll offset it compared
  against **after** the panel had already opened — which is after the only
  moment the offset can be lost. Injecting a `position: fixed` scroll-lock on
  `body` sent the reader from y=432 to the top of the page, and step 6 still
  passed, comparing 0 to 0 and printing “still 0px” into the artifact. Step 6
  now measures against the offset step 4 read *before the click*, and was
  confirmed red against that injection.

  The general form, for M4 and M5: **take the reading before the interaction
  under test, not after it.** An “X is unchanged” step whose baseline is
  sampled mid-interaction asserts only that the damage was stable, never that
  it never happened.

**4. An artifact, written as the walk goes.** Each step appends what it
*observed* — the actual scroll offset, the actual sentence compared — to the
file named by `MEMORIA_GATE_ARTIFACT`, and the shell script frames it with the
run's provenance and the git check for the durable write. The result is a page
someone can read instead of a screenshot nobody opens. A passing run's
artifact is pasted into the gate doc's own Result section by hand; the file
itself is gitignored, because a record that rewrites itself on every run is
not a record.

## Files

| path | what it is |
| --- | --- |
| `gate/corpus/*.eml` | the three-message fixture corpus, invented text, Enron-shaped |
| `gate/skilling.md` | the entry the walk is driven from, copied into the scratch repository |
| `gate/last-run.md` | the last run's artifact (gitignored) |
| `scripts/gate-m3.sh` | prepare, serve, walk, record, tear down |
| `ui/playwright.config.ts` | the browser driver — `npm run gate`, never `npm test` |
| `ui/gate/m3-gate-walk.spec.ts` | the seven steps |
| `docs/gates/m3-gate-walk.md` | what the walk means, and the recorded Result |
| `gate/m4/session.jsonl` | the M4 walk's staged session, four turns in Claude Code's JSONL shape |
| `gate/m4/records.py` | the M4 walk's record-extractor acts, run in the core before and after the browser steps |
| `scripts/gate-m4.sh` | prepare, acts, serve, walk, more acts, validate, record, tear down |
| `ui/gate/m4-gate-walk.spec.ts` | the five browser steps, in two phases |
| `docs/gates/m4-gate-walk.md` | what the M4 walk means, the recorded Result, and what is left to the author |
| `gate/m5/legacy.md` | the M5 walk's "existing chapter", eight paragraphs the author imports as legacy manuscript |
| `gate/m5/session.jsonl` | the M5 walk's staged writing session, two turns; T001's middle sentence authorizes the draft |
| `gate/m5/records.py` | the M5 walk's core acts in three phases: import, brief and assembly, draft and trace; the audit; the re-audit and validate |
| `scripts/gate-m5.sh` | prepare, acts 1-4, serve, browser, act 5, browser (the Settle click), act 6-7, browser, record, tear down |
| `ui/gate/m5-gate-walk.spec.ts` | the seven browser steps, in three phases |
| `docs/gates/m5-gate-walk.md` | what the M5 walk means, what building it found, the recorded Result, and what is left to the author |

## Writing the next walk

Copy the closest of the two scripts and change what the walk does; do not
generalise them first. M4 copied M3 and changed the preparation (it wanted a
manuscript section, a derived session and records the extractor had written)
and split the walk into a core half and a browser half, because most of its
gate is facts about files and commits and only one clause needs a viewport.
Each script passes its own spec name to `npm run gate` - the Playwright
config runs everything under `ui/gate/`, so an unfiltered run walks every
milestone against one milestone's server. Two lessons from building it, both
about the scratch repository rather than the app: never `git add -A` after the index exists (the dirty-tree rule will
refuse every later write, correctly), and a manuscript file the author lays
down by hand is checkpointed, not committed, or `validate` reads it as an
unauthorized AI write.

M5 copied M4 and needed three core phases rather than two, because the
browser's own act - the Settle click - sits between the audit and the
re-audit; the shell script's `browser`/`core` functions are the whole of
that generalisation. Two things it found worth passing on: a walk whose
gate names a *button* should check the button exists before scripting the
click (M5's Settle was a disabled placeholder with a stale tooltip, and the
walk's first job was to build it), and a "before and after" reading of a
count - the tinted paragraphs around the settlement - is the same third
trap as M3's scroll offset, and was taken before the click for the same
reason.

The corpus is the part to reuse. If a walk needs paragraphs a model has
extracted from, add the memo rows the extraction would have written rather
than a larger corpus: what makes this fast is the record count, and nothing
about the walk gets more honest by growing it.
