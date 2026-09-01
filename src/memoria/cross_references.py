"""Cross-reference ground truth: which journal passage was reused in which
published work (issue #8).

The 1906 editors record this fact as a footnote: a journal paragraph carries
an inline numeric marker (``[40]``), and that footnote's *body*, parsed out
of the volume's back-matter FOOTNOTES section by
``memoria.editorial._parse_footnote_bodies``, is itself a bracketed citation
of the published work - e.g. ``[_Week_, p. 319; Riv. 395.]``. This module
does not re-scan the raw corpus: it reads the ``footnote``-type
``EditorialRecord``s ``extract_editorial_apparatus`` (issue #5) already
produced, since a footnote's ``linked_record_id``/``linked_anchor`` is
already the resolved journal-side anchor this issue's acceptance criteria
ask for.

Scope: the journal-side anchor only. Which passage of *Walden* or *A Week*
a reused passage became is adjudication work, explicitly out of scope
(issue #8's "What to build") - the target-side citation is stored verbatim,
never resolved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from memoria.editorial import EditorialRecord

CROSS_REFERENCES_RELATIVE_PATH = "sources/normalized/cross-references.yaml"

# The published works a cross-reference footnote cites (RECON.md §4(b)'s
# table, plus "Maine Woods" - a sixth cited work RECON's own table omits
# entirely, found by mechanical verification; see
# docs/cross-reference-schema.md). "Week" and "Walden" are held in the
# corpus (part 04's downloaded targets); the rest are not.
HELD_WORKS = frozenset({"Week", "Walden"})
UNHELD_WORKS = frozenset({"Excursions", "Cape Cod", "The Service", "Maine Woods"})
KNOWN_WORKS = HELD_WORKS | UNHELD_WORKS

# A footnote body is a cross-reference only if it carries an actual page
# citation - "p. 106; Riv. 118" - not merely a passing mention of a work's
# title (e.g. "though _Walden_ has 'great.'", a textual-variant note with
# no page reference at all, and so nothing to look anything up by).
_CITATION_GATE_RE = re.compile(r"pp?\.\s*\d|Riv\.\s*\d")

# A cited work's title, italicized (``_Week_``) or not (a handful of
# footnotes cite "Week" without its italic markup - a transcription
# inconsistency in the source, not a different citation form) - matched on
# non-letter boundaries rather than ``\b``, since ``\b`` does not fire
# between a title and its surrounding "_" (regex treats "_" as a word
# character). One footnote can cite more than one work (a passage reused in
# both _Week_ and _The Service_) - each cited work is its own
# cross-reference, since each names a distinct journal-passage-to-book
# link, the ground truth this table exists to hold.
_WORK_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(w) for w in sorted(KNOWN_WORKS)) + r")(?![A-Za-z])"
)


@dataclass
class CrossReference:
    source_record_id: str
    source_anchor: str
    target_work: str
    resolvable: bool
    citation: str


def extract_cross_references(
    editorial_records: list[EditorialRecord],
) -> list[CrossReference]:
    """Pull the published-work cross-references out of ``editorial_records``
    (issue #5's footnote records).

    A footnote whose marker fell outside this slice's covered entries
    (``linked_record_id is None`` - Torrey's Introduction, or J02's Chapter
    I heading line, both apparatus rather than any record's evidence; see
    docs/editorial-record-schema.md's "Known gaps") is skipped: this
    issue's acceptance criteria require every cross-reference to carry a
    resolved journal-side ``SRC-`` ID and anchor, and there is no
    normalized record to point one at.
    """
    cross_references: list[CrossReference] = []
    for record in editorial_records:
        if record.editorial_type != "footnote":
            continue
        if not _CITATION_GATE_RE.search(record.text):
            continue
        if record.linked_record_id is None:
            continue
        works = sorted(set(_WORK_RE.findall(record.text)))
        for work in works:
            cross_references.append(
                CrossReference(
                    source_record_id=record.linked_record_id,
                    source_anchor=record.linked_anchor,
                    target_work=work,
                    resolvable=work in HELD_WORKS,
                    citation=record.text,
                )
            )
    cross_references.sort(
        key=lambda c: (c.source_record_id, c.source_anchor, c.target_work)
    )
    return cross_references


def write_cross_references_table(
    cross_references: list[CrossReference], output_path: Path
) -> Path:
    """Write the cross-reference table as YAML to ``output_path`` - "a real,
    checkable table ... readable without Memoria software" (issue #8), the
    same durable-artifact treatment issue #6 gives ``recipients.yaml``.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "source_record_id": c.source_record_id,
            "source_anchor": c.source_anchor,
            "target_work": c.target_work,
            "resolvable": c.resolvable,
            "citation": c.citation,
        }
        for c in cross_references
    ]
    output_path.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    return output_path
