# Answer-key protocol

Forces issue #9's "how a cross-reference's target-side passage gets located",
the third of M0's decisions. Implemented by `src/memoria/editions.py` and
`src/memoria/answer_key.py`; the artifact is `benchmark/answer-key.yaml`.

## What the key is for

A cross-reference (issue #8) is a labelled pair: **this journal passage became
that book passage**, recorded by the 1906 editors in their own footnote.

The benchmark uses the pair in one direction. The book paragraph is the
**probe** — the harness hands it to retrieval and asks for evidence — and the
journal passage is the **correct answer** (part 15 §43.14, part 06 §8.3). That
is Memoria's actual job in miniature: here is manuscript prose, find what in the
archive it came from.

Issue #8 delivered the journal side, mechanically and trustworthily: a `SRC-` ID
and paragraph anchor per link, straight from the editors' footnotes. It could not
deliver the other side, and this document is how the other side is delivered.

## The premise that changed

`RECON.md` §4 concluded the target side was unresolvable:

> the 364 usable cross-references are ground truth for *which journal passage was
> reused in which book*, but resolving them to a location in our Walden/Week text
> requires **fuzzy text matching**, not a page-number join.

That is true of the texts held here and false as a statement about the world. The
journal volumes in this corpus are **Volume VII and VIII of 20** of the 1906
Manuscript Edition, so `[_Week_, p. 319]` cites page 319 of **volume 1 of the same
set**. Both that set and the Riverside set the `Riv.` numbers cite are digitized
page by page. The page numbers were never unresolvable; the cited editions were
simply not held.

Issue #9 was written on the old premise, and asked for a human adjudication
protocol, a hand-resolved pilot of ~30 links, a per-link time cost, and an escape
hatch if 364 proved unaffordable. **None of that is what this slice does**, and the
issue was rewritten rather than executed. What survives unchanged is the reason the
issue existed: the key must not be produced by the machinery it will be used to
score.

## What identifies a target passage

Three things, in this order.

1. **The cited page, in the cited edition.** Read out of the scanned volume by
   printed page number.
2. **That page located in the held text.** The scan and the Gutenberg text are two
   printings of one book, so this is an alignment between near-identical texts, not
   a paraphrase judgement. Every distinctive five-word sequence of the page votes
   for one alignment offset and the winner is taken, which survives OCR damage: a
   page needs only a fraction of its words to come through intact.
3. **A second, independent edition agreeing.** Almost every footnote cites the same
   passage twice, once by Manuscript page and once by Riverside. Those are
   different printings, separately scanned, separately OCR'd, separately anchored.
   Agreement between them is what corroborates a target without anyone reading for
   similarity.

The target recorded is the **span of held paragraphs the cited page covers** —
typically three, and 16 at the widest. A page is what the editors cited, and a
page starts and ends mid-paragraph, so the paragraphs it touches are the honest
unit.

**A citation wider than two pages is not a target.** A passage lives on a page
and sometimes crosses onto the next; seventeen footnotes cite more than that —
`[See _Week_, pp. 356-420; Riv. 442-518.]` runs to 65 pages — and what they
record is that a stretch of journal became a stretch of book. True, and not a
passage-level link. It matters because of the direction the benchmark runs in:
the target span is the **probe**, so scoring that row would be handing retrieval
a third of *A Week* and asking it to find one journal entry. Those rows are kept
with a `not-passage-level` status and are not scored.

The key reports `median_span_paragraphs`, `mean_span_paragraphs` and
`max_span_paragraphs`. All three, because the median alone concealed exactly the
problem above: it read 3 while one row spanned 198.

## What may not be done

**Narrowing within the cited page by comparing the journal passage against
candidate book paragraphs is forbidden.** A page holds several paragraphs and only
one of them is usually the reused passage, so this is tempting and would make the
key tighter. It is exactly the operation the benchmark measures — similarity
between archive evidence and manuscript prose — and using it to build the key
would make retrieval recall a measure of the system agreeing with itself.

Also forbidden, for the same reason: `search_text`, the FTS5 index, gathered sets,
appearances, and any model. Nothing in `editions.py` or `answer_key.py` imports
them. The audit targets are deliberately left out of the index as well
(`docs/normalized-record-schema.md`, "Not indexed"), so a probe cannot retrieve
itself.

The cost of the rule is accepted openly: the target is page-sized rather than
paragraph-sized, and the key reports how wide — median, mean and max.

## Two checks that are not the same check

**Within a volume, page order.** Every printed page of every volume is anchored,
not just the cited ones. Page numbers ascend, so the offsets they map to must
ascend too; a page that breaks the order was mis-anchored and is dropped. Both
Manuscript volumes need no page dropped; the Riverside scans need five between
them.

**Between volumes, the citation.** For a link, the Manuscript page and the
Riverside page must place the passage in the same part of the held text. The two
page-number series drift apart slowly — about three Riverside pages over four
hundred — so the drift is fitted per work (two parameters over a hundred-odd
distinct page pairs) and the residual is what must be small. The fit's
coefficients are written into the key so the correction is inspectable.

**Neither check catches a constant error, and one was there.** Three of the four
scanned volumes number each leaf one page ahead of the number printed on it, and
the fourth does not. A constant offset shifts every citation into a volume
equally, so the drift fit absorbs it into its intercept and reports agreement. It
was caught by reading one sampled row by eye, and it had put 243 of 360 rows one
page late.

The fix is a third check, independent of both: **the running head**. Nearly every
page carries its own printed number beside the chapter title — "SUNDAY 53", "46
WALDEN" — so the page states what page it is. The offset is measured from those
heads per volume and recorded in the key as `printed_page_offset`, with the vote
count behind it. A volume whose pages never say what they are is refused outright
rather than served unverifiable.

This is the general lesson of the slice: **two checks that share an assumption are
one check.** The eye that found it is not a formality, which is why the spot check
below is part of the deliverable rather than a nicety.

## What the two-edition check does not certify

Stated because the check reads stronger than it is. **The tolerance is coarser
than the thing it admits.** Two Riverside pages of slack guard a target that is
one or two pages wide, so a per-link error of a single page passes it — and a
one-page error is not hypothetical here: it is the exact class of mistake that
had put 243 of 360 rows one page late. The running-head check closed that
instance because the error was *constant across a volume*; nothing in the three
checks looks at a page-sized error on one link.

The tolerance is also chosen after seeing the data rather than derived. Of the
349 links where both editions anchor, the median residual is 0.42 pages and only
three exceed 1.5; the worst admitted is 1.78 and the single rejection is 2.16.
That spread is what makes the alignment trustworthy in bulk. It is not what makes
2.0 the right line — the line sits in a 0.38-page gap, and a threshold of 1.9 or
2.1 would have admitted and rejected the same rows for no better reason.

So what remains unguarded is a per-link error of a page or less, and the only
thing that looks at it is the spot check below.

## How uncertainty and rejection are recorded

Every one of the 379 links has a row. A link that was not admitted keeps its
row, its citation and a `note` saying why, because coverage that is not in the
artifact is coverage nobody checks.

| `status` | Meaning |
|---|---|
| `resolved` | Both editions anchored and agree. Scored. |
| `editions-disagree` | Both anchored; the Riverside page sits further from the Manuscript page than the tolerance allows, once drift is taken out. Not scored — this is the check doing its job. |
| `not-passage-level` | The footnote's Manuscript pages span more than two, so it cites a stretch of the book rather than a passage. Not scored — the span would be the probe, and a probe that size measures something else. |
| `no-page-pair` | The footnote gives no Manuscript/Riverside page pair for this work: a passing mention, a Roman-numeral front-matter page, or a `Riv.` belonging to a different work in the same footnote. Nothing to corroborate against. |
| `unanchored` | A cited page could not be placed — its printed number was never read off the leaf (the gaps all have plate leaves interleaved, so there is nothing safe to interpolate from). |

A resolved row also carries `residual_pages`, how far the two editions actually
were, and `manuscript_votes`, how strongly its page anchored. Neither is a
confidence score invented for the occasion; both are the measurements the
admission rule was applied to.

## Coverage

| | Week | Walden | Total |
|---|---|---|---|
| Cross-references landing on the work | 257 | 122 | 379 |
| **Resolved** | 239 | 109 | **348** |
| `not-passage-level` | 9 | 8 | 17 |
| `editions-disagree` | 0 | 1 | 1 |
| `no-page-pair` | 5 | 1 | 6 |
| `unanchored` | 4 | 3 | 7 |

**348 of 379**, or 92%. Against all 668 cross-references — including the 289
citing *Excursions*, *Cape Cod*, *The Service* and *Maine Woods*, which the corpus
does not hold — coverage is 52%, in place of `poc-plan.md` §1's projected 364 of
628 (58%).

The single `editions-disagree` row is `src-000396-p66/Walden`
(`[_Walden_, p. 292; Riv. 408, 409.]`), where the two page numbers are 2.2 pages
apart after drift correction.

## What this key is, and is not, evidence for

Recorded here because the number it feeds will be read as deciding something, and
it decides less than it looks like it does.

Retrieval recall@10 over these links measures **retrieval when wording diverges**
— a real capability, and one a modern archive needs: prose about an event rarely
repeats the words of the evidence behind it. But the *distribution* here is
Thoreau deliberately rewriting journal into literature, which is almost certainly
harder and differently shaped than "the same event, described differently". The
capability transfers; the difficulty does not.

So this benchmark is a **stress case, good for detecting gross failure, and a poor
instrument for setting thresholds.** `poc-plan.md` §6 risk 4 anticipates half of
this — that the task may be hard enough to swamp the signal — but frames it as
difficulty rather than as measuring a task the eventual archive will not have.

Two consequences:

- The embeddings go/no-go pre-registered at M1 (issue #14, `open-problems.md` §2.2)
  should say what a poor score licenses. A bad number here is evidence that lexical
  search fails under paraphrase; it is not a measurement of how much retrieval a
  factual, timeline-shaped archive needs.
- Harness numbers two and three do not have this problem. Gathered-set recall
  measures index completeness and promotion miss rate measures entity resolution
  against `RECON.md`'s 43 recipients — both squarely the People/Timeline/Events
  material a modern archive is made of.

## The spot check

`docs/answer-key-spot-check.md`, regenerated by `scripts/spot-check.py` — six
rows, fixed seed, three per work. The script refuses to overwrite verdicts that
have been filled in, because the verdicts are the only part of that file a
machine did not write.

For each row: does the page the footnote cites hold the text the key names? It is
a comparison between two printings of one book, so it needs no familiarity with
Thoreau and no judgement about his rewriting.

It is not a formality. The one-page offset above was found this way and by nothing
else.
