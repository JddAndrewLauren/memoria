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
        "JOHN THOREAU (AT TAUNTON).",
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


def test_normalize_letters_with_no_dateline_gets_an_empty_dateline_not_a_signature(
    tmp_path,
):
    # Regression test for review round 1 on PR #52's blocking defect 1:
    # a letter with no dateline at all must not have its closing
    # signature block ("Yours truly, HENRY.") picked up as `dateline`.
    evidence_root = tmp_path / "thoreau-evidence"
    text = _FAKE_LETTERS_TEXT.replace(
        "     CONCORD, March 11, 1842.\r\n"
        "\r\n"
        "DEAR FRIEND,--I write to you now about the pond.\r\n",
        "DEAR FRIEND,--I write to you now about the pond, with no dateline\r\n"
        "at all this time.\r\n",
    )
    _write_fake_letters_volume(evidence_root, text)

    records = normalize_letters(evidence_root)

    assert records[2].dateline == ""
    assert records[2].recorded_date == ""


def test_normalize_letters_with_no_salutation_gets_an_empty_salutation_not_prose(
    tmp_path,
):
    # A letter that continues without a fresh greeting (SRC-000045,
    # SRC-000049, SRC-000050, SRC-000129 in the real corpus) must not have
    # its opening body prose picked up as `salutation` - an empty
    # salutation is correct when a letter has none, per the issue #58
    # brief.
    evidence_root = tmp_path / "thoreau-evidence"
    text = _FAKE_LETTERS_TEXT.replace(
        "DEAR FRIEND,--I write to you now about the pond.\r\n",
        "I write to you now about the pond, with no salutation at all.\r\n",
    )
    _write_fake_letters_volume(evidence_root, text)

    records = normalize_letters(evidence_root)

    assert records[2].salutation == ""
    assert "pond" in "\n".join(records[2].paragraphs)


def test_normalize_letters_recognises_a_salutation_with_a_footnote_marker(
    tmp_path,
):
    # SRC-000092 in the real corpus: "MR. WILEY,[75]--" carries a footnote
    # marker between the comma and the dashes, so the plain ",--" pattern
    # missed it and fell through to the (now-removed) prose fallback.
    evidence_root = tmp_path / "thoreau-evidence"
    text = _FAKE_LETTERS_TEXT.replace(
        "DEAR FRIEND,--I write to you now about the pond.\r\n",
        "MR. WILEY,[75]--I write to you now about the pond.\r\n",
    )
    _write_fake_letters_volume(evidence_root, text)

    records = normalize_letters(evidence_root)

    assert records[2].salutation == "MR. WILEY,[75]--"


def test_normalize_letters_skips_a_leading_editorial_annotation_for_dateline(
    tmp_path,
):
    # SRC-000049 in the real corpus: "[The first of many letters.]" (an
    # editorial aside) precedes the real indented dateline. Neither
    # dateline nor salutation extraction may treat the annotation itself
    # as the letter's own content.
    evidence_root = tmp_path / "thoreau-evidence"
    text = _FAKE_LETTERS_TEXT.replace(
        "TO R. W. EMERSON (AT CONCORD).\r\n"
        "\r\n"
        "     CONCORD, March 11, 1842.\r\n",
        "TO R. W. EMERSON (AT CONCORD).\r\n"
        "\r\n"
        "[The first of many letters.]\r\n"
        "\r\n"
        "     CONCORD, March 11, 1842.\r\n",
    )
    _write_fake_letters_volume(evidence_root, text)

    records = normalize_letters(evidence_root)

    assert records[2].dateline == "CONCORD, March 11, 1842."
    assert records[2].salutation == "DEAR FRIEND,--"
    assert not records[2].salutation.startswith("[")


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


def test_normalize_letters_keeps_the_text_after_a_midvolume_footnote_block(
    tmp_path,
):
    # The FOOTNOTES: blocks scattered through this volume are followed by
    # ordinary body text - a chapter heading, connective narrative, a
    # letter written *to* Thoreau. Cutting a letter's lines at the marker
    # dropped all of it, so text that exists in the source reached no
    # record at all; only the block itself may be excised.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(
        evidence_root,
        _FAKE_LETTERS_TEXT.replace(
            "TO R. W. EMERSON (AT CONCORD).\r\n",
            "FOOTNOTES:\r\n"
            "\r\n"
            "[6] A mid-volume footnote that must never appear in any record.\r\n"
            "\r\n"
            "\r\n"
            "II\r\n"
            "\r\n"
            "GOLDEN AGE OF ACHIEVEMENT\r\n"
            "\r\n"
            "This chapter narrative follows a footnote block and must survive.\r\n"
            "\r\n"
            "\r\n"
            "ELLERY CHANNING TO THOREAU (AT CONCORD).\r\n"
            "\r\n"
            "     March 5, 1845.\r\n"
            "\r\n"
            "MY DEAR THOREAU,--you are the same old sixpence.\r\n"
            "\r\n"
            "\r\n"
            "TO R. W. EMERSON (AT CONCORD).\r\n",
        ),
    )

    records = normalize_letters(evidence_root)

    john = next(r for r in records if r.recipient.startswith("JOHN THOREAU"))
    body = "\n".join(john.paragraphs)
    assert "must never appear in any record" not in body
    assert "This chapter narrative follows a footnote block" in body
    assert "ELLERY CHANNING TO THOREAU (AT CONCORD)." in body
    assert "same old sixpence" in body


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


def test_normalize_letters_date_confidence_is_inferred_for_an_explicit_year(
    tmp_path,
):
    # Issue #57: a dateline's year is stated in plain text, no chapter
    # inference or weekday checksum needed or possible - same value the
    # journals give a heading that already states its own year
    # (docs/normalized-record-schema.md's `date_confidence` row), since
    # there is nothing here to independently confirm it against either.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_letters_volume(evidence_root)

    records = normalize_letters(evidence_root)

    assert all(r.date_confidence == "inferred" for r in records)
    assert all(r.event_date == r.dateline for r in records)


def test_normalize_letters_with_no_dateline_is_unresolved(tmp_path):
    # A letter with no dateline at all (SRC-000002/SRC-000129 in the real
    # corpus) has no year to parse - `date_confidence` stays `unresolved`,
    # never invented.
    evidence_root = tmp_path / "thoreau-evidence"
    text = _FAKE_LETTERS_TEXT.replace(
        "     CONCORD, March 11, 1842.\r\n"
        "\r\n"
        "DEAR FRIEND,--I write to you now about the pond.\r\n",
        "DEAR FRIEND,--I write to you now about the pond, with no dateline\r\n"
        "at all this time.\r\n",
    )
    _write_fake_letters_volume(evidence_root, text)

    records = normalize_letters(evidence_root)

    assert records[2].dateline == ""
    assert records[2].date_confidence == "unresolved"
    assert records[2].event_date == ""


def test_normalize_letters_with_no_year_in_dateline_is_unresolved(tmp_path):
    # A dateline can be present but carry no year at all (SRC-000024 in the
    # real corpus, "CASTLETON, STATEN ISLAND, May 23.") or spell it in
    # Roman numerals rather than digits (SRC-000007, "A. D. MDCCCXL.") -
    # both unparseable by a plain year scan, so both stay `unresolved`
    # rather than guessing.
    evidence_root = tmp_path / "thoreau-evidence"
    text = _FAKE_LETTERS_TEXT.replace(
        "     CONCORD, March 11, 1842.\r\n",
        "     CONCORD, March 11.\r\n",
    )
    _write_fake_letters_volume(evidence_root, text)

    records = normalize_letters(evidence_root)

    assert records[2].dateline == "CONCORD, March 11."
    assert records[2].date_confidence == "unresolved"
    assert records[2].event_date == "CONCORD, March 11."


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
        "JOHN THOREAU (AT TAUNTON).": ["SRC-000002"],
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


@pytest.mark.m0
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
        # RECON.md §5 / §7 counts 43 distinct recipients - 43 distinct
        # *heading strings*, three of which carry a footnote marker. The
        # marker is apparatus, not part of the recipient, so it is
        # stripped: two of the three then collapse onto a heading already
        # in the table ("MRS. LUCY BROWN[15] (AT PLYMOUTH)." and "R. W.
        # EMERSON[42] (AT CONCORD)."), leaving 41.
        table = recipients_table(records)
        assert len(table) == 41
        assert not [k for k in table if "[" in k], sorted(table)

    def test_emersons_four_location_forms_are_distinct_recipients(self, records):
        # RECON.md §5/§6: R. W. Emerson appears under four location forms -
        # AT CONCORD, AT NEW YORK, IN ENGLAND, and one bare "TO R. W.
        # EMERSON." (no location). Location forms are never merged (issue
        # #6's alias-resolution hazard material); only the apparatus
        # footnote marker is stripped, which is what makes the bare form
        # read "R. W. EMERSON." rather than "R. W. EMERSON.[41]".
        table = recipients_table(records)
        location_forms = {
            "R. W. EMERSON (AT CONCORD).",
            "R. W. EMERSON (AT NEW YORK).",
            "R. W. EMERSON (IN ENGLAND).",
            "R. W. EMERSON.",
        }
        assert location_forms <= table.keys()

    def test_a_heading_footnote_marker_is_not_part_of_the_recipient(self, records):
        # Three headings carry an inline footnote marker (footnotes 15,
        # 41, 42 - "TO MRS. LUCY BROWN[15] (AT PLYMOUTH)."). The marker is
        # Sanborn's apparatus, not the recipient, and used to be carried
        # verbatim into `recipient`, splitting two correspondents into
        # spurious extra rows of the recipients table. Pinned per source
        # id so a regression cannot hide behind the count alone.
        by_id = {r.id: r for r in records}
        assert by_id["SRC-000009"].recipient == "MRS. LUCY BROWN (AT PLYMOUTH)."
        assert by_id["SRC-000048"].recipient == "R. W. EMERSON."
        assert by_id["SRC-000056"].recipient == "R. W. EMERSON (AT CONCORD)."
        # The stripped marker is not left behind in the locator either.
        assert by_id["SRC-000009"].original_locator == (
            "Familiar Letters, letter to MRS. LUCY BROWN (AT PLYMOUTH)."
        )
        # No letter's recipient carries a bracket anywhere.
        for record in records:
            assert "[" not in record.recipient, (record.id, record.recipient)

    def test_every_letters_dateline_is_plausibly_shaped_or_empty(self, records):
        # Recall/shape check (review round 1 on PR #52's blocking defect
        # 2): a presence check cannot fail on the defect where
        # `_extract_dateline` picked up a closing signature block instead
        # of a real dateline - `dateline` was never empty, just wrong
        # ("TAHATAWAN." for SRC-000002, "Yrs. in great haste, HENRY D.
        # THOREAU." for SRC-000129). This checks the shape of what was
        # extracted (short, does not open with signature-closing
        # vocabulary) and, independently, exactly which letters have no
        # dateline in the raw text at all - a regression that made
        # `_extract_dateline` timid (returning "" for a letter that does
        # have one) would silently grow that set without this failing.
        signature_openers = (
            "yours",
            "yrs",
            "your affectionate",
            "your friend",
            "believe me",
            "truly",
            "affectionately",
            "ever yours",
            "from your",
        )
        for record in records:
            if not record.dateline:
                continue
            assert len(record.dateline) <= 100, (record.id, record.dateline)
            lowered = record.dateline.lower()
            assert not lowered.startswith(signature_openers), (
                record.id,
                record.dateline,
            )
        empty_ids = {r.id for r in records if not r.dateline}
        assert empty_ids == {"SRC-000002", "SRC-000129"}, empty_ids

    def test_every_letters_salutation_is_plausibly_shaped_or_empty(self, records):
        # Recall/shape check (issue #58): a presence-only check cannot
        # fail on the defect where `_extract_salutation` fell back to the
        # body's opening prose - `salutation` was never empty, just wrong
        # (SRC-000045, SRC-000049, SRC-000050, SRC-000129 each got a
        # sentence of body text). This checks the shape of what was
        # extracted (short, ends in the address's trailing "--") and,
        # independently, exactly which letters have no salutation in the
        # raw text at all - a regression that made `_extract_salutation`
        # timid (returning "" for a letter that does have one) would
        # silently grow that set without this failing. Restoring the old
        # prose fallback fails this test: the fallback text does not end
        # in "--".
        for record in records:
            if not record.salutation:
                continue
            assert record.salutation.endswith("--"), (record.id, record.salutation)
            assert len(record.salutation) <= 60, (record.id, record.salutation)
        empty_ids = {r.id for r in records if not r.salutation}
        assert empty_ids == {
            "SRC-000002",
            "SRC-000045",
            "SRC-000049",
            "SRC-000050",
            "SRC-000129",
        }, empty_ids

    def test_no_salutation_is_an_editorial_annotation(self, records):
        # Non-blocking finding, review round 1 on PR #52: SRC-000049 fell
        # back to "[The first of many letters.]" (Sanborn's bracketed
        # aside, not Thoreau's greeting) because the dateline/salutation
        # scan did not skip editorial annotations. Fixed alongside the
        # dateline defect since both walk the same leading paragraphs.
        for record in records:
            assert not record.salutation.startswith(("[", "(")), (
                record.id,
                record.salutation,
            )

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

    def test_date_confidence_split_across_all_130_letters(self, records):
        # Acceptance criterion (issue #57): a real split, not a bare count -
        # this would fail if a dateline's year were silently dropped
        # (every `inferred` record would slide to `unresolved`) or if a
        # record without a parseable year were wrongly promoted. The four
        # `unresolved` records are the two known empty datelines
        # (SRC-000002, SRC-000129) plus two with a dateline but no
        # parseable year: SRC-000007 ("A. D. MDCCCXL.", a Roman-numeral
        # year) and SRC-000024 ("CASTLETON, STATEN ISLAND, May 23.", no
        # year at all).
        unresolved_ids = {
            r.id for r in records if r.date_confidence == "unresolved"
        }
        assert unresolved_ids == {
            "SRC-000002",
            "SRC-000007",
            "SRC-000024",
            "SRC-000129",
        }
        inferred_ids = {r.id for r in records if r.date_confidence == "inferred"}
        assert len(inferred_ids) == 126
        assert inferred_ids | unresolved_ids == {r.id for r in records}
        for record in records:
            if record.date_confidence == "inferred":
                assert record.event_date == record.dateline, record.id

    def test_every_letter_to_thoreau_reaches_a_record(self, records):
        # Six letters in this volume are headed by a correspondent's name
        # rather than Thoreau's "TO ...", so none of them starts a record
        # of its own; each is carried inline in the record it sits in, the
        # same way Sanborn's connective narrative is
        # (docs/normalized-record-schema.md). Two of them - Channing's and
        # Lane's (three letters under the one heading) - used to reach no
        # record at all, because they follow a "FOOTNOTES:" block and the
        # whole tail was cut. A regression here means real source text is
        # silently absent from the archive again, in either direction.
        body = "\n".join(p for r in records for p in r.paragraphs)
        for heading in (
            "ELLERY CHANNING TO THOREAU (AT CONCORD).",
            "CHARLES LANE TO THOREAU (AT CONCORD).",
            "AGASSIZ TO THOREAU (AT CONCORD).",
            "T. CHOLMONDELEY TO THOREAU (IN MINNESOTA).",
            "SOPHIA THOREAU TO DANIEL RICKETSON (AT NEW BEDFORD).",
            "BRONSON ALCOTT TO DANIEL RICKETSON (AT NEW BEDFORD).",
        ):
            assert heading in body, heading

    def test_no_footnote_block_text_reaches_a_letter_record(self, records):
        # The other direction of the same boundary: excising only the block
        # must not let Sanborn's endnotes back into the evidence. Each of
        # the volume's four blocks opens with a bracketed number at the
        # start of a paragraph, which no letter's own prose ever does.
        for record in records:
            for paragraph in record.paragraphs:
                assert "FOOTNOTES:" not in paragraph, record.id
                assert not re.match(r"^\[\d+\] ", paragraph), record.id

    def test_letter_ids_do_not_collide_with_journal_ids(self, records):
        from memoria.normalize import normalize_journals

        journal_records = normalize_journals(os.environ[EVIDENCE_ROOT_ENV_VAR])
        journal_ids = {r.id for r in journal_records}
        letter_ids = {r.id for r in normalize_letters(
            os.environ[EVIDENCE_ROOT_ENV_VAR], start_id=len(journal_records) + 1
        )}
        assert journal_ids.isdisjoint(letter_ids)
