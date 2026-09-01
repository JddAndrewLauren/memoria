# Editorial record schema

Forces `docs/open-problems.md` §6's "how editorial apparatus is
represented" for the PoC's first source type (journals). Implemented by
`src/memoria/editorial.py`, building on the `NormalizedRecord`s
`src/memoria/normalize.py` (issue #3) produces.

## What an editorial record is

The 1906 "Writings" edition puts a 1906 editor's voice **inside** the
1837-46 evidence text: inline footnote markers and their footnote bodies,
bracketed editorial asides, and two long editor introductions (Bradford
Torrey's in Journal I, F. B. Sanborn's in Familiar Letters). Under
`docs/open-problems.md` §6 this is retrospective commentary *about* the
evidence, not evidence itself, so it is extracted out of every
`NormalizedRecord`'s paragraphs into a separate `EditorialRecord`, linked
back to the evidence it annotates rather than living inside it.

`normalize_journals` (#3) deliberately left this apparatus inline -
segregating it was scoped to this later slice.

## Frontmatter fields

```yaml
---
id: ED-000042
editorial_type: footnote
recorded_date: "1906"
retrospective: true
linked_record_id: SRC-000012
linked_anchor: src-000012-p3
original_file: raw/gutenberg/57393-journal-01/pg57393.txt
original_locator: "Journal I, footnote 42"
---
```

| Field | Meaning |
|---|---|
| `id` | Stable `ED-NNNNNN` identifier (six digits, zero-padded, the same form as `SRC-`). Assigned sequentially: both volumes' introductions first, then each volume's footnotes (in footnote-number order), standalone bracketed asides, and interpolations (each in entry/paragraph order), volume order (J01, J02). |
| `editorial_type` | `introduction`, `footnote`, `bracketed-span` (a standalone aside, removed from evidence), or `interpolation` (an editor-supplied word/phrase, kept in evidence - see "What gets extracted" below). |
| `recorded_date` | The edition's own date - `"1906"` for every record this slice produces (RECON.md's corpus table: all three source volumes are the 1906 Houghton Mifflin "Writings" edition). Distinct from, and never overwrites, the evidence record's `event_date`. |
| `retrospective` | Always `true` - an editorial record is retrospective commentary by construction (`docs/open-problems.md` §6). |
| `linked_record_id` | The `SRC-` ID of the evidence record this annotates, or `null` for an introduction (volume-level, not tied to one entry) or a footnote whose marker fell outside the entries this slice covers (see "Known gaps" below). |
| `linked_anchor` | The evidence paragraph anchor (`record.anchor_id(n)` form) this annotates, or `null` alongside an unset `linked_record_id`. If the span's own paragraph was wholly editorial and so dropped from the evidence text entirely, this resolves to the nearest surviving paragraph's anchor instead, so the citation still opens next to real evidence. |
| `original_file` | Path to the raw source, relative to the evidence root - the same convention `NormalizedRecord.original_file` uses. |
| `original_locator` | Human-readable pointer into the original, e.g. `"Journal I, footnote 42"` or `"Journal I, Introduction (Torrey)"`. |

The record body is the extracted text itself - the footnote's body, the
bracketed span's contents, or the introduction's full text.

## What gets extracted

- **Footnote markers and bodies.** An inline `[N]` marker is stripped from
  the evidence paragraph it sits in; its body is parsed out of the
  volume's back-matter `FOOTNOTES` section (already cut from evidence by
  #3) and stored as one `footnote` editorial record, linked to the
  evidence paragraph the marker was in.
- **Standalone bracketed asides.** A `[...]` span that reads as its own
  complete remark - illustration captions (`[Illustration: ...]`),
  cross-references to the published works (`[_Week_, p. 319; Riv.
  395.]`), `[?]` and `[_sic_]` markers, structural notes (`[Two pages
  missing.]`), and any bracket that is a whole paragraph on its own with
  nothing else around it - is stripped from the evidence text and stored
  as one `bracketed-span` record.
- **Interpolations.** Roughly two-thirds of the non-numeric `[...]` spans
  in entry text are not asides at all: they are single words or short
  phrases the 1906 editor supplied to complete a gap in Thoreau's own
  sentence - `"must surely [be] the circulations of God"`, `"Walked to
  Concord [N. H.], 10 miles."`, `"resort [to], it would be difficult"`.
  Excising these mangles the evidence (PR #51 review round 1, BLOCKING
  2), so an interpolation's *text* stays in the evidence paragraph -
  only its brackets are removed - while it is still extracted as its own
  `interpolation` editorial record, linked to the same paragraph and
  anchor, recording that a 1906 editor supplied it.

  `_is_standalone_editorial_aside` (`src/memoria/editorial.py`) draws
  the line: a bracket consuming its whole paragraph, one starting with
  italic markup (`_..._`, covering cross-references and notes like
  `[_sic_]`/`[_Undated._]`), `[?]`, an `[Illustration...]` marker, a
  `[See ...]`/`[Cf. ...]` cross-reference, or content that reads as a
  complete capitalized sentence of its own is a standalone aside;
  anything shorter - one or two words, or an abbreviation-shaped token
  like `[Dec.]` or `[N. H.]` - is an interpolation.
- **Introductions.** Torrey's Introduction (Journal I) and Sanborn's
  Introduction (Familiar Letters) are each extracted whole, between the
  raw file's `INTRODUCTION` heading and the heading that follows it, as a
  single `introduction` record - never split, never treated as journal or
  letter evidence.

A paragraph that was nothing but a standalone aside (e.g. a
`[Two pages missing.]` note) is dropped from the evidence record's
paragraph list once stripped, and the record's anchors renumber over what
survives - the same treatment #3 gives chapter-marker-only paragraphs. An
interpolation's paragraph never empties this way, since its text stays
behind. Whitespace left by a removed span next to punctuation (e.g. "word
, next") is closed up the same way line-wrap whitespace is collapsed.

## Known gaps

Not every footnote marker links to an evidence paragraph. Two already-
documented gaps (both pre-existing #3 scope decisions, not defects here)
leave a footnote's marker outside the entries this slice walks:

- **Torrey's Introduction** (Journal I) itself carries 3 footnote markers.
  The introduction is extracted whole as its own editorial record rather
  than further decomposed, so these 3 footnotes are extracted (their
  bodies are real, readable text) but left unlinked (`linked_record_id:
  null`).
- **J02's undated opening fragments**, discarded by #3 ("Known data loss:
  J02's undated opening fragments" in `docs/normalized-record-schema.md`),
  carry 26 footnote markers for the same reason.

Per real-corpus counts: 880 footnotes total (508 J01 + 372 J02), of which
851 (505 + 346) link to an evidence paragraph and 29 (3 + 26) do not, for
the reasons above. Nothing is deleted either way - every footnote body is
extracted and readable regardless of whether it links.

## Reconciliation against RECON.md

RECON.md §4(a) states ~1,750 footnote markers and ~1,050 bracketed
editorial spans. Mechanically re-counting `[\d+]` and non-numeric `[...]`
spans directly in each raw file (the same grep-shaped method RECON's own
figures imply) finds:

| | J01 | J02 | Total |
|---|---|---|---|
| `[\d+]` occurrences | 1,017 | 744 | 1,761 |
| non-numeric `[...]` spans | 593 | 512 | 1,105 |

Both match RECON.md's approximate figures closely. The `[\d+]` count
matches RECON's own per-file numbers (1,017 / 744) exactly - it counts
each footnote twice, once as the inline citation marker and once as the
footnote list's own `[N]` number label, which is why the extracted
`footnote` record count (880, one per distinct footnote) is roughly half
this total rather than close to it. The 1,105 non-numeric spans split
232 in-entry (86 standalone asides + 146 interpolations) against 873
inside back-matter footnote bodies and the two introductions - already
extracted whole as part of those records, not decomposed further.
`tests/test_editorial.py`'s `TestAgainstTheRealEvidenceCorpus` pins both
the raw-text reconciliation counts above and the extracted-record counts
(880 footnotes, 86 standalone asides, 146 interpolations, 2
introductions) rather than either number in isolation.

## Indexing (issue #7's `memoria rebuild`)

`memoria rebuild` (`src/memoria/index.py`) runs
`extract_editorial_apparatus` on every normalized record before writing
or indexing anything, so the FTS5 index and `sources/normalized/` both
reflect stripped, apparatus-free evidence text - not the unstripped
paragraphs `normalize_journals` alone produces. Every `EditorialRecord`
is indexed too, under `source_type: "editorial"`, so
`memoria.index.search(..., exclude_editorial=True)` genuinely excludes
footnotes, asides, and interpolations from a search rather than being a
no-op (PR #51 review round 1, BLOCKING 1).
