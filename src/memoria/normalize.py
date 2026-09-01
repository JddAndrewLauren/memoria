"""Normalize raw journal and letters volumes into per-entry SRC- records.

Scope of this module (issues #3, #6): entry splitting for the two journal
volumes (J01, J02) on the line-initial italic date headings RECON.md
documents, and letter splitting for the Familiar Letters volume on its
line-initial "TO ..." recipient headings; stable ``SRC-`` ID assignment,
stable paragraph anchors, and quote-convention normalization. Year
resolution and editorial-apparatus segregation (footnotes, bracketed
editorial spans, introductions) into separate retrospective records are
later slices - see docs/plan/16-build-order.md M0.
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

# Familiar Letters (issue #6): the volume this slice normalizes, alongside
# the journals. Single file, so a one-element list for the same shape as
# JOURNAL_VOLUMES.
LETTERS_VOLUME = {
    "source_type": "letter",
    "raw_path": "raw/gutenberg/43523-familiar-letters/pg43523.txt",
    "volume_label": "Familiar Letters",
}

# Letters open with a line-initial "TO <recipient>." heading (RECON.md §5) -
# re-verified directly against the raw corpus: exactly 130 such headings,
# 43 distinct verbatim strings, matching RECON's own counts exactly, with
# zero false positives anywhere in this file (review round 1 on PR #52).
# Deliberately loose (any text after "TO "): safe for this one volume, but
# would need tightening (a real correspondent-name shape) before it could
# be trusted against a second letters volume with different formatting.
_LETTER_HEADING_RE = re.compile(r"^TO .+")

# The two audit targets (issue #9): the published works the journals'
# cross-references point at, held in the corpus as Gutenberg text
# (manifest role ``audit_target``). Normalized so that the answer key has a
# stable ``SRC-`` ID and paragraph anchor to name on the target side - the
# journals and letters had one from #3 and #6, the books had none.
#
# One record per chapter. A chapter is the natural documentary boundary
# here (part 05 §5.2) the way a dated entry is for a journal: it is what
# the work itself declares in its own Contents.
#
# ``chapters`` is a closed set taken from each volume's own Contents block,
# matched **in document order** - the same discipline DATE_HEADING_RE
# applies to date headings, and necessary for the same reason. A generic
# "line is all capitals" rule would take Week's poem title THE INWARD
# MORNING (pg4232.txt:8936) for a ninth chapter, and Walden's title-page
# line "ON THE DUTY OF CIVIL DISOBEDIENCE" (pg205.txt:36) for the start of
# its last chapter, 9,385 lines early.
TARGET_VOLUMES = [
    {
        "source_type": "book",
        "raw_path": "raw/gutenberg/4232-a-week/pg4232.txt",
        "volume_label": "A Week on the Concord and Merrimack Rivers",
        "work": "Week",
        "published_year": "1849",
        "chapters": [
            "CONCORD RIVER",
            "SATURDAY",
            "SUNDAY",
            "MONDAY",
            "TUESDAY",
            "WEDNESDAY",
            "THURSDAY",
            "FRIDAY",
        ],
    },
    {
        "source_type": "book",
        "raw_path": "raw/gutenberg/205-walden/pg205.txt",
        "volume_label": "Walden",
        "work": "Walden",
        "published_year": "1854",
        "chapters": [
            "Economy",
            "Where I Lived, and What I Lived For",
            "Reading",
            "Sounds",
            "Solitude",
            "Visitors",
            "The Bean-Field",
            "The Village",
            "The Ponds",
            "Baker Farm",
            "Higher Laws",
            "Brute Neighbors",
            "House-Warming",
            "Former Inhabitants and Winter Visitors",
            "Winter Animals",
            "The Pond in Winter",
            "Spring",
            "Conclusion",
            # Gutenberg 205 is "Walden, and On The Duty Of Civil
            # Disobedience": one file, two works. The essay is carried as a
            # final chapter rather than dropped, so the file normalizes
            # whole - no cross-reference cites it.
            "ON THE DUTY OF CIVIL DISOBEDIENCE",
        ],
    },
]

# The printer's end-of-work line, which sits between Walden's last
# paragraph and the Civil Disobedience heading. Not prose.
_THE_END_RE = re.compile(r"^THE END$")

# No back matter to cut in the audit-target files.
_NEVER_RE = re.compile(r"(?!)")

# Familiar Letters' back matter (RECON.md §5): the General Index that
# follows the last letter. Analogous to the journals' END OF VOLUME cut -
# excluded by construction rather than swallowed into the last letter.
_GENERAL_INDEX_MARKER = re.compile(r"^GENERAL INDEX$")

# A trailing footnote collection (Sanborn's endnotes for the preceding
# stretch of letters) can land inside an entry's own lines, the same way
# the journals' back matter used to land inside their last entry (PR #48
# review round 1). Trimmed out of every letter's lines, not just the last.
_FOOTNOTES_MARKER = re.compile(r"^FOOTNOTES:$")

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

# A chapter marker line is a bare Roman numeral, flush left (no leading
# whitespace - front-matter title-page lines like "     I" are indented and
# must not match). RECON.md §3: J01 chapters are bare years, J02 chapters
# are month-scoped; both open with a Roman-numeral chapter number, followed
# by a year line ("1837", "1850 (ÆT. 32-33)[1]", "DECEMBER, 1850").
# Defined here rather than in year_resolution because entry splitting is
# the earlier consumer - the volume's first chapter heading is where a
# volume's evidence begins; year_resolution imports it from here.
_CHAPTER_MARKER_LINE_RE = re.compile(r"^[IVXLCM]+$")

# RECON.md §3: J02 Chapter I "opens (L319) with undated fragments separated
# by `*   *   *   *   *` dividers ... transcript-book extracts, not dated
# entries". The same dividers also separate thoughts *inside* dated entries
# (156 in J02, 581 in J01), so a divider is only an entry boundary in the
# one place where there is no date heading to be a boundary instead: a
# volume's undated opening, between its first chapter heading and its first
# date heading.
_DIVIDER_RE = re.compile(r"^\s*\*(?:\s+\*)+\s*$")


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
    # Letter-specific structured fields (issue #6). None for journal
    # records; always set for letter records.
    recipient: str | None = None
    dateline: str | None = None
    salutation: str | None = None
    # Book-specific structured fields (issue #9). None for journal and
    # letter records; always set for the audit-target book records.
    work: str | None = None
    chapter: str | None = None

    def anchor_id(self, paragraph_number: int) -> str:
        """The stable anchor id for this record's Nth paragraph (1-based).

        The single source of the citation contract downstream slices
        (#4-#7) target: ``f"{record.id} P{n}"`` in prose,
        ``record.anchor_id(n)`` as the ``#...`` fragment.
        """
        return f"{self.id.lower()}-p{paragraph_number}"


def _extract_body_lines(
    raw_text: str, back_matter_marker: re.Pattern = _BACK_MATTER_MARKER
) -> list[str]:
    """Return the lines between the Gutenberg START/END markers, with the
    trailing back matter cut off.

    Everything outside the START/END range - license boilerplate, the
    Transcriber's Note, an editor's introduction, Contents/Illustrations
    lists, and the trailing Gutenberg license - is front matter and
    boilerplate, excluded by construction. Everything from the first line
    matching ``back_matter_marker`` to the END marker - the journals'
    printer's colophon and endnote apparatus, or the letters' General
    Index - is 1906 back matter, excluded the same way.
    """
    lines = raw_text.splitlines()
    start_idx = end_idx = back_matter_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and _START_MARKER.match(line):
            start_idx = i
        elif back_matter_idx is None and back_matter_marker.match(line):
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


def _first_chapter_heading(body_lines: list[str]) -> tuple[str, int] | None:
    """Locate the volume's first chapter heading: its Roman numeral and the
    index of the first line *after* its year line.

    Both parts of the heading are chapter apparatus, not evidence, so the
    undated opening begins after them. The year line is required (a
    Roman-numeral line whose next non-blank line carries no four-digit year
    is not a chapter heading) so a stray flush-left "I" in the front matter
    cannot be mistaken for one.
    """
    for i, line in enumerate(body_lines):
        if not _CHAPTER_MARKER_LINE_RE.match(line):
            continue
        year_line = i + 1
        while year_line < len(body_lines) and not body_lines[year_line].strip():
            year_line += 1
        if year_line < len(body_lines) and re.search(r"\d{4}", body_lines[year_line]):
            return line, year_line + 1
    return None


def _split_undated_opening(body_lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split a volume's undated opening into (chapter_numeral, fragment_lines).

    A natural documentary boundary defines a record (part 05 §5.2). These
    fragments have no date heading to bound them, so the divider that the
    1906 edition sets between them is the boundary instead - the only one
    the source offers (RECON.md §3). Everything from the first chapter
    heading to the first date heading is in scope; for J01 that is the
    chapter's age marker and nothing else, so J01 yields no fragments.
    """
    heading = _first_chapter_heading(body_lines)
    if heading is None:
        return []
    numeral, region_start = heading
    date_headings = [
        i for i, line in enumerate(body_lines) if DATE_HEADING_RE.match(line)
    ]
    if not date_headings or date_headings[0] <= region_start:
        return []
    region = body_lines[region_start : date_headings[0]]

    fragments = []
    current: list[str] = []
    for line in region:
        if _DIVIDER_RE.match(line):
            fragments.append(current)
            current = []
        else:
            current.append(line)
    fragments.append(current)
    # A fragment holding nothing but the chapter's remaining apparatus (or
    # nothing at all) is not a record - _paragraphs is the same filter the
    # dated entries use.
    return [(numeral, lines) for lines in fragments if _paragraphs(lines)]


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
    A volume's undated opening fragments (RECON.md §3) come first within
    their volume, since that is the order they appear in the source.
    """
    evidence_root = Path(evidence_root)
    records: list[NormalizedRecord] = []
    counter = 1
    for volume in JOURNAL_VOLUMES:
        raw_path = evidence_root / volume["raw_path"]
        raw_text = raw_path.read_text(encoding="utf-8")
        body_lines = _extract_body_lines(raw_text)
        fragments = _split_undated_opening(body_lines)
        for position, (numeral, fragment_lines) in enumerate(fragments, start=1):
            paragraphs = [normalize_quotes(p) for p in _paragraphs(fragment_lines)]
            src_id = f"SRC-{counter:06d}"
            counter += 1
            records.append(
                NormalizedRecord(
                    id=src_id,
                    source_type=volume["source_type"],
                    # No date heading at all, so nothing to record and
                    # nothing to resolve into: year resolution marks these
                    # chapter-only and leaves both fields empty rather than
                    # inventing a date the source does not give.
                    recorded_date="",
                    event_date="",
                    date_confidence="unresolved",
                    contemporaneous=True,
                    original_file=volume["raw_path"],
                    original_locator=(
                        f"{volume['volume_label']}, Chapter {numeral}, "
                        f"undated fragment {position} of {len(fragments)}"
                    ),
                    paragraphs=paragraphs,
                )
            )
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


def _trim_trailing_footnotes(entry_lines: list[str]) -> list[str]:
    """Cut a letter's lines off at a trailing ``FOOTNOTES:`` block, if any.

    Sanborn's endnotes for the preceding stretch of letters can land inside
    an entry's own lines - the same class of defect the journals' back
    matter caused when swallowed into their last entry (PR #48 review round
    1). Applied to every letter, not just the last, since a footnote block
    is never part of the letter's own body wherever it lands.
    """
    for i, line in enumerate(entry_lines):
        if _FOOTNOTES_MARKER.match(line):
            return entry_lines[:i]
    return entry_lines


def _split_letters(body_lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split body lines into (recipient, entry_lines) per letter.

    A natural documentary boundary defines a record (part 05 §5.2): for the
    letters, one "TO <recipient>." section (occasionally more than one
    physical letter to the same recipient, RECON.md §5's 136 datelines
    across 130 letters). Content before the first heading - Sanborn's
    Introduction and the remaining front matter - is not part of any letter
    and is discarded.
    """
    heading_indices = [
        i for i, line in enumerate(body_lines) if _LETTER_HEADING_RE.match(line)
    ]
    entries = []
    for position, start in enumerate(heading_indices):
        end = (
            heading_indices[position + 1]
            if position + 1 < len(heading_indices)
            else len(body_lines)
        )
        entry_lines = _trim_trailing_footnotes(body_lines[start:end])
        recipient = entry_lines[0][len("TO ") :]
        entries.append((recipient, entry_lines))
    return entries


def _raw_paragraphs(lines: list[str]) -> list[str]:
    """Blank-line-delimited paragraphs, unstripped - preserves each line's
    original indentation so ``_is_indented_paragraph`` can tell a letter's
    indented dateline/signature apart from its unindented body prose.
    """
    text = "\n".join(lines).strip("\n")
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _is_indented_paragraph(paragraph: str) -> bool:
    return all(
        line[:1].isspace() for line in paragraph.splitlines() if line.strip()
    )


# A whole-paragraph editorial annotation - Sanborn's own bracketed or
# parenthetical asides ("[The first of many letters.]", "(Written as from
# one Indian to another.)") rather than Thoreau's dateline or salutation.
# Neither dateline nor salutation extraction may treat one of these as the
# letter's own opening content (review round 1 on PR #52: an unskipped
# "[The first of many letters.]" was wrongly read as a salutation).
_EDITORIAL_ANNOTATION_RE = re.compile(r"^[(\[].*[)\]]\.?$", re.DOTALL)


def _is_editorial_annotation(paragraph: str) -> bool:
    return bool(_EDITORIAL_ANNOTATION_RE.match(paragraph.strip()))


def _extract_dateline(entry_lines: list[str]) -> str:
    """The letter's dateline: the first substantive paragraph after the
    heading - skipping any leading editorial annotation - if and only if
    it is indented, e.g. "     CONCORD, October 27, 1837." Unlike the
    journals' date headings, letter datelines already carry a full
    explicit date (RECON.md §5) - still landing here verbatim, since
    parsing it into a resolved year is the later year-resolution slice,
    not this one.

    Bounded to that one paragraph rather than scanning the whole letter
    (review round 1 on PR #52's blocking defect): a letter can have no
    dateline at all (SRC-000129, a follow-up note with no dateline before
    "FRIEND HECKER,--"), and scanning further would find its closing
    signature block - itself indented - and wrongly report that as the
    dateline. A letter with no dateline gets an empty string, not an
    invented one.
    """
    for paragraph in _raw_paragraphs(entry_lines[1:]):
        if _is_editorial_annotation(paragraph):
            continue
        if _is_indented_paragraph(paragraph):
            return " ".join(
                line.strip() for line in paragraph.splitlines() if line.strip()
            )
        return ""
    return ""


# The opening address, up to and including its trailing "--"
# ("DEAR HELEN,--", "MR. BLAKE,--", "MY DEAR FRIEND,--"). Matched
# generically on punctuation rather than a fixed vocabulary, since the
# corpus's salutations vary widely (RECON.md §5 examples plus "MR. X,--",
# "FRIEND X,--", "MY FRIEND X,--", even Latin "CARA SOROR,--"). An optional
# footnote marker may sit between the comma and the dashes (SRC-000092,
# "MR. WILEY,[75]--").
_SALUTATION_RE = re.compile(r"^(.*?,(?:\[\d+\])?--)")

# A letter's dateline already carries its own explicit year as text (issue
# #6), unlike the journals' headings - no chapter to infer from and no
# weekday checksum to run, the year is simply stated. A plain 4-digit scan
# is enough to parse it out; two real letters have a dateline with no
# parseable year at all (SRC-000024, "CASTLETON, STATEN ISLAND, May 23.",
# and SRC-000007, whose year is spelled in Roman numerals, "A. D.
# MDCCCXL.") and stay `unresolved` rather than guessed. No dateline in the
# real corpus carries more than one 4-digit number, so there is no
# ambiguity between candidates to resolve.
_LETTER_DATELINE_YEAR_RE = re.compile(r"\b\d{4}\b")


def _letter_date_confidence(dateline: str) -> str:
    """`unresolved` for an absent or unparseable dateline; `inferred`
    otherwise - the same value the journals give a heading that already
    states its own year (docs/normalized-record-schema.md), since a
    letter's dateline has no weekday to independently confirm the year
    against a calendar either.
    """
    return "inferred" if _LETTER_DATELINE_YEAR_RE.search(dateline) else "unresolved"


def _extract_salutation(entry_lines: list[str]) -> str:
    """The letter's salutation: extracted from the first unindented,
    non-annotation paragraph after the dateline (the body's opening
    paragraph), which the body itself keeps in full - this is a
    non-destructive read of it, not a split. A second or third letter
    bundled under one recipient heading sometimes continues without a
    fresh greeting (SRC-000045, SRC-000049, SRC-000050, SRC-000129 in the
    real corpus): that paragraph's opening prose is not a salutation, so
    a letter with none gets an empty string rather than an invented one
    (issue #58, the same shape-not-presence remedy #52 applied to
    `dateline`).
    """
    for paragraph in _raw_paragraphs(entry_lines[1:]):
        if _is_editorial_annotation(paragraph) or _is_indented_paragraph(paragraph):
            continue
        first_line = paragraph.splitlines()[0].strip()
        match = _SALUTATION_RE.match(first_line)
        return match.group(1) if match else ""
    return ""


def normalize_letters(
    evidence_root: Path, start_id: int = 1
) -> list[NormalizedRecord]:
    """Normalize the Familiar Letters volume into per-letter records.

    ``start_id`` continues the ``SRC-`` sequence after the journals' 558
    records (part 05 §4: IDs assigned sequentially, volume order then entry
    order) - callers combining both source types pass
    ``start_id=len(journal_records) + 1``; the default of 1 is for
    normalizing letters on their own (tests, or a corpus with no journals).
    """
    evidence_root = Path(evidence_root)
    raw_path = evidence_root / LETTERS_VOLUME["raw_path"]
    raw_text = raw_path.read_text(encoding="utf-8")
    body_lines = _extract_body_lines(
        raw_text, back_matter_marker=_GENERAL_INDEX_MARKER
    )
    records: list[NormalizedRecord] = []
    counter = start_id
    for recipient, entry_lines in _split_letters(body_lines):
        paragraphs = [
            normalize_quotes(p) for p in _paragraphs(entry_lines[1:])
        ]
        dateline = _extract_dateline(entry_lines)
        salutation = _extract_salutation(entry_lines)
        src_id = f"SRC-{counter:06d}"
        counter += 1
        records.append(
            NormalizedRecord(
                id=src_id,
                source_type=LETTERS_VOLUME["source_type"],
                # The dateline already carries its own year as text
                # (issue #57), so event_date lands identical to
                # recorded_date either way - unlike the journals, there is
                # no separate resolved value to append.
                recorded_date=dateline,
                event_date=dateline,
                date_confidence=_letter_date_confidence(dateline),
                contemporaneous=True,
                original_file=LETTERS_VOLUME["raw_path"],
                original_locator=(
                    f"{LETTERS_VOLUME['volume_label']}, letter to {recipient}"
                ),
                paragraphs=paragraphs,
                recipient=recipient,
                dateline=dateline,
                salutation=salutation,
            )
        )
    return records


def _split_chapters(
    body_lines: list[str], chapters: list[str]
) -> list[tuple[str, list[str]]]:
    """Split a book's body lines into (chapter_title, chapter_lines).

    Headings are matched **in document order** against ``chapters``: a line
    is the next chapter's heading only if, stripped of trailing whitespace,
    it equals the next title still expected and is flush left. Ordering is
    what makes the closed set safe - a title that also appears in the
    volume's own Contents block or on its title page is passed over,
    because at that point in the file the expected title is a different one.

    Everything before the first chapter heading - title page, Contents,
    epigraphs - is front matter and is discarded, the same way
    ``_split_entries`` discards everything before the first date heading.
    """
    remaining = list(chapters)
    starts: list[tuple[str, int]] = []
    for i, line in enumerate(body_lines):
        if not remaining:
            break
        if line.rstrip() == remaining[0]:
            starts.append((remaining.pop(0), i))
    if remaining:
        raise ValueError(f"chapter headings not found in order: {remaining}")

    bounds = [i for _, i in starts] + [len(body_lines)]
    return [
        (title, body_lines[start + 1 : bounds[n + 1]])
        for n, (title, start) in enumerate(starts)
    ]


def normalize_targets(
    evidence_root: Path, start_id: int = 1
) -> list[NormalizedRecord]:
    """Normalize the two audit-target books into per-chapter records.

    ``start_id`` continues the ``SRC-`` sequence after the journals' and
    letters' records, the same convention ``normalize_letters`` uses, so
    adding the books moves no ID that already exists.

    These are **not** contemporaneous evidence (part 05 §6): A Week (1849)
    and Walden (1854) are published works Thoreau built *from* the journals,
    which is exactly the relation the cross-references label and the
    benchmark scores. Marking them ``contemporaneous: false`` is what keeps
    a date-leakage test able to tell the two sides apart.
    """
    evidence_root = Path(evidence_root)
    records: list[NormalizedRecord] = []
    counter = start_id
    for volume in TARGET_VOLUMES:
        raw_path = evidence_root / volume["raw_path"]
        raw_text = raw_path.read_text(encoding="utf-8")
        # No back-matter cut: these files end at the Gutenberg END marker
        # with nothing between it and the last chapter but the trailing
        # licence, which _extract_body_lines already excludes. Walden's
        # "THE END" is *not* usable as the marker - it sits before Civil
        # Disobedience, not after it - so it is dropped per paragraph below.
        body_lines = _extract_body_lines(raw_text, back_matter_marker=_NEVER_RE)
        for title, chapter_lines in _split_chapters(body_lines, volume["chapters"]):
            paragraphs = [
                normalize_quotes(p)
                for p in _paragraphs(chapter_lines)
                if not _THE_END_RE.match(p)
            ]
            src_id = f"SRC-{counter:06d}"
            counter += 1
            records.append(
                NormalizedRecord(
                    id=src_id,
                    source_type=volume["source_type"],
                    # A book has no date heading to quote. Its date is the
                    # year of publication - a documentary fact about the
                    # volume, not a date resolved out of the text - which
                    # is what date_confidence: published records.
                    recorded_date="",
                    event_date=volume["published_year"],
                    date_confidence="published",
                    contemporaneous=False,
                    original_file=volume["raw_path"],
                    original_locator=(
                        f"{volume['volume_label']}, chapter \"{title}\""
                    ),
                    paragraphs=paragraphs,
                    work=volume["work"],
                    chapter=title,
                )
            )
    return records


def recipients_table(records: list[NormalizedRecord]) -> dict[str, list[str]]:
    """Map each verbatim recipient string to the SRC- IDs of the letters
    naming them (issue #6: "a real, checkable table ... not a list in a
    comment"). Recipient strings are never merged - Emerson's four location
    forms are four distinct keys (RECON.md §5, §6).
    """
    table: dict[str, list[str]] = {}
    for record in records:
        if record.recipient is None:
            continue
        table.setdefault(record.recipient, []).append(record.id)
    return dict(sorted(table.items()))


def write_recipients_table(table: dict[str, list[str]], output_path: Path) -> Path:
    """Write the recipients table as YAML to ``output_path``."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(table, sort_keys=True), encoding="utf-8")
    return output_path


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
    # Letter-specific fields (issue #6): included only when set, so
    # journal records' frontmatter is unchanged from issue #3.
    if record.recipient is not None:
        frontmatter["recipient"] = record.recipient
    if record.dateline is not None:
        frontmatter["dateline"] = record.dateline
    if record.salutation is not None:
        frontmatter["salutation"] = record.salutation
    # Book-specific fields (issue #9), same "only when set" rule.
    if record.work is not None:
        frontmatter["work"] = record.work
    if record.chapter is not None:
        frontmatter["chapter"] = record.chapter
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
