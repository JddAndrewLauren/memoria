import os
import re
from collections import Counter

import pytest

from memoria.normalize import JOURNAL_VOLUMES, normalize_journals
from memoria.year_resolution import resolve_years

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


def _write_fake_volumes(evidence_root, volume_texts):
    """Write fake volume text at each configured JOURNAL_VOLUMES raw_path."""
    for volume, text in zip(JOURNAL_VOLUMES, volume_texts):
        path = evidence_root / volume["raw_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


# A synthetic multi-year J01-shaped chapter, matching the real corpus's
# 1845-1846 chapter's own genuine weekday-bearing entries and their real
# calendar weekdays (July 5, 1845 and July 5, 1846 fall on different
# weekdays, so the checksum picks exactly one).
_MULTI_YEAR_VOLUME = (
    "The Project Gutenberg eBook of Journal 98\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 98 ***\r\n"
    "\r\n"
    "VII\r\n"
    "\r\n"
    "1845-1846\r\n"
    "\r\n"
    "(ÆT. 27-29)\r\n"
    "\r\n"
    "_July 5. Saturday._ Walden.—Yesterday I came here to live.\r\n"
    "\r\n"
    "_July 6._ I wish to meet the facts of life.\r\n"
    "\r\n"
    "END OF VOLUME 98\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 98 ***\r\n"
)

# A synthetic single-year J01-shaped chapter (RECON.md §3: J01 chapters
# `1837`...`1842` carry exactly one year). Aug. 23, 1845 is a real
# Saturday, used below to exercise the weekday checksum honestly.
_SINGLE_YEAR_VOLUME = (
    "The Project Gutenberg eBook of Journal 99\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
    "\r\n"
    "I\r\n"
    "\r\n"
    "1845\r\n"
    "\r\n"
    "(ÆT. 27-28)\r\n"
    "\r\n"
    "_Aug. 23. Saturday._ I set out this afternoon to go a-fishing.\r\n"
    "\r\n"
    "_Aug. 24._ The weather continued fair.\r\n"
    "\r\n"
    "END OF VOLUME 99\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 99 ***\r\n"
)

_EMPTY_SECOND_VOLUME = (
    "The Project Gutenberg eBook of Journal 100\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 100 ***\r\n"
    "\r\n"
    "I\r\n"
    "\r\n"
    "1850\r\n"
    "\r\n"
    "_Nov. 3._ Nothing much happened.\r\n"
    "\r\n"
    "END OF VOLUME 100\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 100 ***\r\n"
)


def test_resolve_years_marks_a_weekday_confirmed_heading_exact(tmp_path):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_SINGLE_YEAR_VOLUME, _EMPTY_SECOND_VOLUME])
    records = normalize_journals(evidence_root)

    resolve_years(records, evidence_root)

    saturday_entry = records[0]
    assert saturday_entry.recorded_date == "Aug. 23. Saturday."
    assert saturday_entry.date_confidence == "exact"
    assert saturday_entry.event_date == "Aug. 23. Saturday., 1845"


def test_resolve_years_marks_an_unambiguous_chapter_heading_inferred_without_a_weekday(
    tmp_path,
):
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_SINGLE_YEAR_VOLUME, _EMPTY_SECOND_VOLUME])
    records = normalize_journals(evidence_root)

    resolve_years(records, evidence_root)

    no_weekday_entry = records[1]
    assert no_weekday_entry.recorded_date == "Aug. 24."
    assert no_weekday_entry.date_confidence == "inferred"
    assert no_weekday_entry.event_date == "Aug. 24., 1845"


def test_resolve_years_uses_the_weekday_checksum_to_pick_a_single_year_in_a_multi_year_chapter(
    tmp_path,
):
    # Acceptance criterion: "An entry inside a multi-year chapter resolves
    # to a single exact year via its weekday." July 5 falls on a Saturday
    # in 1845 but a Sunday in 1846 - only 1845 satisfies the heading's
    # stated "Saturday", so the checksum picks it exactly, without a
    # chapter heading that names a single year.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_MULTI_YEAR_VOLUME, _EMPTY_SECOND_VOLUME])
    records = normalize_journals(evidence_root)

    resolve_years(records, evidence_root)

    weekday_confirmed_entry = records[0]
    assert weekday_confirmed_entry.recorded_date == "July 5. Saturday."
    assert weekday_confirmed_entry.date_confidence == "exact"
    assert weekday_confirmed_entry.event_date == "July 5. Saturday., 1845"

    # The following entry has no weekday to confirm it, so it resolves by
    # position within the chapter (carrying 1845 forward) - inferred, not
    # exact.
    position_entry = records[1]
    assert position_entry.recorded_date == "July 6."
    assert position_entry.date_confidence == "inferred"
    assert position_entry.event_date == "July 6., 1845"


def test_resolve_years_never_marks_a_record_exact_without_a_weekday(tmp_path):
    # Acceptance criterion: a mismatch between the stated weekday and every
    # candidate year must never be silently accepted as exact - and no
    # entry lacking a weekday at all can be exact either.
    evidence_root = tmp_path / "thoreau-evidence"
    _write_fake_volumes(evidence_root, [_MULTI_YEAR_VOLUME, _SINGLE_YEAR_VOLUME])
    records = normalize_journals(evidence_root)

    resolve_years(records, evidence_root)

    for record in records:
        if record.date_confidence == "exact":
            assert re.search(
                r"\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b",
                record.recorded_date,
            ), record.id


def test_resolve_years_surfaces_a_weekday_checksum_mismatch_as_a_warning(tmp_path):
    # Aug. 23 fell on a Saturday in 1845, not 1846 - a heading stating
    # "Sunday" for a year the chapter pins to 1845 alone is a genuine
    # editorial discrepancy (RECON.md §3), not something to guess past.
    evidence_root = tmp_path / "thoreau-evidence"
    mismatched_volume = _SINGLE_YEAR_VOLUME.replace(
        "_Aug. 23. Saturday._", "_Aug. 23. Sunday._"
    )
    _write_fake_volumes(evidence_root, [mismatched_volume, _EMPTY_SECOND_VOLUME])
    records = normalize_journals(evidence_root)

    warnings = resolve_years(records, evidence_root)

    mismatched_entry = records[0]
    assert mismatched_entry.date_confidence == "inferred"
    assert mismatched_entry.event_date == "Aug. 23. Sunday., 1845"
    assert any("SRC-000001" in w and "not a Sunday" in w for w in warnings)


def test_resolve_years_carries_the_running_year_across_a_chapter_boundary(tmp_path):
    # current_year/current_month are reset only per volume, not per
    # chapter, so a multi-year chapter's very first entry can still be
    # position-resolved from the previous chapter's last known date. This
    # is the real corpus's J01 "1845-1847" chapter: its lone entry ("Feb.
    # 22", no year, no weekday) rolls forward from the preceding chapter's
    # "March 27, 1846" to land on 1847 (Feb < March signals a year
    # rollover).
    evidence_root = tmp_path / "thoreau-evidence"
    two_chapter_volume = (
        "The Project Gutenberg eBook of Journal 96\r\n"
        "\r\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 96 ***\r\n"
        "\r\n"
        "VII\r\n"
        "\r\n"
        "1845-1846\r\n"
        "\r\n"
        "_March 26, 1846._ The change from foul weather to fair.\r\n"
        "\r\n"
        "_March 27._ This morning I saw the geese.\r\n"
        "\r\n"
        "VIII\r\n"
        "\r\n"
        "1845-1847\r\n"
        "\r\n"
        "_Feb. 22_ Jean Lapin sat at my door to-day.\r\n"
        "\r\n"
        "END OF VOLUME 96\r\n"
        "\r\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 96 ***\r\n"
    )
    _write_fake_volumes(evidence_root, [two_chapter_volume, _EMPTY_SECOND_VOLUME])
    records = normalize_journals(evidence_root)

    resolve_years(records, evidence_root)

    feb_entry = records[2]
    assert feb_entry.recorded_date == "Feb. 22"
    assert feb_entry.date_confidence == "inferred"
    assert feb_entry.event_date == "Feb. 22, 1847"


def test_resolve_years_marks_a_volumes_undated_opening_fragments_chapter_only(
    tmp_path,
):
    # RECON.md §3: J02 Chapter I "opens with undated fragments separated by
    # `*   *   *   *   *` dividers ... They need `date_confidence:
    # chapter-only` - scoped to 1850, no day." The chapter gives the year;
    # the fragment gives no day, so neither date field is filled in.
    evidence_root = tmp_path / "thoreau-evidence"
    fragment_volume = (
        "The Project Gutenberg eBook of Journal 95\r\n"
        "\r\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 95 ***\r\n"
        "\r\n"
        "I\r\n"
        "\r\n"
        "1850 (ÆT. 32-33)\r\n"
        "\r\n"
        "The Hindoos are more serenely religious than the Hebrews.\r\n"
        "\r\n"
        "       *       *       *       *       *\r\n"
        "\r\n"
        "Man flows at once to God as soon as the channel is open.\r\n"
        "\r\n"
        "_June 20._ I can see from my window three or four cows.\r\n"
        "\r\n"
        "END OF VOLUME 95\r\n"
        "\r\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 95 ***\r\n"
    )
    _write_fake_volumes(evidence_root, [fragment_volume, _EMPTY_SECOND_VOLUME])
    records = normalize_journals(evidence_root)

    resolve_years(records, evidence_root)

    fragments = [r for r in records if not r.recorded_date]
    assert len(fragments) == 2
    for fragment in fragments:
        assert fragment.date_confidence == "chapter-only"
        assert fragment.event_date == ""

    # The dated entry that follows still resolves against the same chapter -
    # the fragments take no part in the record-to-heading pairing.
    dated_entry = records[2]
    assert dated_entry.recorded_date == "June 20."
    assert dated_entry.date_confidence == "inferred"
    assert dated_entry.event_date == "June 20., 1850"


def test_resolve_years_leaves_an_entry_with_no_governing_chapter_unresolved(tmp_path):
    # A *dated* entry preceding any chapter marker has a heading to resolve
    # but no year context to resolve it against - distinct from
    # `chapter-only`, which is the opposite case (a chapter year, but no
    # heading of its own). Must not invent an event_date either way.
    evidence_root = tmp_path / "thoreau-evidence"
    headerless_volume = (
        "The Project Gutenberg eBook of Journal 97\r\n"
        "\r\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK JOURNAL 97 ***\r\n"
        "\r\n"
        "_June 20._ I can see from my window three or four cows.\r\n"
        "\r\n"
        "I\r\n"
        "\r\n"
        "1850\r\n"
        "\r\n"
        "_Nov. 3._ Nothing much happened.\r\n"
        "\r\n"
        "END OF VOLUME 97\r\n"
        "\r\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK JOURNAL 97 ***\r\n"
    )
    _write_fake_volumes(evidence_root, [headerless_volume, _EMPTY_SECOND_VOLUME])
    records = normalize_journals(evidence_root)

    resolve_years(records, evidence_root)

    chapterless_entry = records[0]
    assert chapterless_entry.recorded_date == "June 20."
    assert chapterless_entry.date_confidence == "unresolved"
    assert chapterless_entry.event_date == chapterless_entry.recorded_date

    dated_entry = records[1]
    assert dated_entry.recorded_date == "Nov. 3."
    assert dated_entry.date_confidence == "inferred"
    assert dated_entry.event_date == "Nov. 3., 1850"


@pytest.mark.m0
@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
class TestAgainstTheRealEvidenceCorpus:
    @pytest.fixture(scope="class")
    @staticmethod
    def records():
        evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
        records = normalize_journals(evidence_root)
        resolve_years(records, evidence_root)
        return records

    def test_every_record_carries_event_date_and_a_recognized_confidence(self, records):
        for record in records:
            # A `chapter-only` fragment is the one record shape with no
            # event_date at all: it has no date heading, so there is no date
            # to carry and none may be invented. Every dated record still
            # carries one.
            if record.date_confidence == "chapter-only":
                assert record.event_date == ""
            else:
                assert record.event_date
            assert record.date_confidence in ("exact", "inferred", "chapter-only")

    def test_no_record_is_exact_without_a_weekday_in_its_heading(self, records):
        weekday = re.compile(
            r"\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b"
        )
        for record in records:
            if record.date_confidence == "exact":
                assert weekday.search(record.recorded_date), record.id

    def test_an_entry_inside_the_1845_1846_multi_year_chapter_resolves_exact_via_weekday(
        self, records
    ):
        # RECON.md §3 / issue #4: J01's chapter VII spans 1845-1846 with no
        # single-year chapter heading to fall back on. "_July 5.
        # Saturday._" is a real Saturday in 1845 and a real Sunday in 1846
        # - the weekday checksum picks 1845 exactly.
        entry = next(
            r for r in records if r.recorded_date == "July 5. Saturday."
        )
        assert entry.date_confidence == "exact"
        assert entry.event_date == "July 5. Saturday., 1845"

    def test_j02_chapter_i_entries_carry_no_invented_event_date_when_undated(
        self, records
    ):
        # The invariant chapter-only exists to guarantee: nothing gets an
        # event_date it did not earn. J02 Chapter I's 29 undated opening
        # fragments are the records that exercise it - they carry neither a
        # recorded_date nor an event_date, and they are the only journal
        # records that carry neither.
        undated = [r for r in records if r.date_confidence == "chapter-only"]
        assert len(undated) == 29
        for record in undated:
            assert record.recorded_date == ""
            assert record.event_date == ""
            assert record.original_file.endswith("pg59031.txt")
            assert "Chapter I, undated fragment" in record.original_locator

    def test_confidence_counts_reconcile_with_the_weekday_checked_headings(self, records):
        # Per docs/normalized-record-schema.md, this slice resolves all
        # 587 records with no invented event_date: 558 dated entries, plus
        # J02 Chapter I's 29 undated fragments as chapter-only. ~100
        # headings carry a weekday (issue #4); 152 actually do, of which 2
        # fail the checksum against a real calendar (SRC-000332's "Sept.
        # 5. Saturday." - actually a Sunday in 1841; SRC-000493's "May 6.
        # Monday." - actually a Tuesday in 1851), both surfaced as
        # warnings rather than marked exact.
        counts = Counter(r.date_confidence for r in records)
        assert counts["chapter-only"] == 29
        assert counts["exact"] == 150
        assert counts["inferred"] == 408
        assert sum(counts.values()) == 587

    def test_weekday_checksum_failures_are_surfaced_as_warnings_not_silently_accepted(
        self, records
    ):
        evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
        fresh_records = normalize_journals(evidence_root)
        warnings = resolve_years(fresh_records, evidence_root)

        assert any("SRC-000332" in w for w in warnings)
        assert any("SRC-000493" in w for w in warnings)
        mismatched = {r.id: r for r in fresh_records if r.id in ("SRC-000332", "SRC-000464")}
        for record in mismatched.values():
            assert record.date_confidence == "inferred"
