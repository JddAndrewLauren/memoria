import os
import re
from pathlib import Path

import pytest
import yaml

from memoria.normalize import (
    LETTERS_VOLUME,
    normalize_letters,
    recipients_table,
    write_normalized_records,
    write_recipients_table,
)

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"

# A synthetic Gutenberg-shaped Familiar Letters volume, CRLF throughout,
# shaped like the real corpus (docs/normalized-record-schema.md, RECON.md
# §5): Sanborn's Introduction before the first letter, three letters (one
# with a footnote marker on the recipient), editorial narrative connecting
# two of them (left inline in the preceding letter's body for this slice -
# same scope decision issue #3 made for footnote markers and bracketed
# editorial spans), a trailing FOOTNOTES: block, and a GENERAL INDEX
# back-matter section - the latter two discarded by construction the same
# way journal front/back matter is.
_FAKE_LETTERS_TEXT = (
    "The Project Gutenberg eBook of Familiar Letters 99\r\n"
    "\r\n"
    "Credits: a transcriber\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK FAMILIAR LETTERS 99 ***\r\n"
    "\r\n"
    "Transcriber's Note:\r\n"
    "\r\n"
    "  Italic text is denoted by _underscores_.\r\n"
    "\r\n"
    "INTRODUCTION\r\n"
    "\r\n"
    "Sanborn wrote a long introduction about Thoreau that must never\r\n"
    "appear in any letter record.\r\n"
    "\r\n"
    "\r\n"
    "TO HELEN THOREAU (AT TAUNTON).\r\n"
    "\r\n"
    "     CONCORD, October 27, 1837.\r\n"
    "\r\n"
    'DEAR HELEN,--Please you, let the defendant say a few words in defense\r\n'
    "of his long silence.\r\n"
    "\r\n"
    "Further, letter-writing too often degenerates.\r\n"
    "\r\n"
    "     Your affectionate brother,\r\n"
    "     HENRY.\r\n"
    "\r\n"
    "This connective narrative by the editor must never appear in any\r\n"
    "letter record.\r\n"
    "\r\n"
    "\r\n"
    "TO JOHN THOREAU[7] (AT TAUNTON).\r\n"
    "\r\n"
    "     CONCORD, February 10, 1838.\r\n"
    "\r\n"
    "DEAR JOHN,--Dost expect to elicit a spark from so dull a steel.\r\n"
    "\r\n"
    "     Your affectionate brother,\r\n"
    "     HENRY D. THOREAU.\r\n"
    "\r\n"
    "\r\n"
    "TO R. W. EMERSON (AT CONCORD).\r\n"
    "\r\n"
    "     CONCORD, March 11, 1842.\r\n"
    "\r\n"
    "DEAR FRIEND,--I write to you now about the pond.\r\n"
    "\r\n"
    "     Yours,\r\n"
    "     HENRY.\r\n"
    "\r\n"
    "\r\n"
    "FOOTNOTES:\r\n"
    "\r\n"
    "[1] An editorial footnote that must never appear in any record.\r\n"
    "\r\n"
    "\r\n"
    "GENERAL INDEX\r\n"
    "\r\n"
    "The following are the titles of the volumes covered by this index.\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK FAMILIAR LETTERS 99 ***\r\n"
    "\r\n"
    "Updated editions will replace the previous one.\r\n"
)


def _write_fake_letters_volume(evidence_root, text=_FAKE_LETTERS_TEXT):
    path = evidence_root / LETTERS_VOLUME["raw_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def test_normalize_letters_splits_on_letter_headings(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    assert len(records) == 3
    assert [r.recipient for r in records] == [
        "HELEN THOREAU (AT TAUNTON).",
        "JOHN THOREAU[7] (AT TAUNTON).",
        "R. W. EMERSON (AT CONCORD).",
    ]


def test_normalize_letters_extracts_dateline_and_salutation(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    assert records[0].dateline == "CONCORD, October 27, 1837."
    assert records[0].salutation == "DEAR HELEN,--"
    assert records[0].recorded_date == "CONCORD, October 27, 1837."
    assert records[0].event_date == "CONCORD, October 27, 1837."


def test_normalize_letters_carries_the_verbatim_body(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    full_text = "\n".join(p for p in records[0].paragraphs)
    assert "Please you, let the defendant" in full_text
    assert "Your affectionate brother" in full_text


def test_normalize_letters_excludes_sanborns_introduction(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "Sanborn wrote a long introduction" not in full_text


def test_normalize_letters_excludes_trailing_footnotes_and_general_index(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    full_text = "\n".join(p for r in records for p in r.paragraphs)
    assert "editorial footnote" not in full_text
    assert "GENERAL INDEX" not in full_text
    assert "titles of the volumes" not in full_text


def test_normalize_letters_handles_crlf_line_endings(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    for record in records:
        for paragraph in record.paragraphs:
            assert "\r" not in paragraph


def test_normalize_letters_source_type_is_letter(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    assert all(r.source_type == "letter" for r in records)


def test_normalize_letters_date_confidence_is_unresolved(tmp_path):
    # Same scale as the journals (docs/normalized-record-schema.md):
    # unresolved for every record this slice produces.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    assert all(r.date_confidence == "unresolved" for r in records)


def test_normalize_letters_assigns_stable_src_ids_continuing_from_start_id(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root, start_id=559)

    assert [r.id for r in records] == ["SRC-000559", "SRC-000560", "SRC-000561"]


def test_normalize_letters_assigns_stable_src_ids_across_reruns(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    first_run = [r.id for r in normalize_letters(evidence_root)]
    second_run = [r.id for r in normalize_letters(evidence_root)]

    assert first_run == second_run


def test_recipients_table_groups_letters_by_verbatim_recipient_string(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)
    records = normalize_letters(evidence_root, start_id=1)

    table = recipients_table(records)

    assert table == {
        "HELEN THOREAU (AT TAUNTON).": ["SRC-000001"],
        "JOHN THOREAU[7] (AT TAUNTON).": ["SRC-000002"],
        "R. W. EMERSON (AT CONCORD).": ["SRC-000003"],
    }


def test_write_recipients_table_writes_yaml(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)
    records = normalize_letters(evidence_root, start_id=1)
    table = recipients_table(records)
    output_path = tmp_path / "sources" / "normalized" / "recipients.yaml"

    written_path = write_recipients_table(table, output_path)

    assert written_path == output_path
    loaded = yaml.safe_load(output_path.read_text())
    assert loaded == table


def test_write_normalized_records_carries_letter_specific_frontmatter_fields(
    tmp_path,
):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)
    records = normalize_letters(evidence_root, start_id=1)
    output_root = tmp_path / "sources" / "normalized"

    paths = write_normalized_records(records, output_root)

    content = {p.name: p.read_text() for p in paths}["SRC-000001.md"]
    frontmatter = yaml.safe_load(content.split("---\n")[1])
    assert frontmatter["recipient"] == "HELEN THOREAU (AT TAUNTON)."
    assert frontmatter["dateline"] == "CONCORD, October 27, 1837."
    assert frontmatter["salutation"] == "DEAR HELEN,--"


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
class TestAgainstTheRealEvidenceCorpus:
    @pytest.fixture(scope="class")
    @staticmethod
    def records():
        return normalize_letters(os.environ[EVIDENCE_ROOT_ENV_VAR])

    def test_letter_count_matches_recon(self, records):
        # RECON.md §5 / §7 and part 16's check-suite line item: 130 letters.
        assert len(records) == 130

    def test_recipient_count_matches_recon(self, records):
        # RECON.md §5 / §7: 43 distinct recipients.
        table = recipients_table(records)
        assert len(table) == 43

    def test_emersons_four_location_forms_are_distinct_recipients(self, records):
        # RECON.md §5/§6: R. W. Emerson appears under four location forms -
        # AT CONCORD, AT NEW YORK, IN ENGLAND, and one bare "TO R. W.
        # EMERSON." (no location). Verbatim preservation also keeps the two
        # footnote-marked variants of these headings as distinct strings
        # (issue #6: "Recipient strings are preserved verbatim"), so the
        # full R. W. Emerson group in the table is larger than 4; this
        # asserts the four location forms specifically are present and
        # distinct, not merged.
        table = recipients_table(records)
        location_forms = {
            "R. W. EMERSON (AT CONCORD).",
            "R. W. EMERSON (AT NEW YORK).",
            "R. W. EMERSON (IN ENGLAND).",
            "R. W. EMERSON.[41]",
        }
        assert location_forms <= table.keys()

    def test_every_letter_has_a_nonempty_dateline(self, records):
        for record in records:
            assert record.dateline, record.id

    def test_every_letter_has_a_nonempty_salutation(self, records):
        for record in records:
            assert record.salutation, record.id

    def test_no_letter_contains_sanborns_introduction(self, records):
        # Acceptance criterion: "Sanborn's introduction is not part of any
        # letter record."
        markers = (
            "The fortune of Henry Thoreau as an author of books has been",
            "Project Gutenberg",
            "Distributed Proofreading",
        )
        for record in records:
            for paragraph in record.paragraphs:
                for marker in markers:
                    assert marker not in paragraph, (record.id, marker)

    def test_no_letter_contains_general_index_back_matter(self, records):
        for record in records:
            for paragraph in record.paragraphs:
                assert "GENERAL INDEX" not in paragraph
                assert "Riverside Press" not in paragraph

    def test_no_letter_paragraph_is_empty(self, records):
        for record in records:
            for paragraph in record.paragraphs:
                assert paragraph.strip() != ""

    def test_letter_ids_do_not_collide_with_journal_ids(self, records):
        from memoria.normalize import normalize_journals

        journal_records = normalize_journals(os.environ[EVIDENCE_ROOT_ENV_VAR])
        journal_ids = {r.id for r in journal_records}
        letter_ids = {r.id for r in normalize_letters(
            os.environ[EVIDENCE_ROOT_ENV_VAR], start_id=len(journal_records) + 1
        )}
        assert journal_ids.isdisjoint(letter_ids)
