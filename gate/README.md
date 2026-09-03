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

## Running the M3 walk

```bash
scripts/gate-m3.sh                 # writes gate/last-run.md
scripts/gate-m3.sh --keep          # and leaves the scratch repository behind
scripts/gate-m3.sh --artifact /tmp/walk.md
```

About four seconds, of which the walk itself is two. It needs `.venv` and
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

Two traps a walk has to be built against, both of which produce a green tick
over a broken app:

- *The vacuous assertion.* "The scroll position did not change" is `0 === 0`
  on a page that never scrolled. The M3 spec asserts the page scrolled to a
  non-zero offset **before** it checks the offset survived.
- *The unproven driver.* A walk that has never been seen to fail proves
  nothing. The M3 spec was checked by injecting the regression it exists to
  catch — a citation chip that navigates instead of opening the slide-over —
  and confirming step 4 goes red before the fix was reverted.

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

## Writing the M4 walk

Copy `scripts/gate-m3.sh` and `ui/gate/m3-gate-walk.spec.ts` and change what
the walk does; do not generalise them first. Two walks are not yet a pattern
worth abstracting, and the M3 script's preparation — seed, normalize, write
the entry, commit, rebuild — is the part most likely to be *wrong* for M4,
whose gate will want records the extractor has actually read.

The corpus is the part to reuse. If M4 needs paragraphs a model has extracted
from, add the memo rows the extraction would have written rather than a
larger corpus: what makes this fast is the record count, and nothing about the
walk gets more honest by growing it.
