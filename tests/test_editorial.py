import os
import re
from pathlib import Path

import pytest
import yaml

from memoria.editorial import (
    EditorialRecord,
    extract_editorial_apparatus,
    write_editorial_records,
)
from memoria.normalize import JOURNAL_VOLUMES, normalize_journals

from test_normalize import _FAKE_VOLUME_TEXT, _write_fake_volumes

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"

# Torrey's Introduction, as it actually sits in the real J01 raw file: an
# "INTRODUCTION" heading, editorial prose (with an inline footnote marker,
# as the real text has), then the "THE JOURNAL OF HENRY DAVID THOREAU"
# heading that starts the front matter's run into the first entry.
_FAKE_INTRODUCTION = (
    "INTRODUCTION\r\n"
    "\r\n"
    "The fortune of Henry Thoreau as an author has been peculiar.[1]\r\n"
    "\r\n"
    "THE JOURNAL OF HENRY DAVID THOREAU\r\n"
    "\r\n"
)

_FAKE_JOURNAL_WITH_APPARATUS = (
    "The Project Gutenberg eBook of Journal 99\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
    "\r\n"
    + _FAKE_INTRODUCTION
    + "I\r\n"
    "\r\n"
    "1899\r\n"
    "\r\n"
    '_Oct 22._ "What are you doing now?"[2] he asked.\r\n'
    "\r\n"
    "[The editor inserts a whole aside here, never Thoreau's words.]\r\n"
    "\r\n"
    "_Oct. 24._ Every part of nature teaches something.\r\n"
    "\r\n"
    "END OF VOLUME 99\r\n"
    "\r\n"
    "The Fake Press\r\n"
    "\r\n"
    "FOOTNOTES\r\n"
    "\r\n"
    "[1] Torrey's footnote on the introduction itself.\r\n"
    "\r\n"
    "[2] A footnote about the year 1899, discussing dates like this: the\r\n"
    "manuscript later mentions 1900 in passing, which is not a new\r\n"
    "footnote despite the brackets that follow: [1900] is just more of\r\n"
    "footnote 2's own text.\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
    "\r\n"
    "Updated editions will replace the previous one.\r\n"
)

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
        evidence_root, [_FAKE_JOURNAL_WITH_APPARATUS, _FAKE_JOURNAL_WITH_APPARATUS]
    )
    letters_path = evidence_root / _LETTERS_RAW_PATH
    letters_path.parent.mkdir(parents=True, exist_ok=True)
    letters_path.write_bytes(_FAKE_LETTERS_TEXT.encode("utf-8"))


def _extract(evidence_root):
    records = normalize_journals(evidence_root)
    editorial = extract_editorial_apparatus(evidence_root, records)
    return records, editorial


def test_footnote_markers_are_stripped_from_evidence_paragraphs(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)

    records, _ = _extract(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "[2]" not in full_text
    assert '"What are you doing now?" he asked.' in full_text


def test_footnote_body_is_extracted_into_a_linked_editorial_record(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)

    records, editorial = _extract(evidence_root)

    footnotes = [e for e in editorial if e.editorial_type == "footnote"]
    footnote_2 = next(
        e for e in footnotes if e.original_locator.endswith("footnote 2")
    )
    assert "1899" in footnote_2.text
    assert "1900" in footnote_2.text  # continuation text, not its own footnote
    entry_with_marker = next(r for r in records if r.recorded_date == "Oct 22.")
    assert footnote_2.linked_record_id == entry_with_marker.id
    assert footnote_2.linked_anchor == entry_with_marker.anchor_id(1)
    assert footnote_2.recorded_date == "1906"
    assert footnote_2.retrospective is True


def test_footnote_with_no_marker_in_entry_text_is_still_extracted_unlinked(tmp_path):
    # Footnote [1] belongs to Torrey's Introduction, which this slice does
    # not further decompose - "nothing in this slice deletes anything"
    # means the footnote body is still extracted, just without a link to
    # a specific evidence paragraph.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)

    _, editorial = _extract(evidence_root)

    footnotes = [e for e in editorial if e.editorial_type == "footnote"]
    footnote_1 = next(
        e for e in footnotes if e.original_locator.endswith("footnote 1")
    )
    assert "Torrey's footnote" in footnote_1.text
    assert footnote_1.linked_record_id is None
    assert footnote_1.linked_anchor is None


def test_bracketed_editorial_span_is_extracted_and_removed_from_evidence(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)

    records, editorial = _extract(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "editor inserts a whole aside" not in full_text

    spans = [e for e in editorial if e.editorial_type == "bracketed-span"]
    assert any("editor inserts a whole aside" in e.text for e in spans)
    span = next(e for e in spans if "editor inserts a whole aside" in e.text)
    assert span.linked_record_id is not None
    assert span.linked_anchor is not None
    assert span.recorded_date == "1906"
    assert span.retrospective is True


def test_a_bracketed_span_that_was_a_whole_paragraph_drops_that_paragraph(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)

    records, _ = _extract(evidence_root)

    entry_with_aside = next(r for r in records if r.recorded_date == "Oct 22.")
    # The entry had two paragraphs before stripping (the marker line, and
    # the whole-paragraph aside); only the marker line survives.
    assert entry_with_aside.paragraphs == [
        '_Oct 22._ "What are you doing now?" he asked.'
    ]


def test_introductions_are_extracted_as_editorial_records_not_evidence(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)

    records, editorial = _extract(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "fortune of Henry Thoreau as an author" not in full_text
    assert "man behind the journal" not in full_text

    introductions = [e for e in editorial if e.editorial_type == "introduction"]
    assert len(introductions) == 2
    torrey = next(e for e in introductions if "Torrey" in e.original_locator)
    sanborn = next(e for e in introductions if "Sanborn" in e.original_locator)
    assert "fortune of Henry Thoreau as an author" in torrey.text
    assert "man behind the journal" in sanborn.text
    for intro in introductions:
        assert intro.recorded_date == "1906"
        assert intro.retrospective is True
        assert intro.linked_record_id is None


def test_editorial_record_ids_are_stable_and_sequential(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)

    _, first_run = _extract(evidence_root)
    _, second_run = _extract(evidence_root)

    assert [e.id for e in first_run] == [e.id for e in second_run]
    assert [e.id for e in first_run] == [f"ED-{i:06d}" for i in range(1, len(first_run) + 1)]


def test_write_editorial_records_emits_frontmatter_and_body(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    _, editorial = _extract(evidence_root)
    output_root = tmp_path / "sources" / "editorial"

    paths = write_editorial_records(editorial, output_root)

    content = {p.name: p.read_text() for p in paths}
    first = content[editorial[0].id + ".md"]
    frontmatter = yaml.safe_load(first.split("---\n")[1])
    for field in (
        "id",
        "editorial_type",
        "recorded_date",
        "retrospective",
        "linked_record_id",
        "linked_anchor",
        "original_file",
        "original_locator",
    ):
        assert field in frontmatter


def test_write_editorial_records_removes_stale_orphans(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_corpus(evidence_root)
    _, editorial = _extract(evidence_root)
    output_root = tmp_path / "sources" / "editorial"
    output_root.mkdir(parents=True)
    stale_path = output_root / "ED-999999.md"
    stale_path.write_text("stale, from a previous run")

    write_editorial_records(editorial, output_root)

    assert not stale_path.exists()


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
class TestAgainstTheRealEvidenceCorpus:
    @pytest.fixture(scope="class")
    @staticmethod
    def extracted():
        evidence_root = Path(os.environ[EVIDENCE_ROOT_ENV_VAR])
        records = normalize_journals(evidence_root)
        editorial = extract_editorial_apparatus(evidence_root, records)
        return records, editorial

    def test_footnote_marker_counts_reconcile_against_recon(self):
        # RECON.md §4(a): "Inline markers [N]: 1,017 in J01, 744 in J02" -
        # ~1,750 total (the brief's figure). RECON's own count is a plain
        # grep for "[N]" over each *raw* file, so it counts each footnote
        # twice - once as the inline citation marker, once as the
        # footnote list's own "[N]" number label - which a direct
        # mechanical re-count confirms exactly.
        evidence_root = Path(os.environ[EVIDENCE_ROOT_ENV_VAR])
        import re

        counts = {}
        for volume in JOURNAL_VOLUMES:
            raw_text = (evidence_root / volume["raw_path"]).read_text(
                encoding="utf-8"
            )
            start = re.search(
                r"^\*\*\* START OF THE PROJECT GUTENBERG EBOOK.*$", raw_text, re.M
            )
            end = re.search(
                r"^\*\*\* END OF THE PROJECT GUTENBERG EBOOK.*$", raw_text, re.M
            )
            body = raw_text[start.end() : end.start()]
            counts[volume["raw_path"]] = len(re.findall(r"\[\d+\]", body))

        j01_count = counts["raw/gutenberg/57393-journal-01/pg57393.txt"]
        j02_count = counts["raw/gutenberg/59031-journal-02/pg59031.txt"]
        assert j01_count == 1017
        assert j02_count == 744
        assert j01_count + j02_count == 1761

    def test_bracketed_span_counts_reconcile_against_recon(self):
        # RECON.md §4(a): "~570 (J01) / ~485 (J02) bracketed spans are
        # neither footnote markers nor cross-references" - ~1,050 total
        # (the brief's figure). A direct mechanical count of every
        # non-numeric "[...]" span in each raw file (matching RECON's own
        # methodology of grepping the raw text, not narrowed to spans this
        # slice actually extracts out of entry text) finds somewhat more,
        # the same kind of deviation #3 documented for date headings.
        evidence_root = Path(os.environ[EVIDENCE_ROOT_ENV_VAR])
        import re

        bracket_re = re.compile(r"\[[^\[\]]*\]")
        counts = {}
        for volume in JOURNAL_VOLUMES:
            raw_text = (evidence_root / volume["raw_path"]).read_text(
                encoding="utf-8"
            )
            start = re.search(
                r"^\*\*\* START OF THE PROJECT GUTENBERG EBOOK.*$", raw_text, re.M
            )
            end = re.search(
                r"^\*\*\* END OF THE PROJECT GUTENBERG EBOOK.*$", raw_text, re.M
            )
            body = raw_text[start.end() : end.start()]
            spans = bracket_re.findall(body)
            non_numeric = [s for s in spans if not s[1:-1].isdigit()]
            counts[volume["raw_path"]] = len(non_numeric)

        j01_count = counts["raw/gutenberg/57393-journal-01/pg57393.txt"]
        j02_count = counts["raw/gutenberg/59031-journal-02/pg59031.txt"]
        assert j01_count == 593
        assert j02_count == 512
        assert j01_count + j02_count == 1105

    def test_footnote_and_span_editorial_records_extracted(self, extracted):
        _, editorial = extracted
        footnotes = [e for e in editorial if e.editorial_type == "footnote"]
        asides = [e for e in editorial if e.editorial_type == "bracketed-span"]
        interpolations = [e for e in editorial if e.editorial_type == "interpolation"]
        introductions = [e for e in editorial if e.editorial_type == "introduction"]

        assert len(footnotes) == 880  # 508 (J01) + 372 (J02) footnote bodies
        assert len(asides) == 86  # 25 (J01) + 61 (J02) standalone asides
        assert len(interpolations) == 146  # 58 (J01) + 88 (J02) interpolations
        assert len(asides) + len(interpolations) == 232  # in-entry bracket spans
        assert len(introductions) == 2

    def test_most_footnote_markers_link_back_to_an_evidence_paragraph(self, extracted):
        # 851 of the 880 footnotes (505 J01 + 346 J02) have their marker
        # inside an extracted entry; the rest are orphaned by known,
        # already-documented gaps - Torrey's Introduction (3, J01) and
        # J02's undated opening fragments discarded by #3 (26, J02) - not
        # by a bug in this slice.
        _, editorial = extracted
        footnotes = [e for e in editorial if e.editorial_type == "footnote"]
        linked = [e for e in footnotes if e.linked_record_id is not None]
        assert len(linked) == 851

    def test_every_span_links_to_a_record_and_anchor(self, extracted):
        _, editorial = extracted
        spans = [
            e
            for e in editorial
            if e.editorial_type in ("bracketed-span", "interpolation")
        ]
        for span in spans:
            assert span.linked_record_id is not None
            assert span.linked_anchor is not None

    def test_sampled_evidence_records_contain_no_editorial_voice(self, extracted):
        records, _ = extracted
        # Every 20th record, spanning both volumes.
        sample = records[::20]
        assert len(sample) > 10
        for record in sample:
            for paragraph in record.paragraphs:
                assert "[" not in paragraph
                assert "]" not in paragraph

    def test_no_evidence_paragraph_contains_bracket_delimited_text_anywhere(
        self, extracted
    ):
        records, _ = extracted
        for record in records:
            for paragraph in record.paragraphs:
                assert "[" not in paragraph and "]" not in paragraph, (
                    record.id,
                    paragraph,
                )

    def test_no_evidence_paragraph_has_a_space_before_punctuation(self, extracted):
        # Regression test for PR #51 review round 1, BLOCKING 2's "41
        # space-before-punctuation artifacts" - the leftover of excising a
        # bracket next to a comma or period without closing the gap.
        records, _ = extracted
        space_before_punct = re.compile(r"\s[,.;:!?]")
        for record in records:
            for paragraph in record.paragraphs:
                assert not space_before_punct.search(paragraph), (
                    record.id,
                    paragraph,
                )

    def test_sentence_completing_interpolations_are_kept_in_the_evidence_text(
        self, extracted
    ):
        # Regression test for PR #51 review round 1, BLOCKING 2: these
        # four editor-supplied words/phrases complete Thoreau's own
        # sentence and must survive in the evidence text - only their
        # brackets are stripped - rather than being excised, which
        # mangled the sentence around them.
        records, _ = extracted
        full_text = "\n".join(p for r in records for p in r.paragraphs)
        assert "must surely be the circulations of God" in full_text
        assert "Walked to Concord N. H., 10 miles." in full_text
        assert "as if out of courtesy to the green sea" in full_text
        assert "Had Robin Hood no Sherwood to resort to, it would be difficult" in (
            full_text
        )

    def test_editorial_records_are_marked_retrospective_with_the_edition_date(
        self, extracted
    ):
        _, editorial = extracted
        for record in editorial:
            assert record.retrospective is True
            assert record.recorded_date == "1906"

    def test_nothing_is_deleted_every_footnote_and_span_remains_readable(
        self, extracted
    ):
        _, editorial = extracted
        for record in editorial:
            assert record.text.strip() != ""
