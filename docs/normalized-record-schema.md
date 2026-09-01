# Normalized record schema

Forces `docs/open-problems.md` §6's "the normalized record schema, and how
editorial apparatus is represented" for the PoC's first source type
(journals). Implemented by `src/memoria/normalize.py`.

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
event_date: Oct. 22.
date_confidence: unresolved
contemporaneous: true
original_file: raw/gutenberg/57393-journal-01/pg57393.txt
original_locator: "Journal I, entry dated Oct. 22."
---
```

| Field | Meaning |
|---|---|
| `id` | Stable `SRC-NNNNNN` identifier (six digits, zero-padded — part 04 §4's `SRC-000184` form; the `SRC-0184` seen in the desktop mockup is a noted divergence, part 19 §19.11). Assigned sequentially: volume order, then entry order within the volume. Stable across re-runs over unchanged input because the assignment is a deterministic function of that input, not a hash or a counter file. |
| `source_type` | `journal` for this slice. Other source types (letter, email, ...) are later slices. |
| `recorded_date` / `event_date` | **This slice does not resolve years** (part 16's M0 scopes year resolution as a separate, later build step — RECON.md's chapter/weekday-checksum work). The date heading text lands here verbatim, exactly as the brief specifies: "Dates land as whatever the heading says; the year arrives in the next slice." Journals have no retrospective/contemporaneous date split within one entry, so `recorded_date` and `event_date` are identical for now. |
| `date_confidence` | `unresolved` for every record this slice produces — a fourth value alongside the plan's `exact` / `inferred` / `chapter-only` (part 16 M0), signaling "year resolution has not run yet" rather than any of those three outcomes. The year-resolution slice is expected to overwrite this field. |
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
| `dateline` | The letter's indented dateline paragraph (e.g. `CONCORD, October 27, 1837.`), found as the first fully-indented paragraph after the heading. Unlike the journals, letter datelines already carry an explicit year — still landing here verbatim rather than parsed, since year resolution is a separate M0 step (part 16) from letters parsing. |
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

## Recipients table (issue #6)

`recipients_table(records)` maps each verbatim `recipient` string to the
`SRC-` IDs of the letters naming them — "a real, checkable table ... not a
list in a comment" (issue #6). `memoria normalize` writes it as YAML to
`sources/normalized/recipients.yaml` via `write_recipients_table`. It has
43 entries against the real corpus, matching RECON.md §5's "43 distinct
recipients" exactly.
