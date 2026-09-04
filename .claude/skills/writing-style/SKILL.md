---
name: writing-style
description: Run Memoria's writing-style analysis - the author-launched pass in which a model reads samples of the author's own writing and proposes observations about how they write, for the author to confirm or change in Settings. Use when the author says "analyse my writing style", "work out my style from these", "run the style analysis", or invokes /writing-style. Not for drafting prose - a writing session calls writing_style() itself.
---

# The writing-style analysis

The writing style (`style/writing-style.md`, ADR-0009) is book-wide craft
direction every writing agent receives: the author's own prose about how
their book is written, plus observations confirmed from an analysis of their
own writing. This skill runs the analysis. **It writes no style.** Everything
it produces is a proposal the author confirms, changes or discards under
Settings > Writing style in the app; only that act puts words in the file.

## Before anything: ask

Call `style_status()` and show the author what it says. Two things matter:

- **the samples** - how many sources they chose and documents they uploaded.
  If both are zero there is nothing to read: tell the author to choose some
  under Settings > Writing style, and stop.
- **observations already proposed** - a number above zero means a previous
  run is still waiting for the author in Settings. Say so; running again
  over the same samples replaces those proposals with new ones.

**Then ask whether to run it, and wait.** The pass reads every sample with a
model, and part 08 §12.1's rule is that nothing needing a model runs unasked.

## The brief

Call `style_brief()` **once** and keep it. It carries the analysis prompt,
what the style already says, and every sample verbatim - the chosen sources'
paragraphs (the first eighty of each; it says when it truncated) and every
uploaded document.

Do not paraphrase the prompt, summarize it, or substitute instructions of
your own; it is served verbatim so that there is exactly one version of it.
Do not propose again what the style already says.

## Reading and recording

1. Read every sample in full before writing anything.
2. Write the observations the brief asks for - between eight and fifteen,
   each with its `aspect`, its `observation` phrased as a directive a writer
   can follow, and an `example` quoted **verbatim** from a sample. The
   example is checked: one that does not occur in the samples exactly as you
   quote it is refused, and that is the right outcome.
3. `style_record(observations=[...])`, the whole batch in one call.
4. Read the outcome. Rejected elements name their reason; re-send those
   **once**, corrected. Do not re-send accepted ones - a second batch under
   the same samples replaces the first.

## The report

Close with the count accepted and, for each rejected observation you did not
re-send, its reason. Then, in as many words:

> Nothing has been written to the writing style. Open Settings > Writing
> style to confirm, change or discard each observation; only what you
> confirm reaches the writers.
