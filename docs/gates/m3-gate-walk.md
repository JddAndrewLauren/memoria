# The M3 gate walk

> Take a citation in an entry, click it, land on the exact evidence paragraph in
> the slide-over without losing your place, then open the original file.

This is the original M0 gate from the pre-rewrite build order, kept deliberately
(part 16 §44). It is the smallest complete demonstration that provenance is
real: from an interpretation, to the exact evidence, to the untouched original.
**"Open the original file" means what `docs/adr/0002-ui-is-a-react-client.md`
settled it as** — the raw, unnormalized source served in the page, showing
`original_locator` as text. No editor launch, no client-local behaviour.

## Who walks it, and how

`scripts/gate-m3.sh` walks it, in Chromium, and writes down what it saw.

There are three layers here and it is worth keeping them apart.
`ui/src/routes/EntryPage.test.tsx` covers the path in jsdom — the chip opens
the panel, the panel shows the cited paragraph, `location.pathname` never
changes, "Open original ↗" points at the raw route in its own tab. That is the
cheap regression net and it runs on every `npm test`. What it *cannot* answer
is the gate's actual question, because jsdom has no `scrollIntoView` and every
measurement it takes reads 0: "landed on the exact paragraph" and "did not
lose my place" are unobservable there by construction, not merely untested. So
the jsdom tests prove the mechanism — that nothing navigated — and the walk
proves the thing itself.

The walk is the second layer: a real browser, real `window.scrollY`, real
viewport geometry, over a real server and a real normalized corpus, ending in
an artifact (`gate/last-run.md`) that says what each step observed. It is not
part of the standing gate — `CLAUDE.md` keeps routine work browser-free — and
is run by name, once per milestone and whenever this path is touched.

The third layer is a person. Nothing here stops the author walking it by hand,
and for anything about how the page *feels* that is still the only instrument.
What the script removes is the need to spend a person on the seven mechanical
questions below in order to find out whether the milestone happened.

The pattern the script follows — and the traps it is built against — is
`gate/README.md`.

## The corpus

`gate/corpus/`: three invented, Enron-shaped `.eml` messages, committed to
this repository. Small on purpose. No evidence corpus is chosen
(`docs/open-problems.md` §2.4), and the four-custodian Enron slice — the
honest stand-in — takes about **50 minutes to normalize** (4,426 records) and
**over an hour to rebuild**, measured 2026-09-03. A check that costs two hours
is a check that runs once and then never again, which is the opposite of what
a gate is for. The fixture corpus normalizes in 0.2s and rebuilds in about a
second, so the walk can be run, failed, fixed and re-run inside a minute.

What is bought back is fidelity, and it is bought deliberately: the corpus
keeps the defects that matter to this path. The ZL production's stray
`Microsoft Mail Internet Headers` line is in every message, so the converter
is exercised on the real failure; one message is a reply whose quoted history
the converter must excise, which is what makes step 7's comparison show a
*difference* rather than an identity; and one message mentions nobody the
entry is about, so gathering is seen to select two records out of three rather
than to return everything.

The claim step 7 makes about the whole corpus — that every served paragraph
appears verbatim in its original — is also asserted in
`tests/test_normalization_fidelity.py`, over the `tests/fixtures/enron/`
messages, through the same two HTTP routes. The walk demonstrates it for a
reader; the pytest file is what keeps it from regressing between walks.

## Setup

None, beyond the toolchains. `scripts/gate-m3.sh` builds its own throwaway
repository — it seeds the subjects, copies `gate/corpus/` in as the evidence
root, normalizes, writes `gate/skilling.md` to `subjects/people/skilling.md`,
commits that seeded state, rebuilds the index and serves it — because two of
the seven steps below write to disk and commit, and this checkout is not a
place to do that.

```bash
scripts/run.sh                       # once: installs both toolchains
cd ui && npx playwright install chromium   # once: the browser
scripts/gate-m3.sh                   # the walk, ~4s, writes gate/last-run.md
```

`rebuild` fills the gathered set and needs no model: gathering stays a
deterministic lexical pass over the entry's word-shaped match terms (part 06
§8.3), so `Skilling` finds its paragraphs without the extraction having run.
Appearances stay empty — they match `source_type: book` only, and the corpus
holds no audit targets.

## The walk

The seven steps, each one a test in `ui/gate/m3-gate-walk.spec.ts` bearing the
same number. Read them as the questions the walk asks; read the spec for what
exactly is asserted.

1. **Open the entry.** `SUBJECTS` → `people` → `skilling`. Before clicking
   anything, check the regions: the audit-visible body is drawn and says the
   record extractor fills it at M4; `Settlements` and `Memoria notes` are
   present and name M4; the `[open]` line is rendered **outside** the
   audit-visible body, under the note that assembly never loads it and the audit
   never evaluates against it. Nothing is hidden, and nothing is stubbed with
   example content.
2. **Read the match terms, then edit them** — add a term and press `Save`. This
   is the first durable write in the system. Then `git log -1`: the commit is
   path-scoped to `subjects/people/skilling.md` and attributed to you. (The
   spec checks the file; `scripts/gate-m3.sh` checks the commit, since it is
   the thing that owns the repository.)
3. **The staleness check.** With the entry still open in the browser, edit
   `subjects/people/skilling.md` in another editor and save it. Then add another
   match term in the browser and press `Save`. It must be refused, name the
   file, leave your edits in the editor, and write nothing — check that the file
   on disk is exactly what the other editor left.
4. **Click a citation** in the gathered set. The slide-over comes in from the
   right, over a scrim that starts at the sidebar's edge.
5. **Land on the exact paragraph.** The panel shows the cited paragraph, its
   record's badge row, and its backlinks.
6. **Confirm you have not lost your place.** Close the panel: the entry is
   exactly where it was, at the same scroll position, with nothing reloaded.
7. **Open the original.** `Open original ↗` in the panel opens the raw route in
   its own tab: the raw bytes of the unnormalized file, with `original_locator`
   above them. Compare a sentence against what the slide-over showed. That
   comparison is the point of the gate — it is what says normalization invented
   nothing.

## Result

_Pasted from a run's own artifact (`gate/last-run.md`). Replace this with the
current one when the walk is re-run; a step that failed is worth more here
than a clean report._

Walked by `scripts/gate-m3.sh` in Chromium at 1280×720, over a scratch
repository built from `gate/corpus/` (3 records normalized,
seeded at `b8268dc`). Memoria at `95cc44d`.

### What each step did

- **Step 1 — the entry opens** — all six regions drawn; Settlements and Memoria notes name M4; the `[open]` line renders inside the “Outside the audit-visible body” region
- **Step 2 — the first durable write** — `Jeffrey Skilling` added and saved; the term is in `subjects/people/skilling.md` on disk
- **Step 3 — the staleness check** — an out-of-band edit made the held token stale; the save was refused, the file on disk is byte-for-byte what the other editor left, and the rejected term is still in the editor
- **Step 4 — the citation opens the panel** — scrolled to y=432px, clicked `src-000006-p1`; the slide-over opened over a scrim starting at the sidebar's edge, and the URL did not change
- **Step 5 — the exact paragraph** — the panel drew the same text `/api/read?ref=src-000006-p1` served, fully inside the viewport at y=131px, with the record's badge row and a `Cited by` backlink to people/skilling
- **Step 6 — the reader's place** — panel closed; `window.scrollY` is still 432px, the URL is unchanged, and the pre-click sentinel on `window` survived, so the page underneath was never remounted
- **Step 7 — the original** — “Open original ↗” opened `/sources/SRC-000006/raw` in its own tab with the entry still open behind it; the served paragraph (“The deck went up to Skilling unchanged, so whatever we send Friday has to…”) appears verbatim in the raw `.eml`, whose headers and quoted reply the record does not carry

### The durable write, in git

- The last commit is path-scoped to `subjects/people/skilling.md` and
  nothing else, authored by `M3 gate walk`: "write: subjects/people/skilling.md"

### Verdict

**Passed**, 2026-09-03. All seven steps behaved as described above.

## Cleanup

None. `scripts/gate-m3.sh` builds its repository in a `mktemp -d` and deletes
it on the way out (`--keep` if you want to poke at it afterwards), so nothing
the walk writes or commits — `subjects/people/skilling.md` included — ever
touches this checkout. `gate/last-run.md` is gitignored; the run worth keeping
is the one pasted above.
