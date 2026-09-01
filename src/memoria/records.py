"""The normalized record: its shape, and how it is written to disk.

The on-disk record format, owned in one place
(``docs/adr/0004-the-read-side-is-functions-over-a-repository-value.md``).
This module carries the **write** direction — the dataclass, the stable
anchor contract, and the Markdown serializer. The read direction is #11's.

Nothing here is corpus-specific, which is why it survived the retirement of
the Thoreau proof-of-concept corpus (``docs/open-problems.md`` §2.4). The
normalizer that used to produce these records was written for that corpus
and went with it; **no normalizer exists today**. What remains is the
contract a future one must satisfy, specified in
``docs/normalized-record-schema.md`` and read by ``memoria.index`` and
``memoria.validate``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Where normalized records live inside the book repository. Here rather than
# in validate.py so that the module owning the record format owns the path to
# it too - validate.py and index.py both read records, and neither should be
# the other's source for where they are (ADR-0004).
NORMALIZED_RELATIVE_PATH = "sources/normalized"


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
    # Letter-specific structured fields. None for records that are not
    # letters; always set for letter records.
    recipient: str | None = None
    dateline: str | None = None
    salutation: str | None = None
    # Book-specific structured fields, for audit-target records. None
    # otherwise.
    work: str | None = None
    chapter: str | None = None

    def anchor_id(self, paragraph_number: int) -> str:
        """The stable anchor id for this record's Nth paragraph (1-based).

        The single source of the citation contract: ``f"{record.id} P{n}"``
        in prose, ``record.anchor_id(n)`` as the ``#...`` fragment. Callers
        cite through this rather than re-deriving the string, so the form
        can only ever change in one place.
        """
        return f"{self.id.lower()}-p{paragraph_number}"


def record_to_markdown(record: NormalizedRecord) -> str:
    """Serialize one record to the on-disk Markdown form.

    Frontmatter, then a run of anchored paragraphs. The inverse of this
    function is the read direction (#11); the two together are what makes
    the format round-trippable rather than merely writable.
    """
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
    # Type-specific fields are included only when set, so a record that is
    # not a letter or a book carries no empty keys for fields that do not
    # apply to it.
    if record.recipient is not None:
        frontmatter["recipient"] = record.recipient
    if record.dateline is not None:
        frontmatter["dateline"] = record.dateline
    if record.salutation is not None:
        frontmatter["salutation"] = record.salutation
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
        path.write_text(record_to_markdown(record), encoding="utf-8")
        written.append(path)

    written_names = {path.name for path in written}
    for stale in output_root.glob("SRC-*.md"):
        if stale.name not in written_names:
            stale.unlink()

    return written
