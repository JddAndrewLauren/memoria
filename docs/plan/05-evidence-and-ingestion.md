<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 5, 6, 7 of the original memoria-plan.md -->
<!-- §7 rewritten 2026-08-31: the canonical alias map is withdrawn; aliasing lives -->
<!-- in entry match terms and subject hazards. Original §7 in _original-memoria-plan.md. -->
<!-- §5.1-5.4 amended 2026-09-01: raw units, the ID ledger, record boundaries per format, -->
<!-- quoted-reply policy, conversion via MarkItDown, skip-unchanged runs. ADR-0006. -->

# 5. Source Ingestion

## 5.1 Raw evidence

Original files are preserved untouched under:

```text
sources/raw/
```

They are never rewritten by the Curator.

Where practical, hashes of raw files should be stored to detect accidental modification.

**A raw unit is what receives a `SRC-` ID** (added 2026-09-01): a file, or one message
inside an email export. The evidence manifest (`raw/manifest.yaml`) lists every raw unit
with its hash, and it is also the **ID ledger**: a unit is numbered on first appearance
and keeps that number forever, a deleted unit keeps its number reserved, and nothing is
reused. IDs are therefore stable under a growing archive and under re-normalization —
which every citation, and since ADR-0005 every extraction placement, depends on. See
`../adr/0006-src-ids-are-allocated-by-the-manifest-ledger.md`.

---

## 5.2 Normalized source records

Documents are converted into searchable Markdown records.

Example:

```yaml
---
id: SRC-000184
source_type: journal
recorded_date: 2011-07-17
event_date: 2011-07-17
date_confidence: exact
contemporaneous: true
original_file: ../raw/journals/2011.docx
original_locator: "Entry dated July 17, 2011"
---
```

A natural documentary boundary should normally define a record:

- journal entry;
- email;
- individual note;
- ~~message or logical message thread~~ one message, never a thread (2026-09-01);
- meeting transcript;
- document section.

Search-time chunking occurs only in the index.

The normalized record remains the unit of evidence.

**The boundary rules as decided 2026-09-01.** Working assumption, unconfirmed: the real
archive's top formats are docx, pdf and email exports. Everything else is a raw unit with
a stub record until it matters.

- **Email: one message per record.** Placements, relations and `recorded_date` are per
  paragraph and inherit the record's date; a thread spans dates and cannot carry an
  honest one. The thread is metadata (`thread_id`) the index groups by, never the unit
  of evidence. Attachments are listed on the message record by name and type, kept
  under `raw/` and hashed, and get a record of their own only when they are a format
  Memoria converts.
- **docx and pdf: one record per file.** Start simple. A file that holds many dated
  entries gives every paragraph one date, which the Timeline subject will feel; the
  amendment path, not built, is a per-collection split rule such as
  split-on-dated-heading, declared in the manifest. Revisit at the first such file.
- **A scanned pdf is a stub record**: ID, frontmatter, Open original, no body. OCR is
  out of scope. A stub has no paragraphs, so neither the index nor the extraction sees
  it, and nothing is invented.

---

## 5.3 Stable internal anchors

Normalized records receive stable paragraph or logical-section anchors.

For example:

```markdown
<a id="src-000184-p17"></a>

I called Bob that evening...
```

This allows Memoria to cite the precise relevant location rather than merely pointing at a large document.

Where the original file format supports deep linking, Memoria should expose an **Open original** action as well.

A source view should ideally provide:

```text
Normalized evidence
Original file
Original locator/page/message
Recorded date
Event date
Source type
Provenance metadata
```

---

## 5.4 Conversion

Added 2026-09-01. "Conversion" means format conversion into the normalized record and
nothing else — no language translation, no OCR. The raw file is the original; the
record is a reading of it that a person can always check against **Open original**.

**The converter is MarkItDown** (Microsoft, MIT, deterministic when no model client is
configured) for docx and for HTML-bodied email. The record keeps whatever it emits —
headings, lists, tables, links, bold and italic — with no stripping pass; FTS5 and the
extraction read words either way, and the raw file holds the rest. Images in a docx are
listed in frontmatter by name, not embedded.

**pdf goes through pdfplumber directly**, page by page, because MarkItDown's own pdf
path discards page boundaries. A page marker is written between pages so that a
citation to a paragraph deep in a long report is followable to a page, which is what
`original_locator`'s "a string a person can follow" rule requires. The marker is not a
paragraph: the paragraph splitter skips it, so it never earns an anchor, an index row or
an extraction read.

**Email parsing is Memoria's own** — the standard library for mbox and `.eml`,
MarkItDown's Outlook converter only when the export is `.msg` — because the boundary,
the headers and the quoted-reply policy are all decisions the converter cannot make.

**Quoted replies are cut and dropped.** Most exported messages carry the earlier thread
quoted below; left in, every message re-indexes its ancestors, search hits land on the
wrong message, and under ADR-0005 the parent's people and relations are placed again
under the child, inflating co-occurrence. A deterministic splitter cuts at the first
standard marker — `>` prefixes, an "On … wrote:" line, an Outlook "From:/Sent:/To:"
header block — and for interleaved replies removes the `>` lines and keeps the sender's
lines in order. The record then carries `in_reply_to`, resolved from `Message-ID` and
`In-Reply-To` within the same export, and `quoted_excised: true` whenever anything was
cut, so a reader knows the body is partial. The excised text is not kept in the record:
it is in the raw file, and usually in the parent record. The accepted gap is a quoted
message whose original was never exported, which is then not searchable.

**A run reconverts only what changed.** Each record's frontmatter carries the raw unit's
hash and the converter version that produced it; a unit is reconverted when the
manifest hash or the pinned converter version differs, and `--all` forces everything.
The record is the state — there is no second store of what was done. Over unchanged
input a run produces no diff, which is the idempotence check; after a new export it
produces only new records, because the ID ledger renumbers nothing.

**Converter drift is a priced event.** The paragraph hash is the extraction's memo key
(part 06 §8.12), so converter output that shifts by a space invalidates a model read.
Converter versions are pinned and recorded in the manifest, and a version bump is an
explicit re-normalize that reports how many paragraph hashes changed *before* the
extraction is run.

**Written down for later, not built:** images, charts and spreadsheets. A deep read of
a spreadsheet is unlikely to ever be worth it; surfacing that a spreadsheet was attached
to a particular message may be. Attachment presence lives in frontmatter, which the
extraction does not read, so that is the seam to reopen if it is wanted.

---

---

# 6. Temporal Discipline

Personal archives contain several kinds of time that must not collapse into one another.

Memoria distinguishes:

- **event date** — when something happened;
- **recorded date** — when the source was created;
- **contemporaneous evidence** — created near the event;
- **retrospective evidence** — later recollection or interpretation.

Therefore:

> What happened in July 2011?

and:

> What did I believe in July 2011?

are different research questions.

A 2018 recollection may help answer the first.

It must not silently answer the second.

This distinction is enforced in research skills and represented in search filters.

---

---

# 7. Alias and Entity Resolution

Names in a personal archive are messy.

A person may appear as:

```text
Bob
Robert
R.
Bob Smith
my brother-in-law
```

**There is no canonical alias map.** That list *is* the Bob entry's **match terms**
(part 06 §8.2) — how this entry is referenced, beyond the subject default — kept on
the entry and owned by the author. A separate `subjects/people/_aliases.yaml` would
be a second store for the same matching seam, guaranteed to drift from the first.

Aliasing therefore lives in two places, at two scales:

- **The subject prompt's matching hazards** (part 06 §8.1) carry the discipline
  that spans entries: match aliases, initials, honorifics, married names and
  location forms; do not merge people sharing a surname without corroboration.
  Cross-entry disambiguation — several people sharing a surname — is a hazard
  stated once per subject, not a map row.
- **The entry's match terms** carry the forms specific to one entry — the several
  forms one person is named by, a nickname, a variant spelling the transcriber
  preserved.

The resolution discipline is unchanged, and the People subject's hazards are where
it is carried: alias resolution is one of the few curation activities where
ambiguity should normally be surfaced to the author.

A mistaken theme summary is reversible.

A mistaken entity merge can silently contaminate thousands of retrieval results.

Memoria should therefore prefer unresolved ambiguity to confident misidentification.

**The extraction does not change this** (2026-09-01, ADR-0005). The model pass that
now proposes candidates records **placements** — its reading that a paragraph mentions
an entry — but the durable mapping is recomputed at rebuild from match terms alone. A
placement the terms do not license is a *proposed* match term, unplaced until the
author accepts it. The model proposes; the author's terms decide.

---
