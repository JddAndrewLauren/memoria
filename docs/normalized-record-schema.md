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
| `source_type` | `journal`, `letter` (the 130 *Familiar Letters*, issue #6), or `book` (the two audit targets, issue #9 — see "The audit targets" below). Other source types (email, ...) are later slices. |
| `recorded_date` | The date heading text, verbatim, exactly as it appears in the source — never rewritten by year resolution. Empty for the 29 undated opening fragments of J02's Chapter I (`date_confidence: chapter-only`), which have no date heading to quote; see "J02's undated opening fragments" below. |
| `event_date` | `recorded_date` with its resolved year appended (`"Oct. 22., 1845"`), or unchanged from `recorded_date` where the heading already states its own year, or where no year could be resolved at all (`date_confidence: unresolved` — no invented date). Empty for the `chapter-only` fragments: their chapter scopes them to 1850, but `event_date` is a date and they have no day, so the field is left empty rather than filled with a year pretending to be one. The chapter's year stays recoverable from `original_locator`. Journals have no retrospective/contemporaneous date split within one entry, so before year resolution `recorded_date` and `event_date` were identical; year resolution (`src/memoria/year_resolution.py`, issue #4) is what makes them diverge. |
| `date_confidence` | `exact` only where a weekday in the heading confirmed the resolved year against a real calendar; `inferred` where the year came from an unambiguous chapter heading, an explicit year in the entry heading itself, or position within a multi-year chapter, without a weekday to confirm it; `chapter-only` where the record has **no date heading of its own**, so its enclosing chapter is the only date context there is — RECON.md §3's reading of the value exactly ("scoped to 1850, no day"), and the 29 undated opening fragments of J02's Chapter I are the records that carry it (see below); `unresolved` where a resolution was attempted and produced nothing — a dated entry with no chapter marker before it anywhere (no record in the corpus: both volumes open with a chapter heading), and all 130 letters: their datelines do carry an explicit year (see the `dateline` row below), but year resolution is a separate M0 step from letters parsing, so that year is left unparsed rather than absent. A weekday that does not match any candidate year is never silently accepted as `exact`; `memoria normalize` prints it as a warning instead. `published` is the audit targets' value: a book's date is its year of publication — a documentary fact about the volume, not a year resolved out of the text — so none of the four resolution outcomes describes it honestly. |
| `contemporaneous` | `true` for journal entries — a diary entry is contemporaneous evidence by definition (part 05 §6). |
| `original_file` | Path to the raw source, relative to the evidence root (`MEMORIA_EVIDENCE_ROOT`) — the same convention `manifest.yaml` and `memoria validate` use, e.g. `raw/gutenberg/57393-journal-01/pg57393.txt`. |
| `original_locator` | Human-readable pointer into the original, e.g. `"Journal I, entry dated Oct. 22."`; for an undated fragment, the chapter and its position within the chapter's opening run, e.g. `"Journal II, Chapter I, undated fragment 3 of 29"`. |

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

## Whitespace policy

`normalize_journals` never reflows a paragraph's whitespace — a paragraph
is `.strip()`ped at its ends and otherwise kept exactly as the raw source's
line breaks and indentation produced it (`_paragraphs` in normalize.py).
Evidence text is sacred: nothing here rewrites it, so a quoted verse's own
line structure (e.g. SRC-000003's stanza from *Ibid.*) survives into the
normalized record unchanged.

The later editorial-extraction step (`extract_editorial_apparatus`,
issue #5, `src/memoria/editorial.py`) *does* reflow whitespace to single
spaces, but **only for a paragraph an editorial span (a footnote marker,
a standalone bracketed aside, or a sentence-completing interpolation) was
actually excised from** — closing up the artifact that excision itself
leaves behind (a doubled space, a stray space before punctuation, e.g.
"Walked to Concord , 10 miles." → "Walked to Concord N. H., 10 miles."). A
paragraph containing no bracketed span at all is left byte-identical to
what `normalize_journals` produced, mid-paragraph newlines included — this
was a defect (issue #55) where the reflow ran unconditionally on every
evidence paragraph regardless of whether anything was actually excised
from it, and a pre-existing space before punctuation in the raw text
itself (not an excision artifact) was wrongly closed up along with it.

## J02's undated opening fragments

Everything before a volume's **first chapter heading** is discarded by
construction — front matter, in both volumes. Everything between that
chapter heading and the volume's first *date* heading is not. For J01 it is
only the chapter's age marker, and yields nothing. For J02 it is ~1,000
lines of undated Thoreau transcript-book extracts opening Chapter I
(RECON.md §3: "J02 Chapter I ... opens ... with undated fragments separated
by `*   *   *   *   *` dividers ... transcript-book extracts, not dated
entries," needing `date_confidence: chapter-only`).

An earlier pass of this slice discarded them too, since dividers rather
than date headings delimit them and the entry splitter had no boundary rule
for a record with no heading. They are now recovered: **29 records,
`SRC-000402`–`SRC-000430`, holding 129 paragraphs.**

**The divider is the boundary.** A record is bounded by a natural
documentary boundary (part 05 §5.2); with no date heading available, the
divider the 1906 edition sets between one extract and the next is the only
boundary the source offers. This applies *only* in a volume's undated
opening: the same dividers also separate thoughts inside dated entries (156
in J02, 581 in J01), where the date heading is the boundary and a divider
is not one.

**They carry no date.** `recorded_date` and `event_date` are both empty and
`date_confidence` is `chapter-only`. Chapter I scopes them to 1850, which
`original_locator` records; the source gives no day, and `event_date` is a
date, not a range, so it is left empty rather than filled with something
the source never said.

**The chapter heading itself is not evidence.** The chapter's numeral (`I`)
and its year line (`1850 (ÆT. 32-33)[1]`) are apparatus. They are excluded
from the first fragment, which is why that line's footnote marker `[1]`
stays unlinked (see `docs/editorial-record-schema.md`).

Recovering these fragments is what makes `chapter-only` a value the corpus
actually carries, and it links 25 footnotes — J02's footnotes 2–26 — whose
markers previously fell outside every record, restoring 17 cross-references
with them (`docs/cross-reference-schema.md`).

## Deviation from RECON.md's date-heading count

RECON.md §3 states 299 (J01) and 149 (J02) date headings — 448 total.
Mechanically re-implementing RECON's own stated detection rule (line-initial
italic date, closed set of month/weekday/qualifier forms) against the raw
corpus finds more: **401 (J01) and 157 (J02) — 558 total.** (558 *date
headings*, and so 558 dated records; the 29 undated fragments above bring
the journals to 587 records in total.)

This was checked twice, independently:

- **Implementer's pass (554 total).** Manual spot-checking of every extra
  heading found no false positives, and one concrete counter-example to
  RECON's own claim: J02's Chapter I (RECON.md §3, "has no date headings at
  all") in fact contains 22 line-initial date headings within RECON's own
  stated line range for that chapter (June–Nov 1850 entries after the
  undated opening fragments above — it is the chapter's *opening* that is
  undated, not the chapter).
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
mechanically verified count (558 dated records) alongside structural
invariants — every
matched heading is preceded by a blank line, no line-initial
`^_<Month>`-prefixed line in the raw body is left unmatched (the recall
check that would have caught the regex bug above automatically), and no
entry carries back-matter markers — rather than a count in isolation.

## Letters (issue #6)

The second source type: the 130 letters of *Familiar Letters*
(`raw/gutenberg/43523-familiar-letters/pg43523.txt`), `source_type: letter`.
`normalize_letters` splits on the line-initial `TO <recipient>.` heading
RECON.md §5 documents — re-verified directly against the raw corpus: exactly
130 headings, 43 distinct verbatim strings, matching RECON's own counts
exactly. IDs continue the journals' `SRC-` sequence (`start_id`, default
`len(journal_records) + 1` when the CLI combines both source types — part
04 §4's "volume order, then entry order").

### Letter-specific frontmatter fields

Alongside the shared fields journals also carry, a letter record's
frontmatter adds three structured fields the acceptance criteria name
(`recipient`, `dateline`, `salutation`) — `NormalizedRecord.recipient` /
`.dateline` / `.salutation`, `None` and omitted from frontmatter for
journal records:

| Field | Meaning |
|---|---|
| `recipient` | The heading text after `TO `, preserved **verbatim** — no stripping, no merging. This is deliberate: R. W. Emerson's four location forms (`(AT CONCORD)`, `(AT NEW YORK)`, `(IN ENGLAND)`, no location) and the Thoreau family's shared surname are the corpus's alias-resolution hazard material (§7), and merging them here would destroy it before M2 ever sees it. |
| `dateline` | The letter's indented dateline paragraph (e.g. `CONCORD, October 27, 1837.`) — the first substantive paragraph after the heading (skipping a leading editorial annotation like `[The first of many letters.]`), if and only if it is indented; empty when the letter has none, rather than scanning further and risking its closing signature block instead (review round 1 on PR #52's blocking defect 1: `SRC-000002`/`SRC-000129` used to get `"TAHATAWAN."`/`"Yrs. in great haste, HENRY D. THOREAU."`). Unlike the journals, letter datelines already carry an explicit year — still landing here verbatim rather than parsed, since year resolution is a separate M0 step (part 16) from letters parsing. |
| `salutation` | The opening address (`DEAR HELEN,--`, `MR. BLAKE,--`), extracted non-destructively from the body's first paragraph — the body keeps that paragraph in full, so nothing is lost by also exposing this field. |

`recorded_date` / `event_date` land as the dateline text, same as `dateline`
(the journals' pattern of landing the heading text verbatim). `contemporaneous`
is `true` — a letter, like a diary entry, is evidence contemporaneous with
when it was written. `date_confidence` is `unresolved` for every letter
record this slice produces, the same value the journals slice produces and
for the same reason: parsing the dateline's already-explicit year into a
resolved date is year-resolution work, scoped to a later M0 step (part 16),
not this one.

### Scope: editorial narrative between letters is left inline

Sanborn's connective prose between two letters (`This singular letter was
addressed to John Thoreau...`) is not segregated out of the preceding
letter's body in this slice — the same scope decision issue #3 made for
footnote markers and bracketed editorial spans within journal entries
("left inline for this slice"). Segregating all editorial voice into
separate retrospective-editorial records is part 16's dedicated
"editorial-voice segregation" build step, distinct from "letters parsing."
**Sanborn's Introduction itself is different** and is excluded by
construction: everything before the first `TO ` heading is discarded, the
same way the journals discard everything before their first date heading.

Issue #56 is that "editorial-voice segregation" step for the letters -
but scoped, like #5 was for the journals, to *bracket-delimited* apparatus
(footnote markers and bodies, bracketed asides, interpolations - see
`docs/editorial-record-schema.md`). Sanborn's unbracketed connective
prose between letters, described above, is a different shape of
editorial voice and stays inline; #56 did not extend to it.

### Back matter: the General Index and trailing footnotes

The volume's General Index (`GENERAL INDEX`, after the last letter) is cut
the same way the journals cut `END OF VOLUME` back matter —
`_extract_body_lines` takes a `back_matter_marker` parameter so both
volumes share the same START/END-marker-and-cut logic. A `FOOTNOTES:`
block — Sanborn's endnotes for the preceding stretch of letters — can land
inside an entry's own lines the same way the journals' back matter used to
land inside their last entry (PR #48 review round 1); `_split_letters`
trims every letter's lines at a trailing `FOOTNOTES:` marker, not just the
last letter's, since a footnote block is never part of the letter itself
wherever it lands.

**"Editorial narrative is left inline" is not uniformly true**, and #5
should not assume it is (review round 1 on PR #52): `_trim_trailing_footnotes`
cuts a letter's lines at its first `FOOTNOTES:` marker, so any connective
narrative that happens to fall *after* a `FOOTNOTES:` block within that
same span is silently dropped along with the footnotes, while narrative
falling *before* one (the ordinary case — narrative between two letters
elsewhere in the volume) is kept. This is a side effect of trimming at the
first marker found, not a deliberate distinction between two kinds of
narrative.

## Recipients table (issue #6)

`recipients_table(records)` maps each verbatim `recipient` string to the
`SRC-` IDs of the letters naming them — "a real, checkable table ... not a
list in a comment" (issue #6). `memoria normalize` writes it as YAML to
`sources/normalized/recipients.yaml` via `write_recipients_table`. It has
43 entries against the real corpus, matching RECON.md §5's "43 distinct
recipients" exactly.

**Not person-level ground truth on its own.** The 43 rows are 43 distinct
verbatim *strings*, over roughly 25 actual people — they include artefacts
of the source text alongside genuine location-form variants: a stray-comma
duplicate (`DANIEL RICKETSON, (AT NEW BEDFORD).` vs `DANIEL RICKETSON (AT
NEW BEDFORD).`), an `(AT MILTON)` / `(IN MILTON)` preposition variant, and
two footnote-marked Emerson headings alongside his three genuine location
forms. This is correct as issue #6 specifies it (verbatim, unmerged — the
alias-resolution hazard material §7 wants intact), but M2's
promotion-miss-rate scoring will need an alias layer on top of this table
before it is ground truth at the level of a *person*, not a heading string.

## Weekday checksum: reconciled against RECON.md (issue #4)

RECON.md §3 estimates "roughly 100 headings carry a weekday." Mechanically
counting weekday-bearing headings against the raw corpus finds more:
**152**, of which **150 confirm** against a real calendar the year
resolution otherwise assigns from the chapter and position (giving
`date_confidence: exact` for those 150). The remaining 2 are genuine
editorial/transcription
discrepancies in the source, not parsing bugs — verified by hand against
the raw text and a real calendar:

- `SRC-000332`, `raw/gutenberg/57393-journal-01/pg57393.txt:10062` —
  `"_Sept. 5. Saturday._"`; the source text does read "Saturday", but
  Sept. 5, 1841 (the chapter's single candidate year) was actually a
  Sunday.
- `SRC-000493`, `raw/gutenberg/59031-journal-02/pg59031.txt:5746` —
  `"_May 6. Monday._"`, under the `MAY, 1851` chapter; May 6, 1851 was
  actually a Tuesday.

Both are surfaced as warnings by `resolve_years()` (printed by `memoria
normalize`) rather than silently accepted as `exact` — RECON.md §3's own
prediction: "where it does not [match], it flags a genuine editorial
problem worth surfacing rather than guessing."

Final counts across all 587 journal records: **exact=150, inferred=408,
chapter-only=29** (`tests/test_year_resolution.py`'s
`TestAgainstTheRealEvidenceCorpus` asserts this distribution, alongside the
invariant that no record is `exact` without a weekday in its heading, and
that a `chapter-only` record carries neither a `recorded_date` nor an
`event_date`). The 130 letters are `unresolved`, for 717 records in all.


## The audit targets

Issue #9 normalizes the two published works the journals' cross-references
point at — *A Week on the Concord and Merrimack Rivers* (Gutenberg 4232) and
*Walden* (Gutenberg 205) — under `source_type: book`.

They exist for one reason: the answer key needs a stable `SRC-` ID and
paragraph anchor **on the target side**. The journals and letters had both
from issues #3 and #6; the books had neither, and no other slice covered
them.

**One record per chapter.** A chapter is the natural documentary boundary
here (part 05 §5.2) the way a dated entry is for a journal — it is what the
work declares in its own Contents. That yields 27 records,
`SRC-000718`–`SRC-000744`: *A Week*'s 8 (`CONCORD RIVER`, `SATURDAY` …
`FRIDAY`), *Walden*'s 18, and *On the Duty of Civil Disobedience*, which
Gutenberg 205 carries in the same file and which is kept rather than dropped
so the file normalizes whole. No cross-reference cites the essay.

**Two extra frontmatter fields**, on book records only, the same "written
only when set" rule the letters' `recipient`/`dateline`/`salutation` follow:

| Field | Meaning |
|---|---|
| `work` | `Week` or `Walden` — the value a cross-reference's `target_work` joins against. |
| `chapter` | The chapter title verbatim, as the volume's Contents gives it. |

**Chapter headings are a closed set matched in document order**, the same
discipline `DATE_HEADING_RE` applies to date headings, and necessary for the
same reason. A generic "line is all capitals, flush left" rule breaks twice
on this corpus:

- `THE INWARD MORNING` (`pg4232.txt:8936`) is a poem title inside
  `WEDNESDAY`, and would become a ninth chapter of *A Week*;
- `ON THE DUTY OF CIVIL DISOBEDIENCE` appears flush left on *Walden*'s title
  page (`pg205.txt:36`) as well as at its real heading (`pg205.txt:9421`), and
  the title-page line would start the last chapter 9,385 lines early,
  swallowing all 18 of *Walden*'s own chapters.

Both are regression tests in `tests/test_normalize.py::TestTargetNormalization`.

**`contemporaneous: false`.** *A Week* (1849) and *Walden* (1854) are works
Thoreau built *from* the journals — the relation the cross-references label
and the benchmark scores. This flag is what lets a date-leakage test tell the
two sides apart (part 05 §6).

**Not indexed.** `memoria rebuild` writes the book records but does not put
them in `.memoria/index.db`. The index is the *evidence* retrieval surface,
and a book paragraph is the benchmark's **probe** (part 06 §8.3): indexing
the targets would let a search for a book paragraph return that same
paragraph as its own top hit, which is exactly the self-agreement failure the
answer key exists to prevent. Appearances over the audit targets (part 06
§8.11) are M2's, and get their own structure.

`"THE END"` sits between *Walden*'s last paragraph and the essay's heading
rather than after both, so it cannot be used as a back-matter cut; it is
dropped as a paragraph instead.
