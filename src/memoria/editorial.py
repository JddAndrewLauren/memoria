"""Segregate 1906 editorial apparatus out of 1837-46 journal evidence.

Scope of this module (issue #5): footnote markers and their footnote
bodies, bracketed editorial spans embedded in entry text, and the two
volume-level editor introductions (Bradford Torrey's in J01, F. B.
Sanborn's in Familiar Letters) are extracted into ``EditorialRecord``
objects, each linked back to the evidence record and paragraph anchor it
annotates. ``normalize_journals`` (issue #3) deliberately left this
apparatus inline - "segregating it into separate retrospective-editorial
records is a later M0 step" (normalize.py's module docstring); this
module is that later step.

Under docs/open-problems.md §6 an editorial record is retrospective
commentary *about* the evidence (what a 1906 editor knew), never itself
evidence (what Thoreau knew at the time) - so every record here carries
``retrospective=True`` and its own 1906 ``recorded_date``, distinct from
the ``event_date`` on the evidence record it annotates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from memoria.normalize import JOURNAL_VOLUMES, NormalizedRecord

# Both journal volumes and Familiar Letters are the same 1906 Houghton
# Mifflin "Writings" edition (RECON.md's corpus table) - the date an
# editorial record's own retrospective commentary was recorded.
_EDITION_DATE = "1906"

EDITORIAL_RELATIVE_PATH = "sources/editorial"

# The volume-level editor introductions this slice extracts whole, as one
# editorial record each - not linked to a specific evidence paragraph,
# since an introduction is retrospective commentary about the volume as a
# whole rather than an annotation of one entry.
INTRODUCTIONS = [
    {
        "raw_path": "raw/gutenberg/57393-journal-01/pg57393.txt",
        "volume_label": "Journal I",
        "editor": "Torrey",
        "start_heading": re.compile(r"^INTRODUCTION\s*$", re.M),
        "end_heading": re.compile(r"^THE JOURNAL OF HENRY DAVID THOREAU\s*$", re.M),
    },
    {
        "raw_path": "raw/gutenberg/43523-familiar-letters/pg43523.txt",
        "volume_label": "Familiar Letters",
        "editor": "Sanborn",
        "start_heading": re.compile(r"^INTRODUCTION\s*$", re.M),
        "end_heading": re.compile(r"^FAMILIAR LETTERS OF THOREAU\s*$", re.M),
    },
]

_FOOTNOTES_HEADING_RE = re.compile(r"^FOOTNOTES\s*$", re.M)
_END_MARKER = re.compile(r"^\*\*\* END OF THE PROJECT GUTENBERG EBOOK")

# A bracketed span, single-line or multi-line (a plain negated character
# class matches "\n" too, so this needs no re.S flag). Distinguishing a
# footnote marker from a bracketed editorial span is then just: is the
# bracket's inner text all digits?
_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")


@dataclass
class EditorialRecord:
    id: str
    editorial_type: str  # "footnote" | "bracketed-span" | "introduction"
    recorded_date: str
    retrospective: bool
    linked_record_id: str | None
    linked_anchor: str | None
    original_file: str
    original_locator: str
    text: str


def _clean_ws(text: str) -> str:
    """Collapse the line-wrap whitespace of raw Gutenberg text (leading
    indentation, mid-paragraph newlines) to single spaces."""
    return " ".join(text.split())


def _parse_footnote_bodies(raw_text: str) -> dict[int, str]:
    """Parse a volume's back-matter FOOTNOTES section into {number: body}.

    A footnote body can span several blank-line-separated paragraphs (a
    footnote citing several quoted examples, say), so a paragraph starts a
    *new* footnote only when it opens with "[N]" where N is the next
    expected number in strict sequence - not merely digits in brackets,
    since a footnote's own continuation text can coincidentally start a
    line with a bracketed number (e.g. a footnote discussing the year
    "[1840]"; matching on digits alone misidentifies it as footnote 1840).
    """
    heading = _FOOTNOTES_HEADING_RE.search(raw_text)
    if heading is None:
        return {}
    end = _END_MARKER.search(raw_text, heading.end())
    section = raw_text[heading.end() : end.start() if end else len(raw_text)]

    bodies: dict[int, str] = {}
    expected = 1
    current_number: int | None = None
    current_parts: list[str] = []
    for para in re.split(r"\n\s*\n", section):
        para = para.strip()
        if not para:
            continue
        match = re.match(r"^\[(\d+)\]\s*(.*)", para, re.S)
        if match and int(match.group(1)) == expected:
            if current_number is not None:
                bodies[current_number] = _clean_ws("\n\n".join(current_parts))
            current_number = int(match.group(1))
            current_parts = [match.group(2)]
            expected += 1
        else:
            current_parts.append(para)
    if current_number is not None:
        bodies[current_number] = _clean_ws("\n\n".join(current_parts))
    return bodies


def _extract_introduction_text(
    raw_text: str, start_heading: re.Pattern, end_heading: re.Pattern
) -> str:
    start = start_heading.search(raw_text)
    end = end_heading.search(raw_text, start.end()) if start else None
    if start is None or end is None:
        raise ValueError("introduction start/end markers not found")
    return _clean_ws(raw_text[start.end() : end.start()])


def _strip_editorial_apparatus_from_record(
    record: NormalizedRecord,
) -> tuple[list[str], dict[int, str | None], list[tuple[str | None, str]]]:
    """Strip footnote markers and bracketed spans out of one record's
    paragraphs, in place-equivalent fashion (the caller assigns the
    returned list back onto ``record.paragraphs``).

    A span that was a whole paragraph on its own (e.g. a standalone
    "[Two pages missing.]" aside) leaves that paragraph empty once
    stripped; it is then dropped and the surviving paragraphs renumber -
    the same treatment normalize.py already gives chapter-marker
    paragraphs, so anchors stay positional over what is actually evidence.
    An editorial span pulled from a dropped paragraph links to the
    nearest surviving paragraph's anchor instead (preceding, else
    following), so the citation still opens next to the evidence it
    annotates.

    Returns ``(cleaned_paragraphs, footnote_marker_anchors, bracket_spans)``:
      - ``footnote_marker_anchors``: {footnote number: resolved anchor id}
        for every numeric marker found.
      - ``bracket_spans``: [(resolved anchor id, span text)] for every
        non-numeric bracketed span found, in encounter order.
    """
    original_paragraphs = record.paragraphs
    footnote_hits: list[tuple[int, int]] = []  # (original_index, number)
    bracket_hits: list[tuple[int, str]] = []  # (original_index, text)
    cleaned: list[str] = []
    survives_at: dict[int, int] = {}  # original_index -> final anchor number

    for original_index, paragraph in enumerate(original_paragraphs):

        def _replace(match: re.Match, original_index: int = original_index) -> str:
            inner = match.group(0)[1:-1]
            if inner.isdigit():
                footnote_hits.append((original_index, int(inner)))
            else:
                bracket_hits.append((original_index, inner))
            return ""

        stripped = _clean_ws(_BRACKET_RE.sub(_replace, paragraph))
        if stripped:
            cleaned.append(stripped)
            survives_at[original_index] = len(cleaned)

    def _resolve_anchor(original_index: int) -> str | None:
        for i in range(original_index, -1, -1):
            if i in survives_at:
                return record.anchor_id(survives_at[i])
        for i in range(original_index, len(original_paragraphs)):
            if i in survives_at:
                return record.anchor_id(survives_at[i])
        return None

    footnote_anchors = {
        number: _resolve_anchor(original_index)
        for original_index, number in footnote_hits
    }
    bracket_spans = [
        (_resolve_anchor(original_index), text)
        for original_index, text in bracket_hits
    ]
    return cleaned, footnote_anchors, bracket_spans


def extract_editorial_apparatus(
    evidence_root: Path, records: list[NormalizedRecord]
) -> list[EditorialRecord]:
    """Extract editorial apparatus out of ``records`` (from
    ``normalize_journals``) plus the volume-level introductions.

    Mutates each record's ``paragraphs`` in place, stripping every
    footnote marker and bracketed editorial span so the evidence text
    reads continuously without them, and returns the ``EditorialRecord``
    list - one per footnote, one per non-numeric bracketed span found in
    entry text, and one per introduction - each linked back to the
    evidence record and paragraph anchor it annotates (or, for a footnote
    whose marker fell in text this slice does not cover - Torrey's
    Introduction, or J02's undated opening fragments discarded by #3 -
    left unlinked rather than dropped, per "nothing in this slice deletes
    anything").
    """
    evidence_root = Path(evidence_root)
    editorial: list[EditorialRecord] = []
    counter = 1

    def next_id() -> str:
        nonlocal counter
        editorial_id = f"ED-{counter:06d}"
        counter += 1
        return editorial_id

    for intro in INTRODUCTIONS:
        raw_text = (evidence_root / intro["raw_path"]).read_text(encoding="utf-8")
        text = _extract_introduction_text(
            raw_text, intro["start_heading"], intro["end_heading"]
        )
        editorial.append(
            EditorialRecord(
                id=next_id(),
                editorial_type="introduction",
                recorded_date=_EDITION_DATE,
                retrospective=True,
                linked_record_id=None,
                linked_anchor=None,
                original_file=intro["raw_path"],
                original_locator=(
                    f"{intro['volume_label']}, Introduction ({intro['editor']})"
                ),
                text=text,
            )
        )

    records_by_file: dict[str, list[NormalizedRecord]] = {}
    for record in records:
        records_by_file.setdefault(record.original_file, []).append(record)

    for volume in JOURNAL_VOLUMES:
        volume_records = records_by_file.get(volume["raw_path"], [])
        if not volume_records:
            continue
        raw_text = (evidence_root / volume["raw_path"]).read_text(encoding="utf-8")
        footnote_bodies = _parse_footnote_bodies(raw_text)

        marker_links: dict[int, tuple[str, str | None]] = {}
        pending_spans: list[tuple[NormalizedRecord, str | None, str]] = []

        for record in volume_records:
            cleaned, footnote_anchors, bracket_spans = (
                _strip_editorial_apparatus_from_record(record)
            )
            record.paragraphs = cleaned
            for number, anchor in footnote_anchors.items():
                marker_links[number] = (record.id, anchor)
            for anchor, text in bracket_spans:
                pending_spans.append((record, anchor, text))

        for number in sorted(footnote_bodies):
            linked_record_id, linked_anchor = marker_links.get(number, (None, None))
            editorial.append(
                EditorialRecord(
                    id=next_id(),
                    editorial_type="footnote",
                    recorded_date=_EDITION_DATE,
                    retrospective=True,
                    linked_record_id=linked_record_id,
                    linked_anchor=linked_anchor,
                    original_file=volume["raw_path"],
                    original_locator=f"{volume['volume_label']}, footnote {number}",
                    text=footnote_bodies[number],
                )
            )

        for record, anchor, text in pending_spans:
            locator = f"{volume['volume_label']}, {record.id}"
            if anchor:
                locator += f" {anchor}"
            editorial.append(
                EditorialRecord(
                    id=next_id(),
                    editorial_type="bracketed-span",
                    recorded_date=_EDITION_DATE,
                    retrospective=True,
                    linked_record_id=record.id,
                    linked_anchor=anchor,
                    original_file=volume["raw_path"],
                    original_locator=locator,
                    text=_clean_ws(text),
                )
            )

    return editorial


def _editorial_record_to_markdown(record: EditorialRecord) -> str:
    frontmatter = {
        "id": record.id,
        "editorial_type": record.editorial_type,
        "recorded_date": record.recorded_date,
        "retrospective": record.retrospective,
        "linked_record_id": record.linked_record_id,
        "linked_anchor": record.linked_anchor,
        "original_file": record.original_file,
        "original_locator": record.original_locator,
    }
    return (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n\n"
        + record.text
        + "\n"
    )


def write_editorial_records(
    records: list[EditorialRecord], output_root: Path
) -> list[Path]:
    """Write one Markdown file per editorial record to ``output_root``.

    Removes any ``ED-*.md`` file already in ``output_root`` that this run
    did not (re)write - the same stale-orphan cleanup
    ``write_normalized_records`` performs for ``SRC-*.md``.
    """
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    written = []
    for record in records:
        path = output_root / f"{record.id}.md"
        path.write_text(_editorial_record_to_markdown(record), encoding="utf-8")
        written.append(path)

    written_names = {path.name for path in written}
    for stale in output_root.glob("ED-*.md"):
        if stale.name not in written_names:
            stale.unlink()

    return written
