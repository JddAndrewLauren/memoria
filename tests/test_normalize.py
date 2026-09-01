import os
import re
from pathlib import Path

import pytest
import yaml

from memoria.normalize import (
    DATE_HEADING_RE,
    JOURNAL_VOLUMES,
    _extract_body_lines,
    normalize_journals,
    normalize_quotes,
    write_normalized_records,
)

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"

# A synthetic Gutenberg-shaped journal, CRLF throughout, with front matter
# and a trailing license both outside the START/END markers, four entries
# (one using the "to"-range form), a chapter-marker paragraph ("II") landing
# between two entries, and a back-matter block (colophon + a footnote) after
# the last entry - all as the real corpus does (RECON.md §3, §4).
_FAKE_VOLUME_TEXT = (
    "The Project Gutenberg eBook of Journal 99\r\n"
    "\r\n"
    "Credits: a transcriber\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
    "\r\n"
    "I\r\n"
    "\r\n"
    "1899\r\n"
    "\r\n"
    '_Oct 22._ "What are you doing now?" he asked.\r\n'
    "So I make my first entry to-day.\r\n"
    "\r\n"
    "SOLITUDE\r\n"
    "\r\n"
    "_Oct. 24._ Every part of nature teaches something.\r\n"
    "\r\n"
    "II\r\n"
    "\r\n"
    "_Nov. 3._ If one would reflect, let him embark.\r\n"
    "\r\n"
    "_July 10 to 12._ This town, too, lies out under the sky.\r\n"
    "\r\n"
    "END OF VOLUME 99\r\n"
    "\r\n"
    "The Fake Press\r\n"
    "\r\n"
    "FOOTNOTES\r\n"
    "\r\n"
    "[1] An editorial footnote that must never appear in any record.\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
    "\r\n"
    "Updated editions will replace the previous one.\r\n"
)


def _write_fake_volumes(evidence_root, volume_texts):
    """Write fake volume text at each configured JOURNAL_VOLUMES raw_path."""
    for volume, text in zip(JOURNAL_VOLUMES, volume_texts):
        path = evidence_root / volume["raw_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def test_normalize_quotes_collapses_curly_quotes_to_straight_ascii():
    curly = "“Do you keep a journal?” he asked."

    result = normalize_quotes(curly)

    assert result == '"Do you keep a journal?" he asked.'


def test_normalize_quotes_collapses_curly_apostrophes_to_straight_ascii():
    curly = "‘tis the season’s end"

    result = normalize_quotes(curly)

    assert result == "'tis the season's end"


def test_normalize_quotes_leaves_already_straight_quotes_unchanged():
    straight = '"Do you keep a journal?" he asked.'

    result = normalize_quotes(straight)

    assert result == straight


def test_normalize_journals_splits_on_line_initial_date_headings(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    records = normalize_journals(evidence_root)

    assert len(records) == 8
    assert [r.recorded_date for r in records[:4]] == [
        "Oct 22.",
        "Oct. 24.",
        "Nov. 3.",
        "July 10 to 12.",
    ]


def test_normalize_journals_excludes_gutenberg_boilerplate_and_front_matter(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    records = normalize_journals(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "Project Gutenberg" not in full_text
    assert "Credits:" not in full_text
    assert "Updated editions" not in full_text
    assert "1899" not in full_text


def test_normalize_journals_excludes_back_matter_after_the_last_entry(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    records = normalize_journals(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "END OF VOLUME" not in full_text
    assert "The Fake Press" not in full_text
    assert "FOOTNOTES" not in full_text
    assert "editorial footnote" not in full_text
    # The colophon and footnote must not have been swallowed into the
    # volume's last entry (the bug: the last entry used to run to end of
    # file).
    last_entry_of_first_volume = records[3]
    assert last_entry_of_first_volume.recorded_date == "July 10 to 12."
    assert len(last_entry_of_first_volume.paragraphs) == 1


def test_normalize_journals_strips_chapter_marker_paragraphs(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    records = normalize_journals(evidence_root)

    for record in records:
        assert "II" not in record.paragraphs


def test_normalize_journals_assigns_stable_src_ids_across_reruns(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    first_run = [r.id for r in normalize_journals(evidence_root)]
    second_run = [r.id for r in normalize_journals(evidence_root)]

    assert first_run == second_run
    assert first_run == [f"SRC-{i:06d}" for i in range(1, 9)]


def test_normalize_journals_handles_crlf_line_endings(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    records = normalize_journals(evidence_root)

    for record in records:
        for paragraph in record.paragraphs:
            assert "\r" not in paragraph


def test_write_normalized_records_emits_stable_paragraph_anchors(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])
    records = normalize_journals(evidence_root)
    output_root = tmp_path / "sources" / "normalized"

    first_run_paths = write_normalized_records(records, output_root)
    first_run_content = {p.name: p.read_text() for p in first_run_paths}

    second_run_paths = write_normalized_records(records, output_root)
    second_run_content = {p.name: p.read_text() for p in second_run_paths}

    assert first_run_content == second_run_content
    first_record_text = first_run_content["SRC-000001.md"]
    assert '<a id="src-000001-p1"></a>' in first_record_text
    assert '<a id="src-000001-p2"></a>' in first_record_text


def test_write_normalized_records_carries_the_required_frontmatter_fields(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])
    records = normalize_journals(evidence_root)
    output_root = tmp_path / "sources" / "normalized"

    paths = write_normalized_records(records, output_root)

    content = paths[0].read_text()
    frontmatter_text = content.split("---\n")[1]
    frontmatter = yaml.safe_load(frontmatter_text)
    for field in (
        "id",
        "source_type",
        "recorded_date",
        "event_date",
        "date_confidence",
        "contemporaneous",
        "original_file",
        "original_locator",
    ):
        assert field in frontmatter


@pytest.mark.parametrize(
    "heading_line",
    [
        "_July 10 to 12._ This town, too, lies out under the sky, a port of entry",
        "_Nov. 29. Cambridge._\u2014One must fight his way, after a fashion, even in",
        "_July 20. Sunday morning._ A thunder-shower in the night. Thunder near",
        "_July 28. Monday morning._ Sailed [to] the Gurnet, which runs down",
    ],
)
def test_date_heading_re_matches_previously_missed_forms(heading_line):
    # Regression test for defect 2 (review round 1 on PR #48): these four
    # genuine line-initial date headings were silently merged into their
    # predecessor entries by an earlier version of DATE_HEADING_RE.
    assert DATE_HEADING_RE.match(heading_line)


def test_normalized_record_anchor_id_matches_the_written_markdown_anchor(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])
    records = normalize_journals(evidence_root)
    output_root = tmp_path / "sources" / "normalized"

    paths = write_normalized_records(records, output_root)

    first_record = records[0]
    written_text = {p.name: p.read_text() for p in paths}["SRC-000001.md"]
    assert first_record.anchor_id(1) == "src-000001-p1"
    assert f'<a id="{first_record.anchor_id(1)}"></a>' in written_text


def test_write_normalized_records_removes_stale_orphans(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])
    records = normalize_journals(evidence_root)
    output_root = tmp_path / "sources" / "normalized"
    output_root.mkdir(parents=True)
    stale_path = output_root / "SRC-999999.md"
    stale_path.write_text("stale, from a previous run over a larger corpus")

    write_normalized_records(records, output_root)

    assert not stale_path.exists()


def test_quote_normalization_finds_the_same_phrase_regardless_of_source_convention():
    search_phrase = '"Do you keep a journal?"'
    straight_quote_source = normalize_quotes(
        '_Oct 22._ "What are you doing now?" he asked. "Do you keep a journal?"'
    )
    curly_quote_source = normalize_quotes(
        "_Oct 22._ “What are you doing now?” he asked. “Do you keep a journal?”"
    )

    assert search_phrase in straight_quote_source
    assert search_phrase in curly_quote_source


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
class TestAgainstTheRealEvidenceCorpus:
    @pytest.fixture(scope="class")
    @staticmethod
    def records():
        return normalize_journals(os.environ[EVIDENCE_ROOT_ENV_VAR])

    def test_finds_a_phrase_in_both_j01_and_j02_quote_conventions(self, records):
        # J01/Familiar Letters use straight ASCII quotes; J02 uses curly
        # Unicode quotes (RECON.md section 6.1). A single normalized search
        # must find quoted material in records from both volumes.
        j01_records = [r for r in records if "57393" in r.original_file]
        j02_records = [r for r in records if "59031" in r.original_file]

        assert any(
            '"Do you keep a journal?"' in p for r in j01_records for p in r.paragraphs
        )
        assert any(
            '"' in p and "“" not in p and "”" not in p
            for r in j02_records
            for p in r.paragraphs
        )

    def test_no_normalized_record_contains_gutenberg_boilerplate(self, records):
        boilerplate_markers = (
            "Project Gutenberg",
            "PROJECT GUTENBERG",
            "Distributed Proofreading",
        )
        for record in records:
            for paragraph in record.paragraphs:
                for marker in boilerplate_markers:
                    assert marker not in paragraph

    def test_no_normalized_record_contains_the_trailing_back_matter(self, records):
        # Regression test for defect 1 (review round 1 on PR #48): each
        # volume's back matter - the printer's colophon and Torrey's
        # editorial endnote apparatus, between the last date heading and
        # the Gutenberg END marker - used to be swallowed whole into that
        # volume's last entry.
        back_matter_markers = (
            "END OF VOLUME",
            "The Riverside Press",
            "H. O. HOUGHTON",
            "FOOTNOTES",
        )
        for record in records:
            for paragraph in record.paragraphs:
                for marker in back_matter_markers:
                    assert marker not in paragraph, (record.id, marker, paragraph[:80])

    def test_no_entry_paragraph_count_is_an_order_of_magnitude_above_the_median(
        self, records
    ):
        # A generous bound: the corpus's one legitimately huge entry (J01's
        # "selections" chapter groups many undated fragments under a single
        # heading, ~230 paragraphs) must still pass, but the back-matter
        # regression this guards against previously produced 525- and
        # 379-paragraph entries by swallowing 500+ footnotes whole.
        counts = sorted(len(r.paragraphs) for r in records)
        median = counts[len(counts) // 2]
        cap = median * 100
        for record in records:
            assert len(record.paragraphs) <= cap, (
                record.id,
                len(record.paragraphs),
                cap,
            )

    def test_no_paragraph_is_a_bare_chapter_marker(self, records):
        chapter_marker = re.compile(
            r"^(?:[IVXLCM]+|\d{4}(?:-\d{2,4})?|\(?\u00c6T\.\s*\d+(?:-\d+)?\)?)$"
        )
        for record in records:
            for paragraph in record.paragraphs:
                assert not chapter_marker.match(paragraph), (record.id, paragraph)

    def test_every_entry_starts_at_a_line_matched_by_the_heading_regex(self, records):
        # Every record's recorded_date was extracted verbatim from a raw
        # line DATE_HEADING_RE matched (normalize.py's _split_entries); a
        # record whose recorded_date does not itself re-match the heading
        # form would mean an entry started somewhere other than a matched
        # heading.
        for record in records:
            assert DATE_HEADING_RE.match(f"_{record.recorded_date}_")

    def test_every_matched_heading_is_preceded_by_a_blank_line_in_the_raw_text(self):
        # RECON.md section 3: "All ... date headings are line-initial" -
        # verified directly against the raw text rather than trusted.
        evidence_root = Path(os.environ[EVIDENCE_ROOT_ENV_VAR])
        for volume in JOURNAL_VOLUMES:
            raw_text = (evidence_root / volume["raw_path"]).read_text(
                encoding="utf-8"
            )
            body_lines = _extract_body_lines(raw_text)
            for i, line in enumerate(body_lines):
                if DATE_HEADING_RE.match(line):
                    assert i == 0 or body_lines[i - 1].strip() == "", (
                        volume["raw_path"],
                        i,
                        line,
                    )

    def test_no_line_initial_month_prefixed_line_is_left_unmatched(self):
        # Recall check for defect 2 (review round 1 on PR #48): any raw
        # body line that opens with an italicized month name must also be
        # matched by DATE_HEADING_RE, or it silently merges into its
        # predecessor entry instead of starting its own.
        month_prefix = re.compile(
            r"^_(?:Jan|Feb|March|April|May|June|July|Aug|Sept|Oct|Nov|Dec)\b"
        )
        evidence_root = Path(os.environ[EVIDENCE_ROOT_ENV_VAR])
        for volume in JOURNAL_VOLUMES:
            raw_text = (evidence_root / volume["raw_path"]).read_text(
                encoding="utf-8"
            )
            body_lines = _extract_body_lines(raw_text)
            unmatched = [
                line
                for line in body_lines
                if month_prefix.match(line) and not DATE_HEADING_RE.match(line)
            ]
            assert unmatched == [], (volume["raw_path"], unmatched)

    def test_date_headings_found_are_reconciled_against_recon(self, records):
        # RECON.md section 3 states 299 (J01) and 149 (J02) date headings,
        # 448 total. Mechanically re-implementing RECON's own stated
        # detection rule (line-initial italic date, closed set of forms)
        # against the raw text finds more: 401 (J01) and 157 (J02), 558
        # total. An independent review of PR #48 confirmed this
        # mechanically: every one of these matches is preceded by a blank
        # line (see test_every_matched_heading_is_preceded_by_a_blank_line_
        # in_the_raw_text above), RECON's own J02 "_Mon. N._" count matches
        # exactly, and the gap traces to RECON's counter requiring an
        # abbreviating period and so missing unabbreviated months (May,
        # June, July, March, April). The review also independently
        # reproduced the falsification of RECON's "J02 Chapter I has no
        # date headings" claim (22 headings within RECON's own stated line
        # range for that chapter). This test asserts the mechanically
        # verified count rather than RECON's summary figure - see the
        # finding posted on issue #3.
        j01_count = sum(1 for r in records if "57393" in r.original_file)
        j02_count = sum(1 for r in records if "59031" in r.original_file)

        assert j01_count == 401
        assert j02_count == 157
        assert j01_count + j02_count == 558
