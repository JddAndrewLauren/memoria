<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 5, 6, 7 of the original memoria-plan.md -->

# 5. Source Ingestion

## 5.1 Raw evidence

Original files are preserved untouched under:

```text
sources/raw/
```

They are never rewritten by the Curator.

Where practical, hashes of raw files should be stored to detect accidental modification.

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
- message or logical message thread;
- meeting transcript;
- document section.

Search-time chunking occurs only in the index.

The normalized record remains the unit of evidence.

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

A canonical alias map lives in:

```text
people/_aliases.yaml
```

Alias resolution is one of the few curation activities where ambiguity should normally be surfaced to the author.

A mistaken theme summary is reversible.

A mistaken entity merge can silently contaminate thousands of retrieval results.

Memoria should therefore prefer unresolved ambiguity to confident misidentification.

---
