# Normalized record schema

The contract a normalized record must satisfy: stable identity, stable
paragraph anchors, and honest temporal metadata. Forces
`docs/open-problems.md` §6's "the normalized record schema".

**No normalizer implements this today.** The Thoreau PoC corpus was retired
2026-09-01 (`docs/open-problems.md` §2.4) and the ingestion code written for
it was removed with it. This document survives that removal deliberately: it
is what a future normalizer must produce, and what `memoria.index` and
`memoria validate` already read. Treat it as an interface, not a description
of running code.

## What a normalized record is

A normalized record is one Markdown file per natural documentary boundary
(part 05 §5.2 of the build plan) — one dated diary entry, one letter, one
message. Each record gets a stable `SRC-` ID (part 04 §4) and stable
paragraph anchors (part 05 §5.3), so a citation like `SRC-000184 ¶17` keeps
meaning forever.

## Frontmatter fields

```yaml
---
id: SRC-000184
source_type: journal
recorded_date: Oct. 22.
event_date: Oct. 22., 1845
date_confidence: inferred
contemporaneous: true
original_file: raw/<collection>/<file>
original_locator: "Journal I, entry dated Oct. 22."
---
```

| Field | Meaning |
|---|---|
| `id` | Stable `SRC-NNNNNN` identifier (six digits, zero-padded — part 04 §4's `SRC-000184` form; the `SRC-0184` seen in the desktop mockup is a noted divergence, part 19 §19.11). Assigned sequentially in a deterministic document order. Stable across re-runs over unchanged input because the assignment is a function of that input, not a hash or a counter file. |
| `source_type` | What kind of document this is — `journal`, `letter`, `book`, and whatever else an archive supplies (email, message, transcript). Consumers must render the values actually present rather than a hardcoded list. `book` marks an **audit target**: already-written prose, the query side of an appearance, never evidence to write from. |
| `recorded_date` | The date as the source states it, verbatim — never rewritten by year resolution. Empty where the record carries no date of its own. |
| `event_date` | `recorded_date` with its resolved year appended, or unchanged where the source already states its own year, or where no year could be resolved (`date_confidence: unresolved` — **no invented date**). Empty where the record has no day at all: a year that scopes a record is not a date, and the field is left empty rather than filled with a year pretending to be one. The scope stays recoverable from `original_locator`. |
| `date_confidence` | How firmly the date is known, and by what route. Five values, all of which a consumer must render distinguishably: `exact`, where the resolution was independently confirmed (e.g. a weekday checked against a real calendar); `inferred`, where the year came from surrounding context or a plain-text statement with nothing to confirm it against; `chapter-only`, where the record has no date of its own and its enclosing section is the only date context there is; `unresolved`, where resolution was attempted and produced nothing; `published`, for an audit target, whose date is a year of publication — a documentary fact about the volume, not a date resolved out of the text. A resolution that fails its own check is never silently promoted to `exact`; it is reported. |
| `contemporaneous` | Whether this is evidence recorded at the time, or a retrospective record about it. Load-bearing: it is how §6's temporal discipline is enforced at retrieval time (`search_text`, issue #12). |
| `original_file` | Path to the raw source, relative to the evidence root (`MEMORIA_EVIDENCE_ROOT`) — the same convention `manifest.yaml` and `memoria validate` use. |
| `original_locator` | Human-readable pointer into the original, e.g. `"Journal I, entry dated Oct. 22."`. **It is a string a person can follow, not a byte offset or a line number** — nothing may mechanically scroll to or highlight it in the raw file (issue #25). |

## Paragraph anchors

Each paragraph in a record's body is preceded by an HTML anchor, numbered
positionally within the record:

```markdown
<a id="src-000184-p17"></a>

I called Bob that evening...
```

Anchors are stable across re-runs for the same reason IDs are: paragraph
splitting (on blank-line boundaries) is a deterministic function of the
record text. `NormalizedRecord.anchor_id(n)` is the single source of this
`f"{id.lower()}-p{n}"` form — downstream slices citing a paragraph should
call it rather than re-deriving the anchor string independently.

## Whitespace policy

**Evidence text is sacred: normalization never reflows it.** A paragraph is
stripped at its ends and otherwise kept exactly as the raw source's line
breaks and indentation produced it, so a quoted verse's own line structure
survives into the normalized record unchanged.

The one licensed exception is a paragraph an editorial span was actually
**excised from**, where closing up the artifact the excision itself left
behind (a doubled space, a stray space before punctuation) is repair rather
than rewriting. A paragraph nothing was excised from stays byte-identical.
Scoping that reflow to excised paragraphs only is not a detail — running it
unconditionally silently edits evidence that needed no repair.
