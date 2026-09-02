# Normalized record schema

The contract a normalized record must satisfy: stable identity, stable
paragraph anchors, and honest temporal metadata. Forces
`docs/open-problems.md` §6's "the normalized record schema".

**Amended 2026-09-01** after the ingest grilling: raw units and the ID ledger (ADR-0006),
the email and conversion fields, page markers, stub records. Part 05 §5.1-5.4 carries the
decisions; this file carries the contract.

**No normalizer implements this today.** The Thoreau PoC corpus was retired
2026-09-01 (`docs/open-problems.md` §2.4) and the ingestion code written for
it was removed with it. This document survives that removal deliberately: it
is what a future normalizer must produce, and what `memoria.index` and
`memoria validate` already read. Treat it as an interface, not a description
of running code.

## What a normalized record is

A normalized record is one Markdown file per **raw unit** — a file, or one
message inside an email export (part 05 §5.1-5.2 of the build plan). One
message, never a thread; one docx or pdf, never a section of one, until a
per-collection split rule says otherwise. Each record gets a stable `SRC-` ID
(part 04 §4) and stable paragraph anchors (part 05 §5.3), so a citation like
`SRC-000184 ¶17` keeps meaning forever.

A record may be a **stub**: frontmatter and no body. That is what a scanned
pdf produces while OCR is out of scope. A stub has no paragraphs, no anchors,
no index rows and nothing for the extraction to read; it exists so the raw
unit has an ID, a place in the `SOURCES` tree and an **Open original**.

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
| `id` | Stable `SRC-NNNNNN` identifier (six digits, zero-padded — part 04 §4's `SRC-000184` form; the `SRC-0184` seen in the desktop mockup is a noted divergence, part 19 §19.11). Assigned in **order of first appearance in the evidence manifest**, which is the ID ledger (ADR-0006): a raw unit is numbered when the manifest first lists it and keeps that number forever, a deleted unit keeps its number reserved, and nothing is reused. Stable across re-runs and across a growing archive because the assignment is a function of the committed manifest, not of run order. (Until 2026-09-01 this read "sequentially in a deterministic document order … not a hash or a counter file"; that held for a fixed corpus and renumbers everything the first time a file sorts into the middle.) |
| `source_type` | What kind of document this is — `journal`, `letter`, `book`, and whatever else an archive supplies (email, message, transcript). Consumers must render the values actually present rather than a hardcoded list. `book` marks an **audit target**: already-written prose, the query side of an appearance, never evidence to write from. |
| `recorded_date` | The date as the source states it, verbatim — never rewritten by year resolution. Empty where the record carries no date of its own. |
| `event_date` | `recorded_date` with its resolved year appended, or unchanged where the source already states its own year, or where no year could be resolved (`date_confidence: unresolved` — **no invented date**). Empty where the record has no day at all: a year that scopes a record is not a date, and the field is left empty rather than filled with a year pretending to be one. The scope stays recoverable from `original_locator`. |
| `date_confidence` | How firmly the date is known, and by what route. Five values, all of which a consumer must render distinguishably: `exact`, where the resolution was independently confirmed (e.g. a weekday checked against a real calendar); `inferred`, where the year came from surrounding context or a plain-text statement with nothing to confirm it against; `chapter-only`, where the record has no date of its own and its enclosing section is the only date context there is; `unresolved`, where resolution was attempted and produced nothing; `published`, for an audit target, whose date is a year of publication — a documentary fact about the volume, not a date resolved out of the text. A resolution that fails its own check is never silently promoted to `exact`; it is reported. |
| `contemporaneous` | Whether this is evidence recorded at the time, or a retrospective record about it. Load-bearing: it is how §6's temporal discipline is enforced at retrieval time (`search_text`, issue #12). |
| `original_file` | Path to the raw source, relative to the evidence root (`MEMORIA_EVIDENCE_ROOT`) — the same convention `manifest.yaml` and `memoria validate` use. |
| `original_locator` | Human-readable pointer into the original, e.g. `"Journal I, entry dated Oct. 22."`. **It is a string a person can follow, not a byte offset or a line number** — nothing may mechanically scroll to or highlight it in the raw file (issue #25). |
| `raw_sha256` | The hash of the raw unit this record was converted from, as the manifest records it. With `converter`, this is what a normalization run compares to decide whether to reconvert (part 05 §5.4). Added 2026-09-01. |
| `converter` | The converter and pinned version that produced the body, e.g. `markitdown 0.1.2` or `pdfplumber 0.11.4`. A version bump reconverts and reports how many paragraph hashes changed. Added 2026-09-01. |
| `thread_id` | Email only. The thread the message belongs to, for grouping in the index and the viewer. A thread is never a record. Resolved to the thread root's own `Message-ID` (or its own `SRC-` id when the root has none) - the root found by walking each message's `In-Reply-To`, or, where that is absent, the sibling whose `Thread-Index` is the longest proper prefix present in the export (docs/corpora/enron.md finding 2, #115). One thread never splits into two `thread_id`s by mixing the two mechanisms. Added 2026-09-01. |
| `subject` | Email only. The `Subject` header, verbatim. Added 2026-09-01 (#115). |
| `from` / `to` / `cc` | Email only. The message headers, kept here and **never written into the body as paragraphs** — they are not the sender's words. Whether the extraction is handed them alongside each paragraph is an open interface question with ADR-0005. Added 2026-09-01. |
| `in_reply_to` | Email only. The `SRC-` ID of the message this one replies to, resolved from `Message-ID` / `In-Reply-To` within the same export; empty when the headers are missing or the parent is not in the archive. When `In-Reply-To` is absent and `Thread-Index` is present, resolved instead to the sibling whose `Thread-Index` is the longest proper prefix present in the export (docs/corpora/enron.md finding 2, #115). Added 2026-09-01. |
| `quoted_excised` | Email only. `true` when the quoted-reply splitter cut anything from the body, so a reader knows the body is partial and the raw file holds the rest. The cut text is not kept in the record (part 05 §5.4). Added 2026-09-01. |
| `attachments` | Email only. The attachments by filename and type. The files are kept under `raw/` and hashed; each gets a record of its own only when it is a converted format. Added 2026-09-01. |
| `images` | docx only. Embedded images by name, not embedded in the body. Added 2026-09-01. |

## Paragraph anchors

Each paragraph in a record's body is preceded by an HTML anchor, numbered
positionally within the record:

```markdown
<a id="src-000184-p17"></a>

I called Bob that evening...
```

Anchors are stable across re-runs for the same reason IDs are: paragraph
splitting (on blank-line boundaries) is a deterministic function of the
record text.

**pdf page markers are not paragraphs** (2026-09-01). A pdf record carries a
marker line between pages — an HTML comment of the form
`<!-- page 12 -->` — so a paragraph deep in a long file is followable to a
page. The splitter skips marker lines: a marker earns no anchor, no index
row, and no extraction read. Anchors number the real paragraphs only, and a
marker inserted or removed by a converter change shifts no anchor. `NormalizedRecord.anchor_id(n)` is the single source of this
`f"{id.lower()}-p{n}"` form — downstream slices citing a paragraph should
call it rather than re-deriving the anchor string independently.

**No paragraph may contain the anchor sequence itself.** The format has no
escaping, so `<a id="...">` inside a paragraph's own text is indistinguishable
from the separator: at a paragraph boundary it reads back as two paragraphs,
re-serializes byte-identically, and shifts every citation index after it while
looking correct. A normalizer must not emit one, and `record_to_markdown`
refuses to write one rather than leaving the ambiguity on disk — by read time
the two cases are the same bytes and cannot be told apart.

**Records are LF.** The parser names CRLF as the problem rather than reporting
missing frontmatter, and `.gitattributes` keeps the repository's own files
that way.

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
