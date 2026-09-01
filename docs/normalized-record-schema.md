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
entry text.

## Entry boundaries

Journal entries open with a line-initial italic date heading — RECON.md §3's
closed set of forms (`_Oct 22._`, `_Jan. 24. Sunday._`, `_Sept. 29, 1842._`,
`_May 3-4._`, and the two bare `_Dec._` / `_Jan._` month-only headings).
`normalize_journals` splits the raw text at every line matching that form,
after first stripping the Gutenberg license boilerplate, Transcriber's Note,
Torrey's Introduction, Contents/Illustrations lists (all of it front matter
preceding the first date heading, discarded by construction) and the
Gutenberg trailing license (outside the `*** END OF ... ***` marker).

**Editorial apparatus** (footnote markers, bracketed editorial spans,
running section titles like `SOLITUDE`) is left inline for this slice —
segregating it into separate retrospective-editorial records is a later M0
step (part 16), not this one. Quote characters are normalized (curly →
straight ASCII) so a search phrase matches regardless of which volume's
convention produced it (RECON.md §6.1: J01/Familiar Letters use straight
quotes, J02 uses curly).

## Deviation from RECON.md's date-heading count

RECON.md §3 states 299 (J01) and 149 (J02) date headings — 448 total.
Mechanically re-implementing RECON's own stated detection rule (line-initial
italic date, closed set of month/weekday forms) against the raw corpus
finds more: 399 (J01) and 155 (J02) — 554 total. Manual spot-checking of the
extra headings turned up no false positives, and one concrete
counter-example to RECON's own claim: J02's Chapter I (RECON.md §3, "has no
date headings at all") in fact contains 22 line-initial date headings within
RECON's own stated line range for that chapter (June–Nov 1850 entries after
the undated opening fragments). See the finding posted on issue #3 for the
full evidence. `tests/test_normalize.py`'s
`TestAgainstTheRealEvidenceCorpus.test_date_headings_found_are_reconciled_against_recon`
asserts the actual, mechanically verified count (554) rather than RECON's
summary figure (448).
