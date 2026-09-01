# Cross-reference schema

Forces issue #8's "ground truth the whole machine-scored track is scored
against". Implemented by `src/memoria/cross_references.py`, building on
`src/memoria/editorial.py` (issue #5).

## What a cross-reference is

The 1906 edition's editors record, footnote by footnote, which journal
passage was reused in which of Thoreau's published books - e.g. footnote 40
of Journal I reads `[_Week_, p. 319; Riv. 395.]`. That footnote's *body* -
already parsed out of the volume's back-matter `FOOTNOTES` section and
linked back to the evidence paragraph its `[40]` marker sits in by
`extract_editorial_apparatus` (issue #5) - is itself the citation. This
module does not re-scan the raw corpus: it reads the `footnote`-type
`EditorialRecord`s issue #5 already produced, filters the ones that carry an
actual page citation to one of the published works, and tables them.

A citation is never resolved to a location in the held *Walden*/*A Week*
text - that is adjudication work, out of scope for this issue (part 05 §6,
issue #8's own "What to build"). The target side is stored exactly as
written.

## Table fields

Written as YAML to `sources/normalized/cross-references.yaml` - a list of
rows, each:

| Field | Meaning |
|---|---|
| `source_record_id` | The journal-side `SRC-` ID the citing footnote's marker was found in. |
| `source_anchor` | The journal-side paragraph anchor (`record.anchor_id(n)` form) the marker sits in. |
| `target_work` | The published work cited: `Week`, `Walden`, `Excursions`, `Cape Cod`, `The Service`, or `Maine Woods`. |
| `resolvable` | `true` for `Week`/`Walden` (held in the corpus, part 04's downloaded targets); `false` otherwise. |
| `citation` | The footnote's full body text, verbatim - never parsed apart to isolate one work's page numbers from another's (see "One footnote, more than one citation" below). |

A footnote whose marker falls outside the entries `normalize_journals`
covers - Torrey's Introduction, or J02 Chapter I's own heading line (see
`docs/editorial-record-schema.md`'s "Known gaps") - has no `SRC-` ID or
anchor to point at, and is excluded from the table entirely rather than
carried with a null source. Only 4 footnotes now fall in this gap, and none
of them is a citation, so the table loses nothing to it.

Until J02 Chapter I's undated opening fragments were recovered as records
(`docs/normalized-record-schema.md`), 29 footnotes fell in this gap, 17 of
them citations - 10 *Walden*, 5 *Excursions*, 2 *Cape Cod*. Those 17 are in
the table below.

## One footnote, more than one citation

A footnote can cite more than one published work in the same body - a
passage reused in both *Week* and *The Service*, say:

```
[40] [_Week_, p. 183; Riv. 227. _The Service_, p. 13.]
```

Each cited work is its own row (same `source_record_id`/`source_anchor`,
different `target_work`), since each names a distinct journal-passage-to-
book fact - the thing this table exists to hold. `citation` repeats the
whole footnote body verbatim on both rows, rather than attempting to slice
out just the one work's page numbers: doing that reliably (this same
footnote's `Riv. 227` belongs to *Week*, not *The Service*, and nothing
marks the boundary except word order) risks introducing a parsing error of
this module's own into what is supposed to be ground truth.

## What is *not* a cross-reference

- **Internal journal page references** (`[See p. 106.]`, RECON.md §4(b)'s
  ~14 internal refs) - resolvable via the journal HTML's own page anchors,
  never a citation of a published work, and correctly excluded by requiring
  a known work title be present.
- **A title mentioned with no page reference** - a textual-variant footnote
  discussing a wording difference ("though `_Walden_` has 'great.'") with
  nothing to look up.
- **A citation to a different book entirely** - Sanborn's *Thoreau*
  biography, E. W. Emerson's *Emerson in Concord*, Hawthorne's *American
  Note-Books* - excluded by construction: they are not one of the six
  published-work titles this table recognizes.

## Deviation from RECON.md

RECON.md §4(b) states 628 cross-references (430 J01 + 198 J02), 364 landing
on held works (`Week`, `Walden`). Mechanically re-deriving the table from
the footnote bodies (rather than trusting RECON's own summary count -
the same discipline issues #3-#6 already applied to date headings, the
weekday checksum, and footnote/span counts) finds **668** cross-references,
of which **379** resolvable and **289** unresolvable. (651/369/282 on the
first pass, before the 17 citations stranded on J02's undated opening
fragments were recovered with them.)

The gap traces to three things RECON's own count appears to miss:

- **Multi-work footnotes.** A footnote citing two published works (see
  above) is one footnote but two cross-references; RECON's methodology,
  whatever it was, evidently counted at most one citation per footnote.
- **A `_Cape Cod, and Miscellanies_` combined-title variant** (19
  occurrences in J02) and a handful of `Week` citations missing their
  italic markup (a transcription inconsistency in the source, not a
  different citation form) - both genuine citations RECON's own count
  appears to have missed via a narrower title pattern.
- **A sixth published work, `Maine Woods`, cited once** (J02) - not held in
  the corpus (correctly unresolvable), but not named anywhere in RECON.md
  §4(b)'s work table either.

All three were checked by hand against the raw text before being folded
into the table (`tests/test_cross_references.py`'s
`TestAgainstTheRealEvidenceCorpus` asserts the reconciled counts, not
RECON's). No cross-reference RECON's own count would have caught is lost by
this module - every deviation found is an addition, the same pattern issues
#3 and #4 already documented (558 vs. RECON's 448 date headings, 152 vs.
RECON's ~100 weekday-bearing headings).

## Indexing

Cross-references are not indexed into `.memoria/index.db` (issue #7): they
are a table over evidence *facts* (which passage became which book
passage), not searchable text of their own, and every `source_record_id`/
`source_anchor` they carry already points at evidence the index does cover.
`memoria rebuild` still regenerates `cross-references.yaml` alongside the
index, in lockstep with `memoria normalize`
(`tests/test_cli.py::test_rebuild_produces_byte_identical_output_to_normalize`).
