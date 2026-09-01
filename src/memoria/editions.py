"""Locate a cited page of a reference edition in the held Gutenberg text.

The journals' cross-reference footnotes cite pages of two editions the
corpus does not hold (``[_Week_, p. 319; Riv. 395.]``): the 1906 Manuscript
Edition and the 1894 Riverside Edition. ``RECON.md`` §4 read that as
unresolvable - "resolving them to a location in our Walden/Week text
requires fuzzy text matching, not a page-number join".

That is true of the texts held and false as a statement about the world.
The journals themselves are **volumes VII and VIII of 20** of the Manuscript
Edition, so ``p. 319`` is a page of volume 1 of the same set - and both
sets are digitized page by page. This module turns a cited page number into
a position in the held text, which is a lookup plus an alignment between two
printings of one book, not a paraphrase judgement.

**Nothing here may use Memoria's retrieval.** No FTS5, no index, no
gathered set, no model - see ``docs/answer-key-protocol.md``. The whole
point of the answer key is that it is not produced by the machinery it is
used to score.
"""

from __future__ import annotations

import bisect
import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from memoria.normalize import NormalizedRecord

REFERENCE_RELATIVE_PATH = "raw/archive-org"

# The four scanned volumes, two per held work: the edition whose page the
# footnote's `p.` cites, and the edition whose page its `Riv.` cites. Two
# independent scans of two independent printings are what makes a
# cross-check possible at all - see answer_key.py's admission rule.
REFERENCE_EDITIONS = [
    {
        "identifier": "writingsofhenryd01thor",
        "work": "Week",
        "series": "manuscript",
        "label": "The Writings of Henry David Thoreau (Manuscript Edition, 1906), vol. 1",
    },
    {
        "identifier": "writingsofhenryd01thor_1",
        "work": "Week",
        "series": "riverside",
        "label": "The Writings of Henry David Thoreau (Riverside Edition, 1894), vol. 1",
    },
    {
        "identifier": "writingsofhenryd02thoruoft",
        "work": "Walden",
        "series": "manuscript",
        "label": "The Writings of Henry David Thoreau (Manuscript Edition, 1906), vol. 2",
    },
    {
        "identifier": "writingsofhenryd02thor_0",
        "work": "Walden",
        "series": "riverside",
        "label": "The Writings of Henry David Thoreau (Riverside Edition, 1894), vol. 2",
    },
]

# An n-gram this long, occurring at most this many times in the held work,
# is distinctive enough to vote on where a scanned page sits. Both numbers
# are deliberately blunt: the two texts are two printings of one book, so
# agreement is near-verbatim and the alignment is not a close call.
_NGRAM = 5
_MAX_OCCURRENCES = 3
# A page anchored on fewer than this many voting n-grams is not trusted.
# Real pages score 60-160; the ones that fall short are plates, blank
# leaves, and front matter, which have no counterpart in the held text.
_MIN_VOTES = 15

# OCR breaks a word across a line ("re- nounced") and the searchtext keeps
# the break as a hyphen followed by whitespace. Rejoining before tokenizing
# is what lets those words vote.
_HYPHEN_BREAK_RE = re.compile(r"-\s+")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")

# Every page of these volumes carries a running head - the chapter title
# and the page's own printed number, "SUNDAY 53" or "46 WALDEN". Read back
# out of the OCR, it is the page telling you what page it is, and it is the
# only check on the scanner's own page numbering that does not go through
# the alignment. It is needed: three of the four volumes number their
# leaves one ahead of what is printed on them, and one does not.
#
# A closed set of titles again, and for the same reason as everywhere else
# here - a bare "number next to capitals" rule matches body text.
_RUNNING_HEAD_TITLES = (
    r"CONCORD RIVER|SATURDAY|SUNDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY"
    r"|A WEEK ON THE CONCORD|WALDEN|ECONOMY|READING|SOUNDS|SOLITUDE|VISITORS"
    r"|THE BEAN-FIELD|THE VILLAGE|THE PONDS|BAKER FARM|HIGHER LAWS"
    r"|BRUTE NEIGHBORS|HOUSE-WARMING|WINTER ANIMALS|SPRING|CONCLUSION"
    r"|CIVIL DISOBEDIENCE"
)
_RUNNING_HEAD_RE = re.compile(
    r"(?:(\d{1,3})\s+(?:" + _RUNNING_HEAD_TITLES + r")"
    r"|(?:" + _RUNNING_HEAD_TITLES + r")\s+(\d{1,3}))"
)
# How many pages must state their own number, and how strongly they must
# agree, before the offset they imply is trusted.
_MIN_HEAD_VOTES = 20
_MIN_HEAD_AGREEMENT = 0.9


def tokenize(text: str) -> list[str]:
    """Casefolded alphanumeric tokens, with OCR hyphen-breaks rejoined.

    The one normalization both sides of every comparison go through: a
    1906 scan's OCR and a Distributed Proofreaders transcription differ in
    punctuation, quote convention, capitalization and line breaking, and
    agree on words.
    """
    return _NON_WORD_RE.sub(" ", _HYPHEN_BREAK_RE.sub("", text).lower()).split()


@dataclass
class ReferenceVolume:
    """One scanned volume, keyed by the page number printed on the page.

    ``offset`` is what had to be added to the scanner's own leaf numbering
    to get there, and ``agreeing``/``voting`` are how many pages voted for
    it - all three are written into the answer key, because an offset
    applied silently is an offset nobody can check.
    """

    identifier: str
    pages: dict[int, str]
    offset: int
    agreeing: int
    voting: int


def detect_printed_page_offset(pages: dict[int, str]) -> tuple[int, int, int]:
    """Read the running heads and report ``(offset, agreeing, voting)``.

    Only offsets of a single page either way are considered: the question
    is whether the scanner's numbering is aligned with the print, not where
    an arbitrary number in the body text happens to sit.
    """
    votes: Counter[int] = Counter()
    for page, text in pages.items():
        flat = " ".join(text.split())
        for match in _RUNNING_HEAD_RE.finditer(flat):
            printed = int(match.group(1) or match.group(2))
            if abs(printed - page) <= 1:
                votes[printed - page] += 1
                break
    if not votes:
        return 0, 0, 0
    offset, agreeing = votes.most_common(1)[0]
    return offset, agreeing, sum(votes.values())


def read_reference_volume(evidence_root: Path, identifier: str) -> ReferenceVolume:
    """Return one scanned volume keyed by **printed** page number.

    Three files per volume, byte-for-byte as the Internet Archive serves
    them: ``_page_numbers.json`` maps a leaf to the page number printed on
    it, ``_hocr_pageindex.json`` gives each leaf's byte range within
    ``_hocr_searchtext.txt``, and that file holds the text. (The
    ``_djvu.txt`` full text carries no page delimiters at all, which is why
    it is not the file used.)

    Where two leaves carry the same printed number - it happens in front
    matter - the first wins.

    A page whose printed number the scanner never read is simply absent,
    and a citation to it ends up ``unanchored`` in the answer key. Filling
    such gaps by arithmetic was tried and dropped: every gap in all four
    volumes has plate leaves interleaved (six leaves spanning two page
    numbers, eight spanning four), so leaf count never matches page count
    and there is nothing safe to interpolate from. Twelve cited pages are
    lost this way, and that is reported as coverage rather than guessed at.

    **The scanner's numbering is not the print's.** Three of these four
    volumes label each leaf one page ahead of the number printed on it and
    the fourth does not, so the offset is measured per volume from the
    running heads rather than assumed. Nothing else catches this: a
    constant offset shifts every citation of a volume equally, which the
    answer key's two-edition check absorbs into its drift fit and reports
    as agreement. It was found by reading one sampled row by eye.
    """
    root = Path(evidence_root) / REFERENCE_RELATIVE_PATH
    page_numbers = json.loads(
        (root / f"{identifier}_page_numbers.json").read_text(encoding="utf-8")
    )
    with gzip.open(root / f"{identifier}_hocr_pageindex.json.gz", "rt") as handle:
        page_index = json.load(handle)
    with gzip.open(root / f"{identifier}_hocr_searchtext.txt.gz", "rb") as handle:
        searchtext = handle.read()

    leaves: dict[int, str] = {}
    for page in page_numbers["pages"]:
        printed = str(page["pageNumber"]).strip()
        if not printed.isdigit():
            continue
        number = int(printed)
        if number in leaves:
            continue
        start, end = page_index[page["leafNum"] - 1][:2]
        leaves[number] = searchtext[start:end].decode("utf-8", "replace")

    offset, agreeing, voting = detect_printed_page_offset(leaves)
    if voting < _MIN_HEAD_VOTES or agreeing < _MIN_HEAD_AGREEMENT * voting:
        raise ValueError(
            f"{identifier}: cannot establish the printed-page offset - "
            f"{agreeing} of {voting} pages agree on {offset:+d}. Every page "
            "citation into this volume would be unverifiable."
        )
    return ReferenceVolume(
        identifier=identifier,
        pages={number + offset: text for number, text in leaves.items()},
        offset=offset,
        agreeing=agreeing,
        voting=voting,
    )


@dataclass
class ParagraphSpan:
    """Where one normalized paragraph sits in a work's token stream."""

    record_id: str
    paragraph_number: int
    start: int
    end: int


@dataclass
class WorkText:
    """A held work as one token stream, with paragraph boundaries kept.

    Cross-work concatenation is deliberately not done: a page of *Walden*
    is only ever looked for in *Walden*.
    """

    tokens: list[str]
    spans: list[ParagraphSpan]
    _index: dict[tuple[str, ...], list[int]] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records: list[NormalizedRecord]) -> WorkText:
        tokens: list[str] = []
        spans: list[ParagraphSpan] = []
        for record in records:
            for number, paragraph in enumerate(record.paragraphs, start=1):
                start = len(tokens)
                tokens.extend(tokenize(paragraph))
                spans.append(
                    ParagraphSpan(record.id, number, start, len(tokens))
                )
        work = cls(tokens=tokens, spans=spans)
        for i in range(len(tokens) - _NGRAM + 1):
            work._index.setdefault(tuple(tokens[i : i + _NGRAM]), []).append(i)
        return work

    def anchor(self, page_text: str) -> tuple[int | None, int, int]:
        """Find where ``page_text`` sits in this work's token stream.

        Every distinctive n-gram of the page votes for one alignment
        offset; the winner is taken. Voting rather than a single best match
        is what makes the result survive OCR damage - a page needs only a
        fraction of its n-grams to survive intact.

        Returns ``(token offset, votes, page token count)``.
        """
        page_tokens = tokenize(page_text)
        votes: Counter[int] = Counter()
        for j in range(len(page_tokens) - _NGRAM + 1):
            positions = self._index.get(tuple(page_tokens[j : j + _NGRAM]))
            if positions and len(positions) <= _MAX_OCCURRENCES:
                for position in positions:
                    votes[position - j] += 1
        if not votes:
            return None, 0, len(page_tokens)
        offset, count = votes.most_common(1)[0]
        return offset, count, len(page_tokens)

    def paragraphs_overlapping(self, start: int, end: int) -> list[ParagraphSpan]:
        return [s for s in self.spans if s.start < end and s.end > start]


@dataclass
class PageMap:
    """Every printed page of one scanned volume, placed in the held work.

    Built over *all* the volume's pages rather than only the cited ones,
    which is what makes the check below possible: page numbers ascend, so
    the token offsets they map to must ascend too. A page that breaks the
    order was mis-anchored, and is dropped rather than trusted.
    """

    identifier: str
    work: str
    series: str
    printed_page_offset: int
    printed_page_offset_agreeing: int
    printed_page_offset_voting: int
    offsets: dict[int, int]
    votes: dict[int, int]
    lengths: dict[int, int]
    unanchored: list[int]
    non_monotonic: list[int]

    @property
    def pages(self) -> list[int]:
        return sorted(self.offsets)

    def span(self, page: int) -> tuple[int, int] | None:
        """The token range of one page: from its own offset to the next
        anchored page's, falling back to the page's own token count for the
        last page in the volume."""
        if page not in self.offsets:
            return None
        start = self.offsets[page]
        following = [p for p in self.pages if p > page]
        end = (
            self.offsets[following[0]]
            if following
            else start + self.lengths[page]
        )
        return start, max(end, start + 1)

    def page_containing(self, token: int) -> int | None:
        """The printed page whose span covers ``token``."""
        pages = self.pages
        if not pages:
            return None
        starts = [self.offsets[p] for p in pages]
        return pages[max(bisect.bisect_right(starts, token) - 1, 0)]


def build_page_map(
    evidence_root: Path, edition: dict, work_text: WorkText
) -> PageMap:
    """Anchor every printed page of one scanned volume into the held work."""
    volume = read_reference_volume(evidence_root, edition["identifier"])
    pages = volume.pages
    offsets: dict[int, int] = {}
    votes: dict[int, int] = {}
    lengths: dict[int, int] = {}
    unanchored: list[int] = []
    for page in sorted(pages):
        offset, count, length = work_text.anchor(pages[page])
        if offset is None or count < _MIN_VOTES:
            unanchored.append(page)
            continue
        offsets[page] = offset
        votes[page] = count
        lengths[page] = length

    non_monotonic: list[int] = []
    previous = -1
    for page in sorted(offsets):
        if offsets[page] < previous:
            non_monotonic.append(page)
        else:
            previous = offsets[page]
    for page in non_monotonic:
        del offsets[page], votes[page], lengths[page]

    return PageMap(
        identifier=edition["identifier"],
        work=edition["work"],
        series=edition["series"],
        printed_page_offset=volume.offset,
        printed_page_offset_agreeing=volume.agreeing,
        printed_page_offset_voting=volume.voting,
        offsets=offsets,
        votes=votes,
        lengths=lengths,
        unanchored=unanchored,
        non_monotonic=non_monotonic,
    )
