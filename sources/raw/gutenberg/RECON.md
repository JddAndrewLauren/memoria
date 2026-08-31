# RECON — Memoria PoC corpus (Thoreau / Project Gutenberg)

Retrieved 2026-08-31. 10 files (5 txt + 5 html), 661,946 words of text.
No file has been modified. All findings below are read-only observations.

| ID | Role | Work | Words | Lines |
|---|---|---|---|---|
| 57393 | evidence | Journal I, 1837–1846 (Writings vol. VII, 1906) | 139,336 | 17,561 |
| 59031 | evidence | Journal II, 1850–Sep 15 1851 (Writings vol. VIII, 1906) | 142,119 | 15,490 |
| 43523 | evidence | Familiar Letters (Writings vol. VI, 1906, ed. Sanborn) | 143,211 | 18,452 |
| 205 | audit_target | Walden, and On The Duty Of Civil Disobedience | 118,874 | 10,600 |
| 4232 | audit_target | A Week on the Concord and Merrimack Rivers | 118,406 | 12,338 |

## 0. Deviation from the task spec — Walden ID changed

**The spec's ID 26289 is an audiobook, not a text.** `gutenberg.org/files/26289/`
contains only `m4b/`, `mp3/`, `ogg/`, `spx/` directories plus a readme and index.
No `.txt` or `.html` edition exists under that ID; both cache URLs returned 404.

Per the spec's instruction to check the ebook page rather than guess, I searched
Gutenberg and substituted **ID 205, "Walden, and On The Duty Of Civil Disobedience"**
(23,094 downloads vs 4,097 for the audiobook). This is the standard Gutenberg
Walden text. Flagging it because it changes a corpus identifier you specified.

## 1. Proofread text, not OCR — confirmed

All five texts are Distributed Proofreaders output, not raw OCR.

- **Explicit provenance.** J01 carries `Produced by Melissa McDaniel and the Online
  Distributed Proofreading Team at http://www.pgdp.net (This file was produced from
  images generously made available by The Internet Archive)`, plus a Transcriber's
  Note declaring the editorial policy (below).
- **Zero ligature corruption.** No `ﬁ ﬂ ﬀ ﬃ` in any file.
- **Zero l/1 and rn→m confusions**, the two commonest OCR signatures.
- **No stray page numbers mid-sentence.** A scan for bare numbers inside prose
  returned 8–45 hits per file; I inspected them and *all* are legitimate text —
  mileages (`Walked to Concord [N. H.], 10 miles`), years (`In 449 three Saxon
  cyules arrived`), and Thoreau's own page counts (`_End of my Journal of 546
  pages._`). No OCR noise.
- **Encoding is clean.** All five are valid UTF-8, no BOM, CRLF line endings
  throughout (`\r\n` on every line — the normalizer must handle this).

The one caveat is deliberate, not defective. J01's Transcriber's Note states:

```
Inconsistent hyphenation and spelling in the original document have been preserved.
Obvious typographical errors have been corrected.
Italic text is denoted by _underscores_.
The following alternate spellings were noted, but retained:
   contemporaries and cotemporaries / Bramins and Brahmins
   Shakspeare and Shakespeare / Sanskrit and Sanscrit / Catskills and Caatskills
```

Those retained variants are **alias-resolution test material, not errors** — do not
normalize them away. `[?]` (9 in J01, 5 in J02) marks editorially uncertain readings
and `[_sic_]` (8 in J01, 22 in J02) marks preserved originals; both are meaningful.

## 2. Gutenberg content boundaries

| File | START marker | END marker | Body begins |
|---|---|---|---|
| pg57393.txt | L31 | L17210 | **L1331** (`THE JOURNAL OF HENRY DAVID THOREAU`) |
| pg59031.txt | L31 | L15139 | **L308** (`THE JOURNAL OF HENRY DAVID THOREAU`) |
| pg43523.txt | L32 | L18101 | **L189** (`INTRODUCTION`, Sanborn's) |
| pg205.txt | L27 | L10249 | **L79** (`WALDEN`) |
| pg4232.txt | L27 | L11987 | **L98** (`CONCORD RIVER`) |

Exact marker text, e.g.:
```
*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 01, 1837-1846 ***
*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 01, 1837-1846 ***
```

**The front matter is large and must be excluded from evidence.** J01 carries
~1,300 lines before the first journal entry: publisher's boilerplate, Transcriber's
Note, half-title, Contents, Illustrations list, Publishers' Note, Editor's Preface,
and **Bradford Torrey's Introduction (L428–~L1290)**.

Torrey's Introduction is a 1906 editor writing about an 1837–46 diarist. Under §6
it is *retrospective evidence about the evidence* — it must not be ingested as
Thoreau's contemporaneous record. Same for Sanborn's Introduction in Familiar
Letters. These are genuinely useful as a distinct source type, but misclassifying
them silently poisons every date-leakage test in §43.3.

## 3. Journal date-heading conventions

### Entry headings — a small closed set, highly parseable

Entries open with a line-initial italic date. **All 299 (J01) and 149 (J02) date
headings are line-initial** — zero occur mid-line, so a `^_...` anchor is safe.

Verbatim examples from J01:
```
_Oct 22._ "What are you doing now?" he asked. "Do you keep a journal?"
_Oct. 24._ Every part of nature teaches that the passing away of one
_Jan. 24. Sunday._
_Sept. 29, 1842._
_May 3-4._
```

Observed forms, by frequency:

| Form | J01 | J02 |
|---|---|---|
| `_Mon. N._` (period after month) | 137 | 73 |
| `_Mon N._` (no period) | 81 | 35 |
| `_Mon. N. Weekday._` | ~60 | ~35 |
| `_Mon. N, N._` (two days) | 3 | — |
| `_Mon N-N._` (range) | 1 | — |
| `_Mon._` (month only, no day) | 2 | — |
| carrying an explicit year | 3 | 0 |

The month-period inconsistency (`Oct 22` vs `Oct. 24`) is *within the same page* —
it is original compositor variance, not corruption. Parse tolerantly.

### Chapter headings — and the two volumes disagree

**J01 chapters are bare years:**
```
I
1837
(ÆT. 20)
```
Chapter years found: `1837, 1838, 1839, 1840, 1841, 1842, 1845-1846, 1845-1847, 1837-1847`.

**J02 chapters are month-scoped:**
```
II          III                     VII
DECEMBER, 1850   JANUARY-APRIL, 1851    AUGUST, 1851
(ÆT. 33)         (ÆT. 33)               (ÆT. 34)
```
Full J02 chapter map: I `1850` (L314), II `DECEMBER, 1850` (L3695), III
`JANUARY-APRIL, 1851` (L4092), IV `MAY, 1851` (L5614), V `JUNE, 1851` (L6713),
VI `JULY, 1851` (L8272), VII `AUGUST, 1851` (L10555), VIII `SEPTEMBER, 1851` (L12521).

### Assessment: entry-boundary parsing is easy; `recorded_date` resolution is not

Splitting entries is straightforward — a line-initial italic date is an unambiguous
boundary. **Assigning a full date is the real work**, because entry headings carry
month and day but almost never the year (3 of 448). The year must come from the
enclosing chapter, and:

- **J02 chapters II–VIII are trivially safe** — the chapter names its month *and*
  year, so entries resolve exactly.
- **J01 chapters 1837–1842 are safe** — one year each.
- **J01 chapters `1845-1846`, `1845-1847`, `1837-1847` are ambiguous.** An entry
  reading `_Feb. 22_` inside a chapter spanning 1845–1847 has three candidate years.

**There is a free checksum.** Roughly 100 headings carry a weekday
(`_Jan. 24. Sunday._`). For any month/day, only one candidate year normally puts
that date on that weekday — so the weekday resolves the ambiguity exactly, and
where it does not, it flags a genuine editorial problem worth surfacing rather
than guessing. I would make weekday-checked resolution the primary path and mark
the remainder `date_confidence: inferred` rather than `exact`.

**J02 Chapter I has no date headings at all.** It opens (L319) with undated
fragments separated by `*   *   *   *   *` dividers (581 such dividers in J01, 156
in J02). These are transcript-book extracts, not dated entries. They need
`date_confidence: chapter-only` — scoped to 1850, no day.

## 4. Editorial apparatus

### (a) Footnotes

Inline markers `[N]`: **1,017 in J01, 744 in J02**. These are Torrey's editorial
footnotes, not Thoreau's. They interleave directly with Thoreau's prose
(`...my second growth.[4]`) and must be stripped from the evidence text and
retained as separate annotation, or they will contaminate quotations.

Bracketed editor prose also appears inline as whole passages, e.g.:
```
[The small manuscript volume bearing on its first fly-leaf the legend printed on
the preceding page is evidently a transcript of unused passages in the early
journals, and this is also the case with several succeeding small volumes.]
[A pencil interlineation in this paragraph is as follows:]
[The italics are Thoreau's.]
```
~570 (J01) / ~485 (J02) bracketed spans are neither footnote markers nor
cross-references. They are 1906 editorial voice inside 1837 evidence — the
single most important thing for the normalizer to segregate.

### (b) Cross-references to the published works — the ground truth

**Format is exactly as you described, but the work title is italicised**, which
matters for the regex:
```
[_Week_, p. 319; Riv. 395.]
[_Walden_, pp. 32, 33; Riv. 48, 49.]
[_Excursions_, pp. 117, 118; Riv. 144, 145.]
[See _Walden_, p. 185; Riv. 262.]
[Cf. _Week_, p. ...]
```
`p.`/`pp.` is the 1906 Manuscript Edition page; `Riv.` is the Riverside Edition page.
Optional `See ` / `Cf. ` prefixes. 389/430 (J01) and 197/198 (J02) carry both.

**Counts:**

| Target work | J01 | J02 | in our corpus? |
|---|---|---|---|
| _Week_ | 242 | 0 | **yes (4232)** |
| _Walden_ | 87 | 35 | **yes (205)** |
| _Excursions_ | 48 | 120 | no |
| _The Service_ | 39 | 0 | no |
| _Cape Cod_ | 14 | 43 | no |
| **total** | **430** | **198** | **364 land on downloaded targets** |

### THE IMPORTANT PROBLEM: these cannot be resolved by page number

The cross-references cite pages in the **1906 Manuscript Edition** and the
**Riverside Edition**. Our audit targets are neither, and:

- `pg205.txt`, `pg4232.txt`, `pg205-images.html`, `pg4232-images.html` contain
  **zero page markers of any kind** — no `[Page N]`, no `id="Page_N"`, no
  `class="pagenum"`. I checked all four files.
- By contrast, the **journal and letters HTML files *do* carry page anchors** —
  `id="Page_304"` with `class="pagenum"`: **486 in J01, 503 in J02, 458 in
  Letters**. The `.txt` versions do not.

So the corpus is asymmetric: the *evidence* side is page-addressable (via HTML),
the *audit-target* side is not, and they are different editions anyway.

**Consequence:** the 364 usable cross-references are ground truth for *which
journal passage was reused in which book*, but resolving them to a location in
our Walden/Week text requires **fuzzy text matching**, not a page-number join.
Thoreau also rewrote heavily between journal and book, so matches are paraphrases
rather than quotations.

I'd argue this is better than it sounds. A page-number join would have tested
nothing; passage-level matching under paraphrase is precisely the §17 manuscript-
impact and §20 provenance task, with 364 labelled instances. But it is a
retrieval problem to be built, not a lookup — worth knowing before you scope it.

Note also `[See p. 106.]`, `[See pp. 124 and 174.]` (~14 in J01) — *internal*
journal page refs. These **are** resolvable, via the HTML page anchors.

## 5. Familiar Letters — second source type

130 letters, **43 distinct recipients**, 136 place+date datelines. Structure:
```
TO HELEN THOREAU (AT TAUNTON).

     CONCORD, October 27, 1837.

DEAR HELEN,--Please you, let the defendant say a few words in defense
```
Header, indented dateline, salutation, body, indented signature. Datelines carry
**full explicit dates including year** — unlike the journals. Top recipients:
Harrison Blake (31), Daniel Ricketson (22), R. W. Emerson (15 across four
location forms), Mrs. Lucy Brown (5), Helen Thoreau (4+).

**This is strong §7 alias material, for free.** The same person appears as
`TO R. W. EMERSON (AT CONCORD)`, `(IN ENGLAND)`, `(AT NEW YORK)`; Helen Thoreau as
`(AT TAUNTON)` and `(AT ROXBURY)`. And the Thoreau family shares a surname across
`JOHN THOREAU`, `SOPHIA THOREAU`, `HELEN THOREAU`, `MRS. THOREAU` — exactly the
unsafe-merge hazard §7 warns about.

## 6. Unexpected findings

1. **Quote characters are inconsistent *across volumes of the same edition*.**
   J01 and Familiar Letters use straight ASCII quotes (J01: 1,028 `"`, 11 `“`).
   J02 uses curly Unicode (0 `"`, 337 `“`, 756 `’`). Any exact-match search or
   quotation-locating tool must normalize quotes or it will silently fail on one
   volume and succeed on another.
2. **Greek passages.** J01 contains ~250 Greek characters (`Λόγος τοῦ...`),
   Week ~40. Not corruption — Thoreau quoting classical sources. Must survive
   normalization intact.
3. **Illustration markers**: `[Illustration: _White Violets_ (_page 304_)]` —
   7 in J01, 24 in J02. Carry page references in their captions.
4. **`™` appears 17 times in every file** — Project Gutenberg™ boilerplate only,
   not content.
5. **Æ/ÆT.** — `(ÆT. 20)` age markers on every chapter heading. Useful as a
   secondary date check: age plus known birth year (1817-07-12) constrains the year.
6. **`A Week`'s chapters are weekday names** (`SATURDAY`…`FRIDAY`), which will
   collide with the weekday tokens in journal date headings if both are parsed
   by the same rules.
7. Walden bundles **two works** — `WALDEN` (to L9417 `THE END`) and
   `ON THE DUTY OF CIVIL DISOBEDIENCE` (L9421+). They should be separate records.

## 7. Summary

- **10 files on disk, all hashed, manifest complete.** Nothing failed verification.
- **Total corpus: 661,946 words** across 5 texts.
- **One spec correction:** Walden ID 26289 is an audiobook; used ID 205 instead.
- **Text quality: excellent.** Genuinely proofread, valid UTF-8, no OCR artifacts.
- **Entry-boundary parsing: easy.** Line-initial italic dates, closed form set,
  zero mid-line occurrences.
- **`recorded_date` resolution: moderate.** Years come from chapter headings, and
  three J01 chapters span multiple years. Weekday tokens on ~100 headings resolve
  the ambiguity; J02 Chapter I is undated and should stay that way.
- **Biggest issue: the cross-reference ground truth needs text matching, not page
  lookup**, because the audit targets have no pagination and are different editions.
  364 labelled journal→book links land on works we hold.
- **Biggest hazard: 1906 editorial voice is interleaved with 1837 evidence** —
  ~1,750 footnote markers, ~1,050 bracketed editorial spans, and two long editor
  introductions. Segregating these is prerequisite to any temporal-discipline claim.

Not proceeding to normalization, chunking, or indexing.
