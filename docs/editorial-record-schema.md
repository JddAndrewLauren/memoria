# Editorial record schema

Forces `docs/open-problems.md` §6's "how editorial apparatus is
represented" for both evidence source types this corpus holds: journals
(issue #5) and, as of issue #56, the letters volume too. Implemented by
`src/memoria/editorial.py`, building on the `NormalizedRecord`s
`src/memoria/normalize.py` (issues #3, #6) produces.

## What an editorial record is

The 1906 "Writings" edition puts a 1906 editor's voice **inside** the
1837-46 evidence text, in both the journals and the letters: inline
footnote markers and their footnote bodies, bracketed editorial asides,
and two long editor introductions (Bradford Torrey's in Journal I, F. B.
Sanborn's in Familiar Letters). Under `docs/open-problems.md` §6 this is
retrospective commentary *about* the evidence, not evidence itself, so it
is extracted out of every `NormalizedRecord`'s paragraphs into a separate
`EditorialRecord`, linked back to the evidence it annotates rather than
living inside it.

`normalize_journals` (#3) and `normalize_letters` (#6) each deliberately
left this apparatus inline in their own volume - segregating it was
scoped to this later slice (#5 for the journals, #56 for the letters).
`extract_editorial_apparatus` runs the same extraction over records from
either volume, or both mixed together: it dispatches to a volume's own
footnote-body parser (the journals' single back-matter section versus the
letters' several scattered blocks - see "What gets extracted" below), and
otherwise treats a letter's paragraphs exactly like a journal entry's.

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
| `id` | Stable `ED-NNNNNN` identifier (six digits, zero-padded, the same form as `SRC-`). Assigned sequentially: both introductions first (Torrey, then Sanborn), then each volume's footnotes (in footnote-number order), standalone bracketed asides, and interpolations (each in entry/paragraph order), volume order (J01, J02, Familiar Letters). |
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
  the evidence paragraph it sits in; its body is parsed out and stored as
  one `footnote` editorial record, linked to the evidence paragraph the
  marker was in. Each volume's footnotes are numbered in one strict
  sequence, but sit differently in the raw source: the journals hold
  every footnote in one volume-level back-matter `FOOTNOTES` section
  (already cut from evidence by #3); the letters (#56) scatter theirs
  across several `FOOTNOTES:` blocks through the body instead, one per
  stretch of letters, each closed by whatever body text resumes next -
  the next such block, the next letter Thoreau wrote, a letter *to*
  Thoreau from another correspondent, a chapter heading, `APPENDIX`, or
  the volume's General Index. Recognized by a positive rule rather than
  an enumeration of those shapes: a bare, unindented line made up
  entirely of uppercase letters/digits and light punctuation, with no
  lowercase letter on it - a shape no footnote body's own text ever
  takes (PR #63 review round 1).
- **Standalone bracketed asides.** A `[...]` span that reads as its own
  complete remark - illustration captions (`[Illustration: ...]`),
  cross-references to the published works (`[_Week_, p. 319; Riv.
  395.]`), `[?]` and `[_sic_]` markers, structural notes (`[Two pages
  missing.]`), a whole-paragraph editorial annotation (the letters'
  `[Postscript by Helen Thoreau.]`), and any bracket that is a whole
  paragraph on its own with nothing else around it - is stripped from the
  evidence text and stored as one `bracketed-span` record.
- **Interpolations.** Roughly two-thirds of the non-numeric `[...]` spans
  in entry text are not asides at all: they are single words or short
  phrases the 1906 editor supplied to complete a gap in Thoreau's own
  sentence - `"must surely [be] the circulations of God"`, `"Walked to
  Concord [N. H.], 10 miles."`, `"resort [to], it would be difficult"`,
  or, in the letters, `"Peabody [a college classmate]"`. Excising these
  mangles the evidence (PR #51 review round 1, BLOCKING 2), so an
  interpolation's *text* stays in the evidence paragraph - only its
  brackets are removed - while it is still extracted as its own
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
, next") is closed up, and the paragraph's line-wrap whitespace is
collapsed along with it - but only in a paragraph a span was actually
excised from. A paragraph carrying no bracketed span at all is left
byte-identical to what normalization produced, mid-paragraph newlines
included (issue #55; see "Whitespace policy" in
`docs/normalized-record-schema.md` for the full rule).

## Known gaps

Not every footnote marker links to an evidence paragraph. Several gaps
leave a footnote's marker outside the entries this slice walks, and none
is a defect here:

- **Torrey's Introduction** (Journal I) itself carries 3 footnote markers.
  The introduction is extracted whole as its own editorial record rather
  than further decomposed, so these 3 footnotes are extracted (their
  bodies are real, readable text) but left unlinked (`linked_record_id:
  null`).
- **J02's Chapter I heading line**, `1850 (ÆT. 32-33)[1]`, carries marker
  `[1]`. The chapter heading is apparatus, not any record's evidence, so it
  belongs to no record and its footnote is unlinked for the same reason.

Per real-corpus counts: 880 journal footnotes total (508 J01 + 372 J02), of
which 876 (505 + 371) link to an evidence paragraph and 4 (3 + 1) do not,
for the reasons above. Nothing is deleted either way - every footnote body
is extracted and readable regardless of whether it links.

### Familiar Letters (issue #56)

The letters volume has its own version of the same shape, plus one gap
the journals don't: footnote numbering runs 1..111 in one strict sequence
across the whole volume, but footnote 1 itself sits inside Sanborn's own
Introduction (under a singular "FOOTNOTE:" heading, distinct from the
plural "FOOTNOTES:" heading every other block uses) - already swept
whole into the `introduction` record's own text by
`_extract_introduction_text`, so it is never decomposed into its own
`footnote` record at all, the one respect in which the letters' handling
isn't a parallel of the journals' (whose own intro footnotes *are*
extracted as separate, unlinked records - see above). Footnote 1's text
is not lost either way; it simply reads as part of the introduction
record rather than its own.

Of the volume's other 110 footnotes (numbers 2-111), 101 link to a
letter's own evidence paragraph and 9 do not, in two shapes:

- **Sanborn's own biographical preamble**, the stretch of narrative
  between the `FAMILIAR LETTERS OF THOREAU` heading and the first actual
  `TO ...` letter, carries 6 footnote markers (footnotes 2-7). `#6`
  discards this preamble as front matter the same way it discards
  Sanborn's Introduction proper - unlike the journals' undated-opening
  fragments (recovered as records), the letters' preamble was never
  recovered as evidence, so these footnotes are extracted (their bodies
  are real, readable text) but left unlinked.
- **A letter's own recipient heading line** carries an inline marker in 3
  cases (footnotes 15, 41, 42) - e.g. `TO MRS. LUCY BROWN[15] (AT
  PLYMOUTH).` The heading is apparatus (it becomes the letter's
  `recipient` field - with this marker stripped out of it - not its
  paragraph text), not evidence, so it belongs to no paragraph and its
  footnote is unlinked for the same reason as J02's chapter-heading
  marker.

Nothing is deleted here either: every one of the 9 unlinked letters
footnotes is extracted with its real body text, just without a
`linked_record_id`/`linked_anchor`.

A third gap used to sit here: J02's undated opening fragments, discarded by
an earlier pass of #3, took 26 footnote markers out of reach with them.
Recovering those fragments as records
(`docs/normalized-record-schema.md`, "J02's undated opening fragments")
linked 25 of the 26 - all but the chapter-heading marker above - and with
them 17 cross-references (`docs/cross-reference-schema.md`).

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
244 in-entry (90 standalone asides + 154 interpolations) against 861
inside back-matter footnote bodies and the two introductions - already
extracted whole as part of those records, not decomposed further. (232
in-entry on the first pass: recovering J02 Chapter I's undated opening
fragments as records brought 4 more asides and 8 more interpolations
within reach, among them "[Part of leaf missing here.]" and "[A third of a
page torn out here.]".) `tests/test_editorial.py`'s
`TestAgainstTheRealEvidenceCorpus` pins both the raw-text reconciliation
counts above and the extracted-record counts (880 footnotes, 90 standalone
asides, 154 interpolations, 2 introductions) rather than either number in
isolation.

## Indexing (issue #7's `memoria rebuild`)

`memoria rebuild` (`src/memoria/index.py`) runs
`extract_editorial_apparatus` on every normalized record - journal and
letter alike, as of issue #56 - before writing or indexing anything, so
the FTS5 index and `sources/normalized/` both reflect stripped,
apparatus-free evidence text for both source types, not the unstripped
paragraphs `normalize_journals`/`normalize_letters` alone produce. Every
`EditorialRecord` is indexed too, under `source_type: "editorial"`, so
`memoria.index.search(..., exclude_editorial=True)` genuinely excludes
footnotes, asides, and interpolations from a search - across both the
journals and the letters - rather than being a no-op (PR #51 review round
1, BLOCKING 1; issue #56 closed the gap that left it a no-op over the
letters specifically).
