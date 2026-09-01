import os
from pathlib import Path

import pytest
import yaml

from memoria.cross_references import (
    HELD_WORKS,
    UNHELD_WORKS,
    extract_cross_references,
    write_cross_references_table,
)
from memoria.editorial import extract_editorial_apparatus
from memoria.normalize import normalize_journals

from test_normalize import _write_fake_volumes

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"

# A footnote body carrying an inline "[N]" number wrapping its own
# citation - the shape the real corpus's FOOTNOTES section actually uses
# (see docs/normalized-record-schema.md's cross-reference examples): the
# marker in entry text is a bare number, and it is the footnote *body*
# text that itself carries a bracketed citation of the published work.
_FAKE_JOURNAL_WITH_CROSS_REFERENCES = (
    "The Project Gutenberg eBook of Journal 99\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
    "\r\n"
    "INTRODUCTION\r\n"
    "\r\n"
    "Some editorial prose about the volume.[1]\r\n"
    "\r\n"
    "THE JOURNAL OF HENRY DAVID THOREAU\r\n"
    "\r\n"
    "I\r\n"
    "\r\n"
    "1899\r\n"
    "\r\n"
    '_Oct 22._ A single-work citation.[2] he wrote.\r\n'
    "\r\n"
    '_Oct. 24._ An unheld-work citation.[3] followed by more prose.\r\n'
    "\r\n"
    '_Oct. 26._ A multi-work citation.[4] closes the passage.\r\n'
    "\r\n"
    '_Oct. 28._ An internal page reference.[5] not a cross-reference.\r\n'
    "\r\n"
    '_Oct. 30._ A title mention with no page number.[6] stays out.\r\n'
    "\r\n"
    "END OF VOLUME 99\r\n"
    "\r\n"
    "The Fake Press\r\n"
    "\r\n"
    "FOOTNOTES\r\n"
    "\r\n"
    "[1] [_Week_, p. 1; Riv. 2.]\r\n"
    "\r\n"
    "[2] [_Week_, p. 319; Riv. 395.]\r\n"
    "\r\n"
    "[3] [_Excursions_, p. 48; Riv. 60.]\r\n"
    "\r\n"
    "[4] [_Week_, p. 10; Riv. 12. _The Service_, p. 4.]\r\n"
    "\r\n"
    "[5] [See p. 106.]\r\n"
    "\r\n"
    "[6] [Plainly a variant, though _Walden_ has different wording.]\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
    "\r\n"
    "Updated editions will replace the previous one.\r\n"
)


# extract_editorial_apparatus also extracts the Familiar Letters
# introduction (issue #5), so the fake corpus needs a minimal letters file
# even though this module never reads letter records themselves.
_FAKE_LETTERS_TEXT = (
    "The Project Gutenberg eBook of Familiar Letters\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK FAMILIAR LETTERS ***\r\n"
    "\r\n"
    "INTRODUCTION\r\n"
    "\r\n"
    "Thoreau's letters give us the man behind the journal.\r\n"
    "\r\n"
    "FAMILIAR LETTERS OF THOREAU\r\n"
    "\r\n"
    "TO HELEN THOREAU (AT TAUNTON).\r\n"
    "\r\n"
    "     CONCORD, October 27, 1837.\r\n"
    "\r\n"
    "DEAR HELEN,--Please you, let the defendant say a few words.\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK FAMILIAR LETTERS ***\r\n"
)

_LETTERS_RAW_PATH = "raw/gutenberg/43523-familiar-letters/pg43523.txt"


def _write_fake_corpus(evidence_root):
    _write_fake_volumes(
        evidence_root,
        [_FAKE_JOURNAL_WITH_CROSS_REFERENCES, _FAKE_JOURNAL_WITH_CROSS_REFERENCES],
    )
    letters_path = evidence_root / _LETTERS_RAW_PATH
    letters_path.parent.mkdir(parents=True, exist_ok=True)
    letters_path.write_bytes(_FAKE_LETTERS_TEXT.encode("utf-8"))


def _extract(evidence_root):
    records = normalize_journals(evidence_root)
    editorial = extract_editorial_apparatus(evidence_root, records)
    return records, editorial


def test_single_work_citation_is_extracted_resolvable_and_linked(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    records, editorial = _extract(evidence_root)

    cross_references = extract_cross_references(editorial)

    entry = next(r for r in records if r.recorded_date == "Oct 22.")
    week_refs = [c for c in cross_references if c.target_work == "Week"]
    match = next(
        c for c in week_refs if c.source_record_id == entry.id
    )
    assert match.source_anchor == entry.anchor_id(1)
    assert match.resolvable is True
    assert match.citation == "[_Week_, p. 319; Riv. 395.]"


def test_unheld_work_citation_is_marked_unresolvable_with_work_named(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    records, editorial = _extract(evidence_root)

    cross_references = extract_cross_references(editorial)

    entry = next(r for r in records if r.recorded_date == "Oct. 24.")
    match = next(
        c
        for c in cross_references
        if c.source_record_id == entry.id and c.target_work == "Excursions"
    )
    assert match.resolvable is False


def test_a_footnote_citing_two_works_yields_two_cross_references(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    records, editorial = _extract(evidence_root)

    cross_references = extract_cross_references(editorial)

    entry = next(r for r in records if r.recorded_date == "Oct. 26.")
    matches = [c for c in cross_references if c.source_record_id == entry.id]
    works = {c.target_work for c in matches}
    assert works == {"Week", "The Service"}
    assert all(c.resolvable == (c.target_work in HELD_WORKS) for c in matches)


def test_internal_page_reference_is_not_a_cross_reference(tmp_path):
    # "[See p. 106.]" - RECON.md §4(b)'s ~14 internal journal page refs,
    # resolvable via the HTML page anchors, never a citation to a
    # published work: no italicized (or bare) work title at all.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    records, editorial = _extract(evidence_root)

    cross_references = extract_cross_references(editorial)

    entry = next(r for r in records if r.recorded_date == "Oct. 28.")
    assert not [c for c in cross_references if c.source_record_id == entry.id]


def test_title_mention_with_no_page_number_is_not_a_cross_reference(tmp_path):
    # A footnote can name a work in passing (a textual-variant note) with
    # no page reference at all - nothing to look anything up by, so it is
    # not ground truth for "this passage was reused here".
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    records, editorial = _extract(evidence_root)

    cross_references = extract_cross_references(editorial)

    entry = next(r for r in records if r.recorded_date == "Oct. 30.")
    assert not [c for c in cross_references if c.source_record_id == entry.id]


def test_a_footnote_whose_marker_is_unlinked_is_excluded_from_the_table(tmp_path):
    # Footnote [1] belongs to Torrey's Introduction, which extract_editorial_
    # apparatus does not further decompose (issue #5's known gap) - its
    # marker never links to an evidence paragraph, so there is no
    # journal-side SRC- ID/anchor to put in the table. Every acceptance
    # criterion here requires a resolved anchor, so it is dropped rather
    # than included with a null one.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    _, editorial = _extract(evidence_root)

    cross_references = extract_cross_references(editorial)

    footnote_1 = next(
        e
        for e in editorial
        if e.editorial_type == "footnote" and e.original_locator.endswith("footnote 1")
    )
    assert footnote_1.linked_record_id is None
    assert not any(c.citation == footnote_1.text for c in cross_references)


def test_every_cross_reference_resolves_to_an_existing_record_and_paragraph(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    records, editorial = _extract(evidence_root)

    cross_references = extract_cross_references(editorial)

    known_anchors = {
        record.anchor_id(n)
        for record in records
        for n in range(1, len(record.paragraphs) + 1)
    }
    known_ids = {record.id for record in records}
    assert cross_references  # the fake corpus does produce some
    for c in cross_references:
        assert c.source_record_id in known_ids
        assert c.source_anchor in known_anchors


def test_resolvable_and_unresolvable_partition_the_known_target_works():
    assert HELD_WORKS.isdisjoint(UNHELD_WORKS)


def test_write_cross_references_table_emits_readable_yaml(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    _, editorial = _extract(evidence_root)
    cross_references = extract_cross_references(editorial)
    output_path = tmp_path / "sources" / "normalized" / "cross-references.yaml"

    write_cross_references_table(cross_references, output_path)

    rows = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert len(rows) == len(cross_references)
    for field in (
        "source_record_id",
        "source_anchor",
        "target_work",
        "resolvable",
        "citation",
    ):
        assert field in rows[0]


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
class TestAgainstTheRealEvidenceCorpus:
    @pytest.fixture(scope="class")
    @staticmethod
    def cross_references():
        evidence_root = Path(os.environ[EVIDENCE_ROOT_ENV_VAR])
        records = normalize_journals(evidence_root)
        editorial = extract_editorial_apparatus(evidence_root, records)
        return extract_cross_references(editorial)

    def test_count_reconciles_against_recon(self, cross_references):
        # RECON.md §4(b) states 628 cross-references (430 J01 + 198 J02),
        # 364 landing on held works. Mechanically re-deriving them from the
        # footnote bodies (rather than trusting RECON's own summary count -
        # docs/cross-reference-schema.md's "Deviation from RECON.md")
        # finds more: RECON's own methodology misses footnotes citing more
        # than one published work (a passage reused in both _Week_ and
        # _The Service_, say - each is its own journal-passage-to-book
        # link), a "_Cape Cod, and Miscellanies_" combined-title variant,
        # a handful of citations to "Week" missing its italic markup, and
        # a citation to a sixth published work ("Maine Woods") RECON's own
        # table never names at all.
        #
        # 668, not the 651 of the first pass: recovering J02 Chapter I's
        # undated opening fragments as records (this branch) linked 17
        # footnotes whose markers used to fall outside every record - 10
        # _Walden_, 5 _Excursions_, 2 _Cape Cod_.
        assert len(cross_references) == 668

    def test_resolvable_and_unresolvable_counts(self, cross_references):
        resolvable = [c for c in cross_references if c.resolvable]
        unresolvable = [c for c in cross_references if not c.resolvable]
        assert len(resolvable) == 379
        assert len(unresolvable) == 289
        assert len(resolvable) + len(unresolvable) == len(cross_references)

    @pytest.fixture(scope="class")
    @staticmethod
    def evidence_records():
        evidence_root = Path(os.environ[EVIDENCE_ROOT_ENV_VAR])
        records = normalize_journals(evidence_root)
        extract_editorial_apparatus(evidence_root, records)
        return records

    def test_every_cross_reference_resolves_to_an_existing_record_and_paragraph(
        self, cross_references, evidence_records
    ):
        known_ids = {record.id for record in evidence_records}
        known_anchors = {
            record.anchor_id(n)
            for record in evidence_records
            for n in range(1, len(record.paragraphs) + 1)
        }
        assert cross_references
        for c in cross_references:
            assert c.source_record_id in known_ids
            assert c.source_anchor in known_anchors

    def test_every_unresolvable_reference_names_one_of_the_unheld_works(
        self, cross_references
    ):
        for c in cross_references:
            if not c.resolvable:
                assert c.target_work in UNHELD_WORKS
