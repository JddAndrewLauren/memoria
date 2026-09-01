"""``memoria normalize``: the skip-unchanged normalization run (part 05 §5.4).

Reads the evidence root, appends newly-discovered raw units to the manifest
ledger (``memoria.manifest``, ADR-0006), and converts a unit only when the
manifest's hash for it, or the pinned version of the converter that would
handle it, differs from what the existing record's ``raw_sha256`` /
``converter`` frontmatter says (``docs/normalized-record-schema.md``). The
record is the state; there is no second store of what was converted when.

**The converter seam.** ``CONVERTERS`` maps a raw file's suffix to a
``Converter`` - a plain function from raw bytes to a ``ConversionDraft``.
This issue registers a plain-text converter only; #77 and #78 register docx
/ pdf and email converters here without otherwise touching this module. A
raw unit whose suffix has no registered converter is left in the ledger -
its ID is still allocated - but produces no record yet, the same way a
future stub-record format will.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from memoria.manifest import DEFAULT_MANIFEST_RELATIVE_PATH, save_manifest, sync
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    ReadError,
    parse_record,
    record_to_markdown,
)
from memoria.repository import Repository


@dataclass(frozen=True)
class ConversionDraft:
    """What a converter contributes; the loop fills in the ID and manifest
    provenance fields (``id``, ``original_file``, ``raw_sha256``,
    ``converter``) that are not the converter's to decide."""

    source_type: str
    recorded_date: str
    event_date: str
    date_confidence: str
    contemporaneous: bool
    original_locator: str
    paragraphs: list[str]


Converter = Callable[[bytes], ConversionDraft]

# Blank-line paragraph boundaries, same rule the record schema documents for
# splitting a normalized record's body (docs/normalized-record-schema.md).
_BLANK_LINE = re.compile(r"\n[ \t]*\n+")


def convert_plain_text(raw_bytes: bytes) -> ConversionDraft:
    """The plain-text converter this issue ships.

    No metadata to read from a bare text file: date fields are left empty
    with ``date_confidence: unresolved`` per the schema's "no invented date"
    rule, and paragraphs are split on blank lines with no reflow -
    whitespace policy applies to every converter alike, not only the richer
    ones #77/#78 add.
    """
    text = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    paragraphs = [p.strip("\n") for p in _BLANK_LINE.split(text) if p.strip()]
    return ConversionDraft(
        source_type="document",
        recorded_date="",
        event_date="",
        date_confidence="unresolved",
        contemporaneous=True,
        original_locator="(whole file)",
        paragraphs=paragraphs,
    )


# suffix -> (converter, pinned version string written to the record's
# `converter` field). The version is part of the pin: a future bump to this
# converter's behaviour changes the string, which is what makes "a changed
# converter version reconverts exactly that unit" possible without a code
# diff also being required to trigger it.
CONVERTERS: dict[str, tuple[Converter, str]] = {
    ".txt": (convert_plain_text, "plain-text 1"),
}


@dataclass
class NormalizeReport:
    added_units: list[str]
    converted: list[str]
    skipped: list[str]
    unconvertible: list[str]


def normalize(
    repository: Repository,
    evidence_root: Path,
    *,
    all: bool = False,
    manifest_relative_path: str = DEFAULT_MANIFEST_RELATIVE_PATH,
) -> NormalizeReport:
    """Run one normalization pass.

    ``all=True`` forces every convertible unit to reconvert, regardless of
    whether its hash or converter version changed.
    """
    evidence_root = Path(evidence_root)
    manifest_path = evidence_root / manifest_relative_path
    entries, added = sync(evidence_root, manifest_relative_path)
    save_manifest(manifest_path, entries)

    output_root = repository.root / NORMALIZED_RELATIVE_PATH

    converted = []
    skipped = []
    unconvertible = []
    for entry in entries:
        if entry.deleted:
            continue
        registration = CONVERTERS.get(Path(entry.path).suffix)
        if registration is None:
            unconvertible.append(entry.id)
            continue
        converter, pinned_version = registration

        record_path = output_root / f"{entry.id}.md"
        if not all and record_path.is_file():
            existing = _try_parse(record_path)
            if (
                existing is not None
                and existing.raw_sha256 == entry.sha256
                and existing.converter == pinned_version
            ):
                skipped.append(entry.id)
                continue

        raw_bytes = (evidence_root / entry.path).read_bytes()
        draft = converter(raw_bytes)
        record = NormalizedRecord(
            id=entry.id,
            source_type=draft.source_type,
            recorded_date=draft.recorded_date,
            event_date=draft.event_date,
            date_confidence=draft.date_confidence,
            contemporaneous=draft.contemporaneous,
            original_file=entry.path,
            original_locator=draft.original_locator,
            raw_sha256=entry.sha256,
            converter=pinned_version,
            paragraphs=draft.paragraphs,
        )
        output_root.mkdir(parents=True, exist_ok=True)
        record_path.write_text(record_to_markdown(record), encoding="utf-8")
        converted.append(entry.id)

    return NormalizeReport(
        added_units=added,
        converted=converted,
        skipped=skipped,
        unconvertible=unconvertible,
    )


def _try_parse(record_path: Path) -> NormalizedRecord | None:
    """A record that fails to parse is treated as needing reconversion
    rather than crashing the run - a hand-corrupted file should not block
    every other unit."""
    try:
        return parse_record(record_path.read_text(encoding="utf-8"), source=record_path.name)
    except ReadError:
        return None
