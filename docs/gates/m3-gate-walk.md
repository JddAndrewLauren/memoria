# The M3 gate walk

> Take a citation in an entry, click it, land on the exact evidence paragraph in
> the slide-over without losing your place, then open the original file.

This is the original M0 gate from the pre-rewrite build order, kept deliberately
(part 16 §44). It is the smallest complete demonstration that provenance is
real: from an interpretation, to the exact evidence, to the untouched original.
**"Open the original file" means what `docs/adr/0002-ui-is-a-react-client.md`
settled it as** — the raw, unnormalized source served in the page, showing
`original_locator` as text. No editor launch, no client-local behaviour.

## Who walks it, and why by hand

By hand, in a browser, by the author. `ui/src/routes/EntryPage.test.tsx` covers
the same path automatically — the chip opens the panel, the panel shows the
cited paragraph, the page underneath never navigates, "Open original ↗" points
at the raw route in its own tab — and that coverage is what keeps the path from
regressing. It is not the gate. The gate asks whether a person can follow a
claim to its evidence without losing their place, and a test asserting that
`location.pathname` is unchanged cannot answer that. This repo has no visual
gate by decision (`CLAUDE.md`), so there is no third option.

## The corpus

No evidence corpus is chosen (`docs/open-problems.md` §2.4), so the walk runs
against the four-custodian Enron slice, which exists for exactly this kind of
exercise — reproducible from `scripts/fetch-enron.py` and
`docs/corpora/enron-acquisition.yaml`, and nothing about the gate depends on it
being the eventual corpus.

```bash
export MEMORIA_EVIDENCE_ROOT=../enron-slice
```

Point it at the **slice**, not at the twelve-custodian pool beside it: that pool
was unpacked before `fetch-enron.py` was fixed to unpack `.eml` only, so it
holds a `.txt` sidecar beside every message and `memoria normalize` would
convert both — every message twice. The M1 gate walk lost time to this.

## Setup

```bash
scripts/run.sh          # installs both toolchains and builds ui/; stop it again (Ctrl-C)

.venv/bin/memoria seed-subjects
.venv/bin/memoria normalize          # a few minutes over the slice; idempotent
```

Then an entry to walk from. An entry is normally a promoted candidate, and
promotion runs through the extraction, which needs a model — so for the gate
write one by hand. That is the same act as writing one in Obsidian, and it is
what `find_entry_path` and the write path are built to survive. Put this at
`subjects/people/skilling.md`:

```markdown
---
id: SUB-people/skilling
match_terms:
- Skilling
---
Jeff Skilling, CEO.

[open] Which of these threads did he actually read?
```

Then:

```bash
.venv/bin/memoria rebuild            # fills the gathered set; no model
scripts/run.sh                       # open http://127.0.0.1:8000
```

`rebuild` is what fills the gathered set, and it needs no model: gathering stays
a deterministic lexical pass over the entry's word-shaped match terms (part 06
§8.3), so `Skilling` finds its paragraphs without the extraction having run.
Appearances stay empty — they match `source_type: book` only, and the slice
holds no audit targets.

## The walk

1. **Open the entry.** `SUBJECTS` → `people` → `skilling`. Before clicking
   anything, check the regions: the audit-visible body is drawn and says the
   record extractor fills it at M4; `Settlements` and `Memoria notes` are
   present and name M4; the `[open]` line is rendered **outside** the
   audit-visible body, under the note that assembly never loads it and the audit
   never evaluates against it. Nothing is hidden, and nothing is stubbed with
   example content.
2. **Read the match terms, then edit them** — add a term and press `Save`. This
   is the first durable write in the system. Then `git log -1`: the commit is
   path-scoped to `subjects/people/skilling.md` and attributed to you.
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

_Not yet walked._ Record the outcome here: the date, who walked it, what each
step did, and anything that did not behave as described above. A step that
failed is worth more in this section than a clean report.

## Cleanup

`subjects/people/skilling.md` is a durable file and the walk commits it. Remove
it and its commits before opening a PR, or run the walk in a scratch worktree.
`sources/normalized/`, `.memoria/` and `changes/` are gitignored derived state
and need no cleanup.
