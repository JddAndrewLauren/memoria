import os

import pytest
import yaml

from memoria.normalize import (
    JOURNAL_VOLUMES,
    normalize_journals,
    normalize_quotes,
    write_normalized_records,
)

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"

# A synthetic Gutenberg-shaped journal, CRLF throughout, with front matter
# and a trailing license both outside the START/END markers, and three
# entries spanning a blank-line-separated paragraph and a chapter title
# landing between two entries (as the real corpus does - RECON.md §3).
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
    "_Nov. 3._ If one would reflect, let him embark.\r\n"
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

    assert len(records) == 6
    assert [r.recorded_date for r in records[:3]] == ["Oct 22.", "Oct. 24.", "Nov. 3."]


def test_normalize_journals_excludes_gutenberg_boilerplate_and_front_matter(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    records = normalize_journals(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "Project Gutenberg" not in full_text
    assert "Credits:" not in full_text
    assert "Updated editions" not in full_text
    assert "1899" not in full_text


def test_normalize_journals_assigns_stable_src_ids_across_reruns(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_FAKE_VOLUME_TEXT, _FAKE_VOLUME_TEXT])

    first_run = [r.id for r in normalize_journals(evidence_root)]
    second_run = [r.id for r in normalize_journals(evidence_root)]

    assert first_run == second_run
    assert first_run == [f"SRC-{i:06d}" for i in range(1, 7)]


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

    def test_date_headings_found_are_reconciled_against_recon(self, records):
        # RECON.md section 3 states 299 (J01) and 149 (J02) date headings,
        # 448 total. Mechanically re-counting every line-initial italic
        # date heading in the raw text against the closed set of forms
        # RECON.md documents finds more: 399 (J01) and 155 (J02), 554
        # total. Spot checks (chapter-by-chapter line ranges, and J02's
        # "Chapter I has no date headings" claim, contradicted by 22
        # headings within RECON's own line range for that chapter) turned
        # up no false positives among the extra headings - see the finding
        # posted on issue #3. This test asserts the actual, mechanically
        # verified count rather than RECON's summary figure.
        j01_count = sum(1 for r in records if "57393" in r.original_file)
        j02_count = sum(1 for r in records if "59031" in r.original_file)

        assert j01_count == 399
        assert j02_count == 155
        assert j01_count + j02_count == 554
