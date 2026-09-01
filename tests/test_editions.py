"""Placing a cited page of a reference edition in the held text (issue #9)."""

import os

import pytest

from memoria.editions import (
    REFERENCE_EDITIONS,
    WorkText,
    build_page_map,
    detect_printed_page_offset,
    read_reference_volume,
    tokenize,
)
from memoria.normalize import NormalizedRecord, normalize_targets

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


def _record(record_id, paragraphs):
    return NormalizedRecord(
        id=record_id,
        source_type="book",
        recorded_date="",
        event_date="1849",
        date_confidence="published",
        contemporaneous=False,
        original_file="raw/gutenberg/4232-a-week/pg4232.txt",
        original_locator="test",
        paragraphs=paragraphs,
        work="Week",
        chapter="TESTDAY",
    )


class TestTokenize:
    def test_rejoins_a_word_ocr_broke_across_a_line(self):
        # The searchtext keeps the printer's line-break hyphen, so "who had
        # not re- nounced our title" must tokenize the same as the held
        # text's "renounced" or the word cannot vote on an alignment.
        assert tokenize("had not re- nounced our title") == [
            "had",
            "not",
            "renounced",
            "our",
            "title",
        ]

    def test_discards_everything_the_two_printings_disagree_about(self):
        # A 1906 scan's OCR and a Distributed Proofreaders transcription
        # differ in case, punctuation and quote convention, and agree on
        # words. Only the words survive tokenization.
        assert tokenize('“What I see is mine.”') == tokenize("what i see is mine")


class TestWorkText:
    @pytest.fixture
    @staticmethod
    def work():
        return WorkText.from_records(
            [
                _record("SRC-000900", ["alpha beta gamma delta epsilon zeta"]),
                _record("SRC-000901", ["eta theta iota kappa lambda mu nu xi"]),
            ]
        )

    def test_paragraph_spans_are_contiguous_across_records(self, work):
        assert [(s.record_id, s.start, s.end) for s in work.spans] == [
            ("SRC-000900", 0, 6),
            ("SRC-000901", 6, 14),
        ]

    def test_anchors_a_passage_at_its_own_offset(self, work):
        offset, votes, length = work.anchor("theta iota kappa lambda mu nu")
        assert offset == 7
        assert votes > 0
        assert length == 6

    def test_reports_no_anchor_for_text_that_is_not_there(self, work):
        offset, votes, _ = work.anchor("nothing here matches the work at all")
        assert offset is None
        assert votes == 0

    def test_a_span_covers_every_paragraph_it_touches(self, work):
        # A cited page starts and ends mid-paragraph, so the paragraph the
        # page opens inside belongs to the span even though the page does
        # not contain its first word.
        touched = work.paragraphs_overlapping(4, 8)
        assert [s.record_id for s in touched] == ["SRC-000900", "SRC-000901"]


@pytest.mark.m0
@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
class TestAgainstTheRealReferenceEditions:
    @pytest.fixture(scope="class")
    @staticmethod
    def works():
        records = normalize_targets(os.environ[EVIDENCE_ROOT_ENV_VAR], start_id=718)
        return {
            work: WorkText.from_records([r for r in records if r.work == work])
            for work in ("Week", "Walden")
        }

    @pytest.fixture(scope="class")
    @staticmethod
    def maps(works):  # noqa: D401
        root = os.environ[EVIDENCE_ROOT_ENV_VAR]
        return {
            edition["identifier"]: build_page_map(
                root, edition, works[edition["work"]]
            )
            for edition in REFERENCE_EDITIONS
        }

    def test_each_volume_is_keyed_by_the_number_printed_on_the_page(self):
        # Found by reading one sampled row by eye, and the reason the spot
        # check exists: three of these four volumes number each leaf one
        # ahead of the number printed on it, and the fourth does not.
        # Nothing else catches it - a constant offset shifts every citation
        # of a volume equally, so the two-edition check absorbs it into its
        # drift fit and calls it agreement.
        root = os.environ[EVIDENCE_ROOT_ENV_VAR]
        offsets = {
            edition["identifier"]: read_reference_volume(
                root, edition["identifier"]
            ).offset
            for edition in REFERENCE_EDITIONS
        }
        assert offsets == {
            "writingsofhenryd01thor": -1,
            "writingsofhenryd01thor_1": -1,
            "writingsofhenryd02thoruoft": 0,
            "writingsofhenryd02thor_0": -1,
        }

    def test_the_running_heads_agree_all_but_unanimously(self):
        root = os.environ[EVIDENCE_ROOT_ENV_VAR]
        for edition in REFERENCE_EDITIONS:
            volume = read_reference_volume(root, edition["identifier"])
            assert volume.voting >= 20, edition["identifier"]
            assert volume.agreeing >= 0.9 * volume.voting, edition["identifier"]

    def test_the_cited_page_holds_what_its_running_head_says_it_does(self):
        # Manuscript vol. 1 page 375 is the page whose own running head
        # reads "FRIDAY 375" - not the leaf the scanner labelled 375, whose
        # head reads 374.
        volume = read_reference_volume(
            os.environ[EVIDENCE_ROOT_ENV_VAR], "writingsofhenryd01thor"
        )
        assert "FRIDAY 375" in " ".join(volume.pages[375].split())
        assert "Merrimack intervals" in " ".join(volume.pages[374].split())

    def test_every_volume_places_the_bulk_of_its_pages(self, maps):
        # Pages that fail are plates, blank leaves and front matter, which
        # have no counterpart in the held text.
        for identifier, page_map in maps.items():
            assert len(page_map.offsets) >= 350, identifier

    def test_page_numbers_and_text_positions_ascend_together(self, maps):
        # The correctness check the whole page map exists to make possible:
        # page numbers ascend, so the offsets they map to must ascend too.
        # A volume that breaks this was mis-anchored somewhere.
        for identifier, page_map in maps.items():
            offsets = [page_map.offsets[p] for p in page_map.pages]
            assert offsets == sorted(offsets), identifier
        # Neither Manuscript volume needs a single page dropped to get
        # there; the Riverside scans are noisier.
        assert maps["writingsofhenryd01thor"].non_monotonic == []
        assert maps["writingsofhenryd02thoruoft"].non_monotonic == []

    def test_a_page_span_runs_to_the_next_page(self, maps):
        page_map = maps["writingsofhenryd01thor"]
        start, end = page_map.span(375)
        assert start == page_map.offsets[375]
        assert end == page_map.offsets[376]
        assert page_map.page_containing(start) == 375


class TestPrintedPageOffset:
    def test_reads_the_offset_out_of_the_running_heads(self):
        # Leaf 54 carries "SUNDAY 53", so the leaf numbering runs one ahead
        # of the print.
        pages = {53: "text SATURDAY 52 more", 54: "text SUNDAY 53 more"}
        assert detect_printed_page_offset(pages) == (-1, 2, 2)

    def test_reports_alignment_when_the_heads_agree_with_the_leaves(self):
        pages = {45: "text ECONOMY 45 more", 46: "text 46 WALDEN more"}
        assert detect_printed_page_offset(pages) == (0, 2, 2)

    def test_ignores_a_number_that_is_not_a_page_number(self):
        # A year or a quantity next to a chapter word is not a running
        # head; only a number within one of the leaf's own is considered.
        pages = {45: "in 1849 WALDEN was not yet written"}
        assert detect_printed_page_offset(pages) == (0, 0, 0)

    def test_refuses_a_volume_whose_pages_never_say_what_they_are(self, tmp_path):
        # Better to stop than to serve pages nobody can check: every
        # citation into such a volume would be unverifiable.
        import json, gzip
        root = tmp_path / "raw" / "archive-org"
        root.mkdir(parents=True)
        (root / "vol_page_numbers.json").write_text(
            json.dumps({"pages": [{"leafNum": 1, "pageNumber": "1"}]})
        )
        with gzip.open(root / "vol_hocr_pageindex.json.gz", "wt") as handle:
            json.dump([[0, 11, 0, 0]], handle)
        with gzip.open(root / "vol_hocr_searchtext.txt.gz", "wb") as handle:
            handle.write(b"plain words")

        with pytest.raises(ValueError, match="printed-page offset"):
            read_reference_volume(tmp_path, "vol")
