"""Year resolution for normalized journal records (issue #4).

Journal entry headings carry month and day but almost never a year - the
year lives on the enclosing chapter heading (RECON.md §3), and three J01
chapters span multiple years (`1845-1846`, `1845-1847`, `1837-1847`), so a
chapter heading alone is not always enough. About 100 headings also carry a
weekday (`_Jan. 24. Sunday._`); for a given month/day, only one candidate
year normally puts that date on that weekday, so the weekday is a free,
mechanical checksum on the year - the primary resolution path.

This module resolves ``event_date``/``date_confidence`` on records
``normalize_journals`` already produced (with ``date_confidence:
unresolved``). It does not change entry boundaries or paragraph content.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from memoria.normalize import DATE_HEADING_RE, JOURNAL_VOLUMES, _extract_body_lines

_MONTH_TO_NUM = {
    "Jan": 1,
    "Feb": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "Aug": 8,
    "Sept": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
_MONTH_RE = re.compile(r"(Jan|Feb|March|April|May|June|July|Aug|Sept|Oct|Nov|Dec)")
_DAY_RE = re.compile(r"\b(\d{1,2})\b")
_YEAR_RE = re.compile(r"\b(\d{4})\b")
_WEEKDAY_RE = re.compile(
    r"\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b"
)
_WEEKDAY_NUM = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

# A chapter marker line is a bare Roman numeral, flush left (no leading
# whitespace - front-matter title-page lines like "     I" are indented and
# must not match). RECON.md §3: J01 chapters are bare years, J02 chapters
# are month-scoped; both open with a Roman-numeral chapter number.
_CHAPTER_MARKER_LINE_RE = re.compile(r"^[IVXLCM]+$")

# A chapter's candidate-year range spans at most this many years - guards
# the year-line parser against picking up unrelated 4-digit numbers that
# happen to sit on the line following a stray Roman-numeral-shaped line.
_MAX_CHAPTER_YEAR_SPAN = 15


def _parse_heading(recorded_date: str) -> tuple[int | None, int | None, int | None, str | None]:
    """Extract (month, day, explicit_year, weekday) from a heading's
    ``recorded_date`` text, e.g. "Jan. 24. Sunday." -> (1, 24, None,
    "Sunday"); "Sept. 29, 1842." -> (9, 29, 1842, None).
    """
    month_match = _MONTH_RE.match(recorded_date)
    month = _MONTH_TO_NUM[month_match.group(1)] if month_match else None
    day_match = _DAY_RE.search(recorded_date)
    day = int(day_match.group(1)) if day_match else None
    year_match = _YEAR_RE.search(recorded_date)
    explicit_year = int(year_match.group(1)) if year_match else None
    weekday_match = _WEEKDAY_RE.search(recorded_date)
    weekday = weekday_match.group(1) if weekday_match else None
    return month, day, explicit_year, weekday


def _parse_candidate_years(chapter_year_text: str) -> list[int]:
    """Parse a chapter's year line into its candidate years, e.g. "1838"
    -> [1838]; "1845-1847" -> [1845, 1846, 1847]; "DECEMBER, 1850" -> [1850].
    """
    years = [int(y) for y in re.findall(r"\d{4}", chapter_year_text)]
    if not years:
        return []
    low, high = min(years), max(years)
    if high - low > _MAX_CHAPTER_YEAR_SPAN:
        return []
    return list(range(low, high + 1))


def _find_chapters(body_lines: list[str]) -> list[tuple[int, list[int]]]:
    """Locate each chapter marker's line index and its candidate years, in
    document order.
    """
    chapters = []
    for i, line in enumerate(body_lines):
        if not _CHAPTER_MARKER_LINE_RE.match(line):
            continue
        j = i + 1
        while j < len(body_lines) and not body_lines[j].strip():
            j += 1
        if j >= len(body_lines):
            continue
        years = _parse_candidate_years(body_lines[j])
        if years:
            chapters.append((i, years))
    return chapters


def _chapter_years_at(chapters: list[tuple[int, list[int]]], position: int) -> list[int] | None:
    """The candidate years of the chapter governing a line at ``position``,
    or ``None`` if no chapter marker precedes it.
    """
    years = None
    for start, chapter_years in chapters:
        if start <= position:
            years = chapter_years
        else:
            break
    return years


def _weekday_matches(month: int, day: int, year: int, weekday: str) -> bool:
    try:
        candidate = date(year, month, day)
    except ValueError:
        return False
    return candidate.weekday() == _WEEKDAY_NUM[weekday]


def _resolved_event_date(recorded_date: str, year: int, explicit_year: int | None) -> str:
    if explicit_year is not None:
        return recorded_date
    return f"{recorded_date}, {year}"


def resolve_years(records, evidence_root) -> list[str]:
    """Resolve ``event_date`` and ``date_confidence`` on every journal
    record in place.

    Returns a list of human-readable warnings for headings that carry a
    weekday whose checksum did not confirm the year resolution chose - a
    genuine editorial problem worth surfacing rather than guessing
    (RECON.md §3), never silently swallowed into a wrong `exact`.
    """
    evidence_root = Path(evidence_root)
    warnings: list[str] = []
    records_by_file: dict[str, list] = {}
    for record in records:
        records_by_file.setdefault(record.original_file, []).append(record)

    for volume in JOURNAL_VOLUMES:
        volume_records = records_by_file.get(volume["raw_path"], [])
        if not volume_records:
            continue
        raw_text = (evidence_root / volume["raw_path"]).read_text(encoding="utf-8")
        body_lines = _extract_body_lines(raw_text)
        heading_positions = [
            i for i, line in enumerate(body_lines) if DATE_HEADING_RE.match(line)
        ]
        chapters = _find_chapters(body_lines)

        assert len(volume_records) == len(heading_positions), (
            f"{volume['raw_path']}: normalize_journals produced "
            f"{len(volume_records)} records but {len(heading_positions)} "
            "date headings were found on this pass - they must zip 1:1, "
            "in order, or entries and their chapter positions would "
            "silently drift apart."
        )

        # current_year/current_month carry forward across chapter
        # boundaries (reset only per volume, not per chapter) so a
        # position-resolved entry can use the immediately preceding
        # entry's date as its starting point even at a chapter's own
        # first entry - e.g. the real corpus's J01 "1845-1847" chapter
        # has exactly one entry ("Feb. 22", no year, no weekday); the
        # month-rollover check below carries March 1846 forward from the
        # previous chapter, sees Feb < March, and rolls it to 1847.
        current_year = None
        current_month = None
        for record, position in zip(volume_records, heading_positions):
            chapter_years = _chapter_years_at(chapters, position)
            month, day, explicit_year, weekday = _parse_heading(record.recorded_date)

            if chapter_years is None:
                # No chapter marker precedes this entry at all - we have no
                # year context whatsoever. Leave event_date untouched
                # rather than inventing one (RECON.md §3: J02 Chapter I's
                # undated fragments).
                record.date_confidence = "chapter-only"
                continue

            confirmed_by_weekday = False
            if explicit_year is not None:
                year = explicit_year
            elif len(chapter_years) == 1:
                year = chapter_years[0]
            elif weekday and day and month:
                matches = [
                    y
                    for y in chapter_years
                    if _weekday_matches(month, day, y, weekday)
                ]
                if len(matches) == 1:
                    year = matches[0]
                    confirmed_by_weekday = True
                else:
                    # Checksum failed to pick a single year (no match, or
                    # more than one) - fall back to position rather than
                    # guess, and surface it.
                    warnings.append(
                        f"{record.id}: weekday {weekday!r} matched "
                        f"{len(matches)} of the candidate years "
                        f"{chapter_years} for heading "
                        f"{record.recorded_date!r} - falling back to position"
                    )
                    year = (
                        current_year
                        if current_year in chapter_years
                        else chapter_years[0]
                    )
            else:
                # Position within a multi-year chapter, no weekday to
                # confirm: carry the running year forward, advancing it
                # when the month goes backwards (a rollover into the
                # chapter's next candidate year).
                if current_year is None or current_year not in chapter_years:
                    current_year = chapter_years[0]
                if (
                    current_month is not None
                    and month is not None
                    and month < current_month
                    and current_year + 1 in chapter_years
                ):
                    current_year += 1
                year = current_year

            if weekday and day and month and not confirmed_by_weekday:
                if _weekday_matches(month, day, year, weekday):
                    confirmed_by_weekday = True
                else:
                    warnings.append(
                        f"{record.id}: heading {record.recorded_date!r} "
                        f"states {weekday}, but {year}-{month:02d}-{day:02d} "
                        f"was not a {weekday} - dating this entry as "
                        f"inferred rather than exact"
                    )

            record.event_date = _resolved_event_date(
                record.recorded_date, year, explicit_year
            )
            record.date_confidence = "exact" if confirmed_by_weekday else "inferred"

            current_year = year
            if month is not None:
                current_month = month

    return warnings
