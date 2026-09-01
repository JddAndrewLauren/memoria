"""Normalize raw journal volumes into per-entry SRC- records.

Scope of this module (issue #3): entry splitting for the two journal
volumes (J01, J02) on the line-initial italic date headings RECON.md
documents, stable ``SRC-`` ID assignment, stable paragraph anchors, and
quote-convention normalization. Year resolution, editorial-apparatus
segregation (footnotes, bracketed editorial spans, introductions), and
letters parsing are later slices - see docs/plan/16-build-order.md M0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Quote characters vary by volume (RECON.md §6.1): J01 and Familiar Letters
# use straight ASCII quotes; J02 uses curly Unicode quotes. Normalizing both
# to straight ASCII means one search convention works across every volume.
_QUOTE_TRANSLATION = str.maketrans(
    {
        "“": '"',  # left double quotation mark
        "”": '"',  # right double quotation mark
        "‘": "'",  # left single quotation mark
        "’": "'",  # right single quotation mark
    }
)


def normalize_quotes(text: str) -> str:
    """Collapse curly Unicode quotes to straight ASCII quotes."""
    return text.translate(_QUOTE_TRANSLATION)


# Journal volumes this slice normalizes, in the fixed order SRC- IDs are
# assigned across. Both raw .txt files are Distributed Proofreaders text:
# valid UTF-8, CRLF line endings throughout (RECON.md §1). Path.read_text()
# performs universal-newline translation, so CRLF is handled without any
# special-casing here.
JOURNAL_VOLUMES = [
    {
        "source_type": "journal",
        "raw_path": "raw/gutenberg/57393-journal-01/pg57393.txt",
        "volume_label": "Journal I",
    },
    {
        "source_type": "journal",
        "raw_path": "raw/gutenberg/59031-journal-02/pg59031.txt",
        "volume_label": "Journal II",
    },
]

_START_MARKER = re.compile(r"^\*\*\* START OF THE PROJECT GUTENBERG EBOOK")
_END_MARKER = re.compile(r"^\*\*\* END OF THE PROJECT GUTENBERG EBOOK")

# The printer's colophon and Torrey's endnote apparatus that closes each
# volume, between the last date heading and the Gutenberg END marker. Not
# part of any entry - it is 1906 back matter, not 1837-46 evidence.
_BACK_MATTER_MARKER = re.compile(r"^END OF VOLUME\b")

# RECON.md §3: entries open with a line-initial italic date, a small closed
# set of forms - re-verified against the raw corpus directly rather than
# trusting RECON.md's own summary counts (see docs/normalized-record-schema.md
# "Deviation from RECON.md's date-heading count"). Forms matched:
# "_Oct 22._", "_Oct. 24._", "_Jan. 24. Sunday._", "_Sept. 29, 1842._",
# "_May 3-4._", "_July 10 to 12._" (a "to"-range), "_Dec. 16, 17, 18._" (a
# comma list), bare "_Dec._" / "_Jan._" month-only headings, and a trailing
# qualifier that is either a weekday, a place ("_Nov. 29. Cambridge._"), or
# a weekday plus a lowercase second word ("_July 20. Sunday morning._").
_MONTHS = "Jan|Feb|March|April|May|June|July|Aug|Sept|Oct|Nov|Dec"
_DAY = r"\d{1,2}"
_DAY_RANGE = rf"{_DAY}(?:\s*(?:-|–|to)\s*{_DAY})?(?:,\s*{_DAY})*"
DATE_HEADING_RE = re.compile(
    rf"^_(?:{_MONTHS})\.?"
    rf"(?:\s+{_DAY_RANGE})?"
    rf"(?:,?\s*\d{{4}})?"
    rf"\.?"
    rf"(?:\s+[A-Z][a-zA-Z]*\.?(?:\s+[a-zA-Z]+\.?)?)?"
    rf"_"
)

# A paragraph that is nothing but chapter apparatus - a bare Roman numeral
# ("II"), a bare year or year range ("1838", "1845-1847"), or an age marker
# ("(ÆT. 20-21)") - landing inside an entry body because it sits between
# one chapter's last entry and the next chapter's first heading (part 05
# §5.2 boundaries are per-entry, not per-chapter).
_CHAPTER_MARKER_RE = re.compile(
    r"^(?:[IVXLCM]+|\d{4}(?:-\d{2,4})?|\(?ÆT\.\s*\d+(?:-\d+)?\)?)$"
)


@dataclass
class NormalizedRecord:
    id: str
    source_type: str
    recorded_date: str
    event_date: str
    date_confidence: str
    contemporaneous: bool
    original_file: str
    original_locator: str
    paragraphs: list[str] = field(default_factory=list)

    def anchor_id(self, paragraph_number: int) -> str:
        """The stable anchor id for this record's Nth paragraph (1-based).

        The single source of the citation contract downstream slices
        (#4-#7) target: ``f"{record.id} P{n}"`` in prose,
        ``record.anchor_id(n)`` as the ``#...`` fragment.
        """
        return f"{self.id.lower()}-p{paragraph_number}"


def _extract_body_lines(raw_text: str) -> list[str]:
    """Return the lines between the Gutenberg START/END markers, with the
    trailing back-matter colophon and endnotes cut off.

    Everything outside the START/END range - license boilerplate, the
    Transcriber's Note, Torrey's Introduction, Contents/Illustrations lists,
    and the trailing Gutenberg license - is front matter and boilerplate,
    excluded by construction. Everything from ``END OF VOLUME`` to the END
    marker - the printer's colophon and Torrey's footnote apparatus - is
    1906 back matter, excluded the same way.
    """
    lines = raw_text.splitlines()
    start_idx = end_idx = back_matter_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and _START_MARKER.match(line):
            start_idx = i
        elif back_matter_idx is None and _BACK_MATTER_MARKER.match(line):
            back_matter_idx = i
        elif _END_MARKER.match(line):
            end_idx = i
            break
    if start_idx is None or end_idx is None:
        raise ValueError("Gutenberg START/END markers not found")
    body_end = back_matter_idx if back_matter_idx is not None else end_idx
    return lines[start_idx + 1 : body_end]


def _split_entries(body_lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split body lines into (heading_text, entry_lines) per journal entry.

    A natural documentary boundary defines a record (part 05 §5.2): for the
    journals, one dated entry. Content before the first date heading -
    chapter titles ("I" / "1837" / "(ÆT. 20)") and any other remaining
    front matter - is not part of any entry and is discarded. (Chapter
    titles between later chapters land inside the preceding entry's trailing
    lines instead, and are filtered out at paragraph level - see
    ``_CHAPTER_MARKER_RE``.)
    """
    heading_indices = [
        i for i, line in enumerate(body_lines) if DATE_HEADING_RE.match(line)
    ]
    entries = []
    for position, start in enumerate(heading_indices):
        end = (
            heading_indices[position + 1]
            if position + 1 < len(heading_indices)
            else len(body_lines)
        )
        entry_lines = body_lines[start:end]
        heading_match = DATE_HEADING_RE.match(entry_lines[0])
        heading_text = heading_match.group(0).strip("_")
        entries.append((heading_text, entry_lines))
    return entries


def _paragraphs(entry_lines: list[str]) -> list[str]:
    text = "\n".join(entry_lines)
    raw_paragraphs = re.split(r"\n\s*\n", text)
    return [
        p.strip()
        for p in raw_paragraphs
        if p.strip() and not _CHAPTER_MARKER_RE.match(p.strip())
    ]


def normalize_journals(evidence_root: Path) -> list[NormalizedRecord]:
    """Normalize J01 and J02 into per-entry records with stable SRC- IDs.

    SRC- IDs are assigned sequentially in a fixed order - volume order
    (J01 then J02), then entry order within the volume - so re-running the
    normalizer over unchanged input reproduces the same IDs every time.
    """
    evidence_root = Path(evidence_root)
    records: list[NormalizedRecord] = []
    counter = 1
    for volume in JOURNAL_VOLUMES:
        raw_path = evidence_root / volume["raw_path"]
        raw_text = raw_path.read_text(encoding="utf-8")
        body_lines = _extract_body_lines(raw_text)
        for heading_text, entry_lines in _split_entries(body_lines):
            paragraphs = [normalize_quotes(p) for p in _paragraphs(entry_lines)]
            src_id = f"SRC-{counter:06d}"
            counter += 1
            records.append(
                NormalizedRecord(
                    id=src_id,
                    source_type=volume["source_type"],
                    # Year resolution is a later slice (part 05 §6): dates
                    # land here as whatever the heading says.
                    recorded_date=heading_text,
                    event_date=heading_text,
                    date_confidence="unresolved",
                    contemporaneous=True,
                    original_file=volume["raw_path"],
                    original_locator=(
                        f"{volume['volume_label']}, entry dated {heading_text}"
                    ),
                    paragraphs=paragraphs,
                )
            )
    return records


def _record_to_markdown(record: NormalizedRecord) -> str:
    frontmatter = {
        "id": record.id,
        "source_type": record.source_type,
        "recorded_date": record.recorded_date,
        "event_date": record.event_date,
        "date_confidence": record.date_confidence,
        "contemporaneous": record.contemporaneous,
        "original_file": record.original_file,
        "original_locator": record.original_locator,
    }
    # Paragraph anchors (part 05 §5.3): stable across re-runs because they
    # are positional within a record whose own ID is itself stable.
    body = "\n\n".join(
        f'<a id="{record.anchor_id(i)}"></a>\n\n{paragraph}'
        for i, paragraph in enumerate(record.paragraphs, start=1)
    )
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + body + "\n"


def write_normalized_records(
    records: list[NormalizedRecord], output_root: Path
) -> list[Path]:
    """Write one Markdown file per record to ``output_root``.

    Removes any ``SRC-*.md`` file already in ``output_root`` that this run
    did not (re)write, so a shrinking or reordered corpus does not leave
    stale orphans behind from a previous run.
    """
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    written = []
    for record in records:
        path = output_root / f"{record.id}.md"
        path.write_text(_record_to_markdown(record), encoding="utf-8")
        written.append(path)

    written_names = {path.name for path in written}
    for stale in output_root.glob("SRC-*.md"):
        if stale.name not in written_names:
            stale.unlink()

    return written
