# The M0 check-suite

Closes issue #10. M0's promise is that the normalized evidence can be trusted, and
`docs/plan/16-build-order.md` puts normalization first because "it is the one place a
mistake silently invalidates every downstream number". This document is where that
claim is made checkable: what the one command runs, what each `RECON.md` count
reconciles to, and which regression test would catch each mismatch M0 found on the way.

## The one command

```
MEMORIA_EVIDENCE_ROOT=/absolute/path/to/thoreau-evidence .venv/bin/python scripts/m0-check.py
```

It runs three things and reports pass/fail per check:

| | What it checks |
|---|---|
| `memoria validate` | raw-file SHA-256 against the manifest, dangling `SRC-` references, answer-key drift |
| `memoria rebuild` | the whole derived state regenerated from evidence, over the full corpus |
| `pytest tests/` | 201 checks, of which 91 carry the `m0` marker and run against the real corpus |

### Why a skip is a failure

Every real-corpus check is gated on `MEMORIA_EVIDENCE_ROOT`. Without it they skip and
`pytest` still exits 0:

```
$ pytest tests/ -q          # with no corpus
110 passed, 91 skipped      # exit 0
```

That is a green suite that reconciled nothing — the exact silence M0 exists to break.
So `scripts/m0-check.py` refuses to start when the corpus is absent, and counts a
skipped `m0` check as a failed one. It also fails if any of the six checks named in its
`REQUIRED_CHECKS` table has gone missing, so renaming one cannot quietly shrink the M0
suite while the suite still reports 201/201.

The script asserts no counts of its own. Every figure below lives in the test that pins
it, and in the schema doc that argues for it — never in a third place that could drift.

## Reconciliation against `RECON.md`

`RECON.md` (in the evidence repo, `raw/gutenberg/RECON.md`) is reconnaissance, not
ground truth. The settled discipline of M0 is to **re-derive rather than trust the
summary**, and to assert the re-derived number with RECON's stated alongside it.
Four of the five counts part 16 names came out different, and **every deviation found
is an addition** — no item RECON's own count would have caught is lost.

| Quantity | `RECON.md` states | Verified | Reasoning | Pinned by |
|---|---|---|---|---|
| Date headings | **448** (299 J01 + 149 J02) | **558** (401 + 157) | `normalized-record-schema.md` "Deviation from RECON.md's date-heading count" | `tests/test_normalize.py::TestAgainstTheRealEvidenceCorpus::test_date_headings_found_are_reconciled_against_recon` |
| Letters | **130** | **130** — exact | `normalized-record-schema.md` "Letters (issue #6)" | `tests/test_letters.py::TestAgainstTheRealEvidenceCorpus::test_letter_count_matches_recon` |
| Distinct recipients | **43** | **41** table rows | `normalized-record-schema.md` "Recipients table (issue #6)" | `tests/test_letters.py::TestAgainstTheRealEvidenceCorpus::test_recipient_count_matches_recon` |
| Footnote markers `[N]` | **~1,750** (1,017 / 744) | **1,761** (1,017 / 744) — per-file exact | `editorial-record-schema.md` "Reconciliation against RECON.md" | `tests/test_editorial.py::TestAgainstTheRealEvidenceCorpus::test_footnote_marker_counts_reconcile_against_recon` |
| Bracketed spans | **~1,050** (~570 / ~485) | **1,105** (593 / 512) | `editorial-record-schema.md` "Reconciliation against RECON.md" | `tests/test_editorial.py::TestAgainstTheRealEvidenceCorpus::test_bracketed_span_counts_reconcile_against_recon` |
| Evidence free of editorial voice | — | sampled, asserted | `editorial-record-schema.md` | `tests/test_editorial.py::TestAgainstTheRealEvidenceCorpus::test_sampled_evidence_records_contain_no_editorial_voice` |

Three further counts reconcile the same way, outside part 16's check-suite line item:

| Quantity | `RECON.md` states | Verified | Pinned by |
|---|---|---|---|
| Weekday-bearing headings | "roughly **100**" | **152** found, **150** confirm as `exact` | `tests/test_year_resolution.py::TestAgainstTheRealEvidenceCorpus::test_confidence_counts_reconcile_with_the_weekday_checked_headings` |
| Cross-references | **628** (430 / 198), 364 on held works | **668**, **379** on held works | `tests/test_cross_references.py::TestAgainstTheRealEvidenceCorpus::test_count_reconciles_against_recon` |
| Answer-key links resolved | premise: unresolvable by page lookup | **348 of 379** | `tests/test_answer_key.py::TestAgainstTheRealEvidenceCorpus` |

The two remaining weekday headings that do not confirm — `SRC-000332`
(`_Sept. 5. Saturday._`, 1841-09-05 was a Sunday) and `SRC-000493`
(`_May 6. Monday._`, 1851-05-06 was a Tuesday) — are genuine editorial or transcription
discrepancies in the 1906 source, not parsing bugs. `resolve_years()` prints them as
warnings and dates both entries `inferred` rather than silently accepting `exact` —
which is RECON §3's own prediction: "where it does not [match], it flags a genuine
editorial problem worth surfacing rather than guessing."

### Two RECON claims the corpus falsified

- **§3, "J02 Chapter I has no date headings at all."** It contains 22 line-initial date
  headings inside RECON's own stated line range for that chapter. Reproduced
  independently by the PR #48 review. The 448 → 558 gap traces to RECON's counter
  requiring an abbreviating period, so missing unabbreviated `May`, `June`, `July`,
  `March`, `April`.
- **§4, the target side "requires fuzzy text matching, not a page-number join."** True
  of the texts held, false as a statement about the world: the cited editions are
  digitized page by page, so the target side is a page lookup plus an alignment between
  two printings. `docs/answer-key-protocol.md`.

## Every M0 mismatch, and the test that catches it again

§43's discipline is one sentence — "Every consequential real-world failure becomes a
regression test." This is the inventory for M0. Each row is a mismatch actually found
while building the milestone, not an imagined one; every one of them is covered.

| Mismatch | Where it came from | Regression test |
|---|---|---|
| Back matter (colophon, Torrey's endnotes) swallowed whole into each volume's last entry, as `contemporaneous: true` | PR #48 review round 1 | `test_normalize.py::test_normalize_journals_excludes_back_matter_after_the_last_entry`, `::TestAgainstTheRealEvidenceCorpus::test_no_normalized_record_contains_the_trailing_back_matter` |
| `DATE_HEADING_RE` missed 4 genuine headings (to-range, place qualifier, weekday + second word) — 554, not 558 | PR #48 review round 1 | `test_normalize.py::test_date_heading_re_matches_previously_missed_forms` (parametrized over the exact four), plus the recall check `::test_no_line_initial_month_prefixed_line_is_left_unmatched` that would have caught it automatically |
| `rebuild()` omitted `resolve_years`, reverting every record to `unresolved` on rebuild | PR #50 review round 1 | `test_index.py::test_rebuild_resolves_years_and_never_leaves_a_journal_record_unresolved` |
| 41 space-before-punctuation artifacts left by bracket excision | PR #51 review round 1 | `test_editorial.py::TestAgainstTheRealEvidenceCorpus::test_no_evidence_paragraph_has_a_space_before_punctuation` |
| 4 sentence-completing interpolations excised instead of unbracketed, mangling Thoreau's sentences | PR #51 review round 1 | `test_editorial.py::TestAgainstTheRealEvidenceCorpus::test_sentence_completing_interpolations_are_kept_in_the_evidence_text` (pins the four phrases) |
| `_extract_dateline` scanned unboundedly and assigned closing signature blocks as datelines | PR #52 review round 1 | `test_letters.py::test_normalize_letters_with_no_dateline_gets_an_empty_dateline_not_a_signature`, `::TestAgainstTheRealEvidenceCorpus::test_every_letters_dateline_is_plausibly_shaped_or_empty` |
| `salutation` fell back to a bracketed editorial annotation | PR #52 review round 1 | `test_letters.py::TestAgainstTheRealEvidenceCorpus::test_no_salutation_is_an_editorial_annotation` |
| J02 Chapter I's ~1,000 undated opening lines discarded entirely; `chapter-only` implemented as the inverse of its documented meaning | `10792ad` | `test_normalize.py::TestAgainstTheRealEvidenceCorpus::test_j02_chapter_i_undated_opening_is_recovered_as_fragment_records` (29 fragments, `SRC-000402..430`), `test_year_resolution.py::test_resolve_years_marks_a_volumes_undated_opening_fragments_chapter_only` |
| *A Week*'s poem title `THE INWARD MORNING` taken for a ninth chapter; *Walden*'s title-page line started its last chapter 9,385 lines early | `6149102` | `test_normalize.py::TestTargetNormalization::test_a_poem_title_in_capitals_is_not_taken_for_a_chapter`, `::test_the_title_page_line_does_not_start_civil_disobedience_early` |
| Leaf-numbering offset: 3 of 4 scanned volumes number each leaf one page ahead, and the drift fit absorbed it — 243 of 360 rows one page late | `90ef13c`, **found by eye in the spot check and nowhere else** | `test_editions.py::test_each_volume_is_keyed_by_the_number_printed_on_the_page`, `::test_the_running_heads_agree_all_but_unanimously` |
| A wide page-range citation resolved to 198 paragraphs — a third of *A Week* | `59b51ef` | `test_answer_key.py::test_no_scored_row_names_a_stretch_of_book_instead_of_a_passage`, `::test_the_tolerance_is_not_what_admits_the_rows` (replacing a tautological test) |
| `_clean_ws` ran on every evidence paragraph: 540 of 558 records differed on whitespace alone, quoted verse lost its line structure | #55 | `test_editorial.py::TestAgainstTheRealEvidenceCorpus::test_records_with_no_excised_span_are_unchanged_from_raw_derived_text` (the mutation guard), `::test_a_real_verse_bearing_record_retains_its_line_structure` |
| 135 bracket-bearing rows in the letters ID range meant `exclude_editorial=True` silently meant "journals only" | #56 | `test_editorial.py::TestLettersAgainstTheRealEvidenceCorpus::test_footnote_and_span_counts`, `test_index.py::test_search_excludes_letters_editorial_content` |
| Footnote-block terminator blacklist missed real resume shapes — footnote 34 ran 8,259 chars past its end | #56 review round 1 | `test_editorial.py::test_letters_footnote_block_ends_at_a_chapter_heading_or_a_letter_to_thoreau`, `::TestLettersAgainstTheRealEvidenceCorpus::test_footnote_bodies_stop_at_the_next_chapter_or_letter_to_thoreau` |
| All 130 letters carried `date_confidence: unresolved` while their datelines state the year in plain text | #57 | `test_letters.py::TestAgainstTheRealEvidenceCorpus::test_date_confidence_split_across_all_130_letters` (126 inferred, the 4 unresolved pinned by ID) |
| `_extract_salutation` fell back to body prose — 6 letters passed Thoreau's own words off as a greeting; `_SALUTATION_RE` also missed `MR. WILEY,[75]--` | #58 | `test_letters.py::test_normalize_letters_with_no_salutation_gets_an_empty_salutation_not_prose`, `::test_normalize_letters_recognises_a_salutation_with_a_footnote_marker`, `::TestAgainstTheRealEvidenceCorpus::test_every_letters_salutation_is_plausibly_shaped_or_empty` |
| `_excise_footnote_blocks` cut the whole tail from the first marker: four real stretches reached no record at all, including the letters Channing, Lane and Agassiz wrote *to* Thoreau | `8c9f831` | `test_letters.py::test_normalize_letters_keeps_the_text_after_a_midvolume_footnote_block`, `::TestAgainstTheRealEvidenceCorpus::test_every_letter_to_thoreau_reaches_a_record`, `::test_no_footnote_block_text_reaches_a_letter_record` |
| Heading footnote markers `[15]/[41]/[42]` carried verbatim into `recipient`, splitting two correspondents into spurious table rows | `8c9f831` | `test_letters.py::TestAgainstTheRealEvidenceCorpus::test_a_heading_footnote_marker_is_not_part_of_the_recipient` (pins `SRC-000009/48/56`) |

There are no `TODO`, `FIXME`, `xfail` or unconditional `skip` markers anywhere in `src/`
or `tests/`. Known-and-accepted gaps are documented as prose instead — see
`editorial-record-schema.md` "Known gaps".

## The gate

`docs/plan/16-build-order.md` closes M0 with four acts, walked by hand and recorded on
issue #10 before it may be closed. A gate is "a concrete, author-visible act that either
works or does not"; it is deliberately not a test, and a box is not ticked for a human
verification that did not happen (the precedent issue #9 set when it closed with its
spot-check box explicitly unticked).
