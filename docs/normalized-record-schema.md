# Normalized record schema

Forces `docs/open-problems.md` §6's "the normalized record schema, and how
editorial apparatus is represented" for the PoC's first source type
(journals). Implemented by `src/memoria/normalize.py`, with year resolution
(the `recorded_date`/`event_date`/`date_confidence` fields below) by
`src/memoria/year_resolution.py` (issue #4).

## What a normalized record is

A normalized record is one Markdown file per natural documentary boundary
(part 05 §5.2 of the build plan) — for the journals, one dated entry. Each
record gets a stable `SRC-` ID (part 04 §4) and stable paragraph anchors
(part 05 §5.3), so a citation like `SRC-000184 ¶17` keeps meaning forever.

## Frontmatter fields

```yaml
---
id: SRC-000184
source_type: journal
recorded_date: Oct. 22.
event_date: Oct. 22., 1845
date_confidence: inferred
contemporaneous: true
original_file: raw/gutenberg/57393-journal-01/pg57393.txt
original_locator: "Journal I, entry dated Oct. 22."
---
```

| Field | Meaning |
|---|---|
| `id` | Stable `SRC-NNNNNN` identifier (six digits, zero-padded — part 04 §4's `SRC-000184` form; the `SRC-0184` seen in the desktop mockup is a noted divergence, part 19 §19.11). Assigned sequentially: volume order, then entry order within the volume. Stable across re-runs over unchanged input because the assignment is a deterministic function of that input, not a hash or a counter file. |
| `source_type` | `journal` for this slice. Other source types (letter, email, ...) are later slices. |
| `recorded_date` | The date heading text, verbatim, exactly as it appears in the source — never rewritten by year resolution. |
| `event_date` | `recorded_date` with its resolved year appended (`"Oct. 22., 1845"`), or unchanged from `recorded_date` where the heading already states its own year, or where no year could be resolved at all (`date_confidence: chapter-only` — no invented date). Journals have no retrospective/contemporaneous date split within one entry, so before year resolution `recorded_date` and `event_date` were identical; year resolution (`src/memoria/year_resolution.py`, issue #4) is what makes them diverge. |
| `date_confidence` | `exact` only where a weekday in the heading confirmed the resolved year against a real calendar; `inferred` where the year came from an unambiguous chapter heading, an explicit year in the entry heading itself, or position within a multi-year chapter, without a weekday to confirm it; `chapter-only` where no chapter marker precedes the entry at all, so no year context exists (RECON.md §3's description of J02 Chapter I's undated opening fragments — none of the corpus's 558 records currently exercise this branch, since `normalize_journals` discards those fragments before this stage; see "Known data loss" below). A weekday that does not match any candidate year is never silently accepted as `exact`; `memoria normalize` prints it as a warning instead. |
| `contemporaneous` | `true` for journal entries — a diary entry is contemporaneous evidence by definition (part 05 §6). |
| `original_file` | Path to the raw source, relative to the evidence root (`MEMORIA_EVIDENCE_ROOT`) — the same convention `manifest.yaml` and `memoria validate` use, e.g. `raw/gutenberg/57393-journal-01/pg57393.txt`. |
| `original_locator` | Human-readable pointer into the original, e.g. `"Journal I, entry dated Oct. 22."`. |

## Paragraph anchors

Each paragraph in a record's body is preceded by an HTML anchor, numbered
positionally within the record:

```markdown
<a id="src-000184-p17"></a>

I called Bob that evening...
```

Anchors are stable across re-runs for the same reason IDs are: paragraph
splitting (on blank-line boundaries) is a deterministic function of the
entry text. `NormalizedRecord.anchor_id(n)` is the single source of this
`f"{id.lower()}-p{n}"` form — downstream slices citing a paragraph should
call it rather than re-deriving the anchor string independently.

## Entry boundaries

Journal entries open with a line-initial italic date heading — re-verified
directly against the raw corpus (see "Deviation from RECON.md's date-heading
count" below) rather than trusted from RECON.md §3's summary. The closed set
of forms matched: `_Oct 22._`, `_Jan. 24. Sunday._`, `_Sept. 29, 1842._`,
`_May 3-4._`, `_July 10 to 12._` (a "to"-range), `_Dec. 16, 17, 18._` (a
comma list), the two bare `_Dec._` / `_Jan._` month-only headings, and a
trailing qualifier that is either a weekday, a place (`_Nov. 29.
Cambridge._`), or a weekday plus a lowercase second word (`_July 20. Sunday
morning._`).

`normalize_journals` splits the raw text at every line matching that form,
after first stripping:

- the Gutenberg license boilerplate, Transcriber's Note, Torrey's
  Introduction, Contents/Illustrations lists — all of it front matter
  preceding the first date heading, discarded by construction;
- the Gutenberg trailing license (outside the `*** END OF ... ***` marker);
- each volume's **back matter** — the printer's colophon and Torrey's
  editorial footnote apparatus, between the `END OF VOLUME` line and the
  Gutenberg END marker. Without this cut, the volume's *last* entry
  absorbed the entire back matter (500+ footnotes) as `contemporaneous:
  true` — a defect caught in review round 1 on PR #48 and fixed here.

A paragraph that is nothing but chapter apparatus — a bare Roman numeral
(`II`), a bare year or year range (`1838`, `1845-1847`), or an age marker
(`(ÆT. 20-21)`) — is filtered out of entry bodies. These land inside an
entry's raw lines because a chapter boundary falls *between* two entries,
not at one, so without the filter the marker attaches to the trailing
paragraphs of the preceding chapter's last entry.

**Editorial apparatus** (footnote markers, bracketed editorial spans,
running section titles like `SOLITUDE`) is left inline for this slice —
segregating it into separate retrospective-editorial records is a later M0
step (part 16), not this one. Quote characters are normalized (curly →
straight ASCII) so a search phrase matches regardless of which volume's
convention produced it (RECON.md §6.1: J01/Familiar Letters use straight
quotes, J02 uses curly).

## Known data loss: J02's undated opening fragments

Everything before a volume's first date heading is discarded by
construction (see above). For J01 that is genuinely front matter. For J02
it also deletes ~1,000 lines of undated Thoreau transcript-book extracts
that open Chapter I (RECON.md §3: "J02 Chapter I ... opens ... with undated
fragments separated by `*   *   *   *   *` dividers ... transcript-book
extracts, not dated entries," needing `date_confidence: chapter-only`).
Normalizing those fragments into their own records is out of scope for this
slice (dividers, not date headings, delimit them, and RECON explicitly
scopes their `chapter-only` confidence to year resolution). Named here so
it is not silently assumed away.

## Deviation from RECON.md's date-heading count

RECON.md §3 states 299 (J01) and 149 (J02) date headings — 448 total.
Mechanically re-implementing RECON's own stated detection rule (line-initial
italic date, closed set of month/weekday/qualifier forms) against the raw
corpus finds more: **401 (J01) and 157 (J02) — 558 total.**

This was checked twice, independently:

- **Implementer's pass (554 total).** Manual spot-checking of every extra
  heading found no false positives, and one concrete counter-example to
  RECON's own claim: J02's Chapter I (RECON.md §3, "has no date headings at
  all") in fact contains 22 line-initial date headings within RECON's own
  stated line range for that chapter (June–Nov 1850 entries after the
  undated opening fragments noted above).
- **Independent review pass, round 1 on PR #48 (558 total).** Confirmed the
  implementer's finding mechanically — every match is preceded by a blank
  line, RECON's own J02 `_Mon. N._` count matches exactly, and the gap
  traces to RECON's counter requiring an abbreviating period and so missing
  unabbreviated months (`May`, `June`, `July`, `March`, `April`) — and
  independently reproduced the Chapter I falsification. The review also
  caught a **recall bug in the implementer's regex**: `_July 10 to 12._`,
  `_Nov. 29. Cambridge._`, `_July 20. Sunday morning._`, and `_July 28.
  Monday morning._` are genuine headings the "to"-range, place-qualifier,
  and "weekday + second word" forms above were added to cover, taking the
  count from 554 to 558.

`tests/test_normalize.py`'s `TestAgainstTheRealEvidenceCorpus` asserts the
mechanically verified count (558) alongside structural invariants — every
matched heading is preceded by a blank line, no line-initial
`^_<Month>`-prefixed line in the raw body is left unmatched (the recall
check that would have caught the regex bug above automatically), and no
entry carries back-matter markers — rather than a count in isolation.
