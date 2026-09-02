---
name: extraction
description: Run Memoria's extraction over the archive - the author-launched pass in which a model reads every paragraph for what it mentions, and proposes candidates, clusters and match terms from what it found. Use when the author says "run the extraction", "extract the archive", "find candidates", or invokes /extraction. Not for searching the archive - that is read(ref) and search_text.
---

# The extraction

The extraction is the subject system's one candidate engine (part 06 §8.4,
`docs/adr/0005-extraction-is-the-candidate-engine.md`). It reads every
paragraph of the archive once, records what each mentions, and from that
proposes candidates under every subject, clusters offered under Themes and
Arcs, and match terms on the entries that already exist.

**It asserts nothing.** Everything it produces is a proposal the author's
match terms decide on, and everything but the cached readings is thrown away
and recomputed by the next `memoria rebuild`.

## Before anything: ask

Call `extraction_status()` and show the author what it says. Two numbers
matter:

- **paragraphs awaiting extraction.** If this is the whole corpus, either
  nothing has been extracted yet or a subject prompt changed - editing a
  subject re-reads everything, which is the price part 06 §8.1 names.
- **candidates and clusters already there**, from the last pass.

**Then ask whether to run it, and wait.** This is not a formality. The pass
reads the entire archive with a model, and part 08 §12.1's rule is that
nothing needing a model runs unasked. The tools are registered in every
session; the author saying go is what stands between a session and a
full-corpus pass.

## The brief

Call `extraction_brief()` **once** and keep it. It carries the extraction
prompt, every subject prompt with its match definition and hazards, and the
names of the entries that exist.

Do not paraphrase it, summarize it, or substitute instructions of your own.
The prompt it serves is the prompt hashed into every row you write; a reading
produced under different instructions would be cached as though it had been
produced under these.

## The paragraph loop

1. `extraction_next_paragraphs(limit=20)`.
2. For each paragraph, judge it **alone** - placements, unplaced surface
   forms, relations - exactly as the brief describes. Do not carry anything
   over from earlier paragraphs in this batch or this pass.
3. `extraction_record(results=[...])`, the whole batch in one call.
4. Read the outcome. Rejected elements name their reason; re-send those
   **once**, corrected. If the same paragraph is rejected twice, note the
   anchor for the final report and move on - one paragraph must not stall the
   pass.
5. Repeat until it says `No paragraphs need extraction.`

**Do not accumulate.** Once a batch is recorded, its text is dead weight: do
not carry it forward, quote it, or summarize it for yourself. If this session
is compacted mid-loop you have lost nothing - call `extraction_brief()` again
and go back to step 1. The database knows what is done.

## Derive

`extraction_derive()`. This calls no model; it recomputes placements,
candidates, relations and clusters from what you just recorded plus the
entries' current match terms. Report its numbers to the author.

## The summary loop

1. `extraction_next_summary()`.
2. Write the summary from **exactly what it served**. A leaf cluster serves
   its member paragraphs - read them with `read(ref)` first. A parent serves
   its children's summaries; write from those and do not reach past them to
   the paragraphs underneath.
3. `extraction_record_summary(cluster_id=..., membership=..., summary=...)`,
   echoing `membership` exactly as served.
4. Repeat until it says `No cluster needs a summary.`

## Finish

`extraction_finish()`. This promotes candidates only under subjects that
declare `auto-promote: yes`, and only above the recurrence filter. Themes and
Arcs ship with it off.

## If you run out of capacity

Stop cleanly. Tell the author which phase you were in and what
`extraction_status()` says, then: *"re-run `/extraction` to resume - nothing
is lost and nothing repeats."*

If the paragraph loop finished and the summary loop did not, say so plainly:
the extraction is complete and the summary set is partial. That is a
supported state, not a broken one (part 13 §24.3).

## The report

Close with:

- paragraphs read this pass, and how many were already cached;
- unplaced surface forms found;
- per subject, candidates **raw -> after the recurrence filter**, with the
  threshold;
- entries auto-promoted, by subject;
- candidates waiting for the author, top ten by recurrence;
- clusters by level; summaries written and remaining;
- proposed match terms waiting to be accepted or rejected;
- any paragraph that failed to record twice, by anchor;

and then, in as many words:

> The extraction asserted nothing. Every number above is a proposal; match
> terms decide what is placed, and nothing under a subject declaring
> `auto-promote: no` became an entry.
