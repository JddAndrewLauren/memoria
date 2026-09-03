"""The normalized record: its shape, and how it is written to disk.

The on-disk record format, owned in one place
(``docs/adr/0004-the-read-side-is-functions-over-a-repository-value.md``).
This module carries **both directions** — the dataclass, the stable anchor
contract, the Markdown serializer, and the parser that is its exact inverse —
together with the composed read that ``read(ref)`` is (#11). Serializing and
parsing live in one module because they are one contract: a change to either
that the other does not match is a corruption, and
``record_to_markdown(parse_record(text)) == text`` is the test that says so.

Nothing here is corpus-specific, which is why it survived the retirement of
the Thoreau proof-of-concept corpus (``docs/open-problems.md`` §2.4). The
normalizer that used to produce these records was written for that corpus
and went with it; **no normalizer exists today**. What remains is the
contract a future one must satisfy, specified in
``docs/normalized-record-schema.md`` and read by ``memoria.index`` and
``memoria.validate``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import yaml

from memoria import (
    changes,
    context_manifest,
    manuscript,
    record_extractor,
    references,
    sessions,
    subjects,
)
from memoria.repository import Repository, require_evidence_root

if TYPE_CHECKING:
    # Deferred to a function-local import in ``read`` below: ``memoria.index``
    # imports this module at the top level (for ``NormalizedRecord`` and
    # ``real_paragraphs``), so importing it back here too would cycle. The
    # same shape ``memoria.index`` already uses for its own reverse import
    # of ``memoria.extraction``.
    from memoria.index import ReadOverlay

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
    # The raw unit's hash, and the converter (name + pinned version) that
    # produced this body, both as the manifest ledger recorded them at
    # conversion time (ADR-0006, part 05 §5.4). A normalization run compares
    # these to the manifest to decide whether to reconvert. Default "" so
    # every existing construction of a record - most of them predating the
    # ledger - keeps working; a real normalizer always sets both.
    raw_sha256: str = ""
    converter: str = ""
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
    # Email-specific fields (#78). None for records that are not one message
    # inside an email export; always set for those. `email_from`/`email_to`/
    # `email_cc` rather than `from`/`to`/`cc`: `from` is a reserved word and
    # cannot be a dataclass field, so the frontmatter key and the attribute
    # name part ways here (record_to_markdown/parse_record map between them).
    thread_id: str | None = None
    subject: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    email_cc: str | None = None
    in_reply_to: str | None = None
    quoted_excised: bool | None = None
    attachments: list[dict] | None = None
    # docx-specific: embedded images by name, not embedded in the body
    # (part 05 §5.4). None for records that are not docx; always a list
    # (possibly empty) for docx records.
    images: list[str] | None = None

    def anchor_id(self, paragraph_number: int) -> str:
        """The stable anchor id for this record's Nth paragraph (1-based).

        The single source of the citation contract: ``f"{record.id} P{n}"``
        in prose, ``record.anchor_id(n)`` as the ``#...`` fragment. Callers
        cite through this rather than re-deriving the string, so the form
        can only ever change in one place.

        That one place is ``references.anchor``, which the parser reads
        through as well, so the write and read directions cannot drift.
        """
        return references.anchor(self.id, paragraph_number)


def record_to_markdown(record: NormalizedRecord) -> str:
    """Serialize one record to the on-disk Markdown form.

    Frontmatter, then a run of anchored paragraphs. The inverse of this
    function is the read direction (#11); the two together are what makes
    the format round-trippable rather than merely writable.

    **The format has no escaping**, so a paragraph containing the anchor
    sequence is refused here rather than written. Written, it would be
    indistinguishable from the separator: a paragraph holding
    ``\n\n<a id="src-000001-p2"></a>\n\n`` reads back as *two* paragraphs,
    re-serializes byte-identically, and so passes a round-trip check while
    every citation index after it is silently wrong. Refusing to write it is
    the only place that ambiguity can be caught with certainty, because by
    read time the two cases are the same bytes.

    **A pdf page marker earns no anchor** and is written between paragraphs
    verbatim, unnumbered (docs/normalized-record-schema.md, "pdf page
    markers are not paragraphs") - anchor numbers count real paragraphs
    only, so a marker inserted or removed shifts no anchor.
    """
    number = 0
    for paragraph in record.paragraphs:
        if is_page_marker(paragraph):
            continue
        number += 1
        if _ANCHOR_TAG.search(paragraph):
            raise ValueError(
                f"{record.id} ¶{number} contains a paragraph anchor, which the "
                "record format cannot represent - see "
                "docs/normalized-record-schema.md"
            )
    frontmatter = {
        "id": record.id,
        "source_type": record.source_type,
        "recorded_date": record.recorded_date,
        "event_date": record.event_date,
        "date_confidence": record.date_confidence,
        "contemporaneous": record.contemporaneous,
        "original_file": record.original_file,
        "original_locator": record.original_locator,
        "raw_sha256": record.raw_sha256,
        "converter": record.converter,
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
    if record.thread_id is not None:
        frontmatter["thread_id"] = record.thread_id
    if record.subject is not None:
        frontmatter["subject"] = record.subject
    if record.email_from is not None:
        frontmatter["from"] = record.email_from
    if record.email_to is not None:
        frontmatter["to"] = record.email_to
    if record.email_cc is not None:
        frontmatter["cc"] = record.email_cc
    if record.in_reply_to is not None:
        frontmatter["in_reply_to"] = record.in_reply_to
    if record.quoted_excised is not None:
        frontmatter["quoted_excised"] = record.quoted_excised
    if record.attachments is not None:
        frontmatter["attachments"] = record.attachments
    if record.images is not None:
        frontmatter["images"] = record.images
    # Paragraph anchors (part 05 §5.3): stable across re-runs because they
    # are positional within a record whose own ID is itself stable. A page
    # marker is written in place but is not itself anchored.
    blocks = []
    number = 0
    for paragraph in record.paragraphs:
        if is_page_marker(paragraph):
            blocks.append(paragraph)
            continue
        number += 1
        blocks.append(f'<a id="{record.anchor_id(number)}"></a>\n\n{paragraph}')
    body = "\n\n".join(blocks)
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


# --- the read direction (issue #11) ---------------------------------------

# The serializer writes an anchor, a blank line, the paragraph, and a blank
# line before the next anchor. The parser strips exactly those separators and
# nothing else: evidence text is sacred, and a blanket .strip() would eat a
# paragraph's own leading indentation and trailing structure (the whitespace
# policy in docs/normalized-record-schema.md).
_ANCHOR_TAG = re.compile(r'<a id="(?P<anchor>[^"]+)"></a>')

# A pdf page marker, written between pages by the pdf converter
# (docs/normalized-record-schema.md, "pdf page markers are not paragraphs").
_PAGE_MARKER = re.compile(r"^<!-- page \d+ -->$")

# Blank-line paragraph boundaries - the same rule that splits a converter's
# raw text into paragraphs (memoria.normalize) - used only to split a
# leading run of page markers, before the first anchor, from one another.
# It is never applied to a real paragraph's own text: a paragraph may
# contain its own internal blank line (AWKWARD in test_read_ref.py), so
# splitting on it there would corrupt evidence rather than recover a marker.
_BLANK_LINE = re.compile(r"\n[ \t]*\n+")

# A page marker recovered from the *end* of an anchor's segment only -
# where record_to_markdown always places one relative to the paragraph it
# follows - never by splitting the segment's own text.
_TRAILING_MARKER = re.compile(r"\n\n(<!-- page \d+ -->)$")


def is_page_marker(paragraph: str) -> bool:
    """Whether ``paragraph`` is a pdf page marker rather than a real one.

    A marker earns no anchor, no index row and no extraction read
    (docs/normalized-record-schema.md, "pdf page markers are not
    paragraphs"). Shared by the serializer, the parser and
    ``index.build_index`` so the rule is enforced identically everywhere a
    record's ``paragraphs`` list is walked.
    """
    return bool(_PAGE_MARKER.match(paragraph))


def real_paragraphs(record: NormalizedRecord) -> list[str]:
    """``record.paragraphs`` with page markers left out.

    What every anchor number, index row and extraction read is actually
    counted against - ``record.paragraphs`` itself is positional storage for
    ``record_to_markdown``, which needs the markers' original places.
    """
    return [p for p in record.paragraphs if not is_page_marker(p)]


_REQUIRED_FIELDS = (
    "id",
    "source_type",
    "recorded_date",
    "event_date",
    "date_confidence",
    "contemporaneous",
    "original_file",
    "original_locator",
    "raw_sha256",
    "converter",
)
_OPTIONAL_FIELDS = (
    "recipient", "dateline", "salutation", "work", "chapter",
    "thread_id", "subject", "in_reply_to", "images",
)
# Frontmatter keys whose attribute name differs (#78's email fields): `from`
# is a reserved word and cannot be a dataclass field / constructor kwarg.
_ALIASED_OPTIONAL_FIELDS = {"from": "email_from", "to": "email_to", "cc": "email_cc"}
# Non-scalar optional fields, handled outside the generic `_as_text` path:
# `quoted_excised` is a bool like `contemporaneous`, and `attachments` is a
# list of `{filename, type}` mappings the schema does not render as text.
_STRUCTURED_OPTIONAL_FIELDS = ("quoted_excised", "attachments")


class ReadError(Exception):
    """A reference could not be served, and why."""


def parse_record(text: str, *, source: str = "<string>") -> NormalizedRecord:
    """Parse one record's Markdown back into a ``NormalizedRecord``.

    The inverse of ``record_to_markdown``: for any record it round-trips,
    ``record_to_markdown(parse_record(record_to_markdown(r))) ==
    record_to_markdown(r)``, paragraph bytes included.

    **One input it refuses rather than round-trips.** The record format is
    not escaped: a paragraph whose own text contains a literal
    ``<a id="src-000001-p2"></a>`` is indistinguishable from the separator
    the serializer writes. Such a record serializes, and parsing it back
    raises here rather than silently splitting the paragraph in two. The
    failure is loud on purpose - a corrupted read of evidence is worse than a
    refused one - but it means the pair are inverses over the records a
    normalizer produces, not over every string the dataclass will hold.
    Escaping the anchor form would fix it and would change the on-disk
    format, which is not this slice's to change.

    ``source`` names the file in error messages and is otherwise unused.
    """
    if text.startswith("---\r\n"):
        # Named rather than reported as missing frontmatter, which is what a
        # CRLF checkout used to look like from here. The record format is LF;
        # `.gitattributes` keeps the repository's own files that way.
        raise ReadError(
            f"{source}: record has CRLF line endings - the record format is "
            "LF (see docs/normalized-record-schema.md)"
        )
    if not text.startswith("---\n"):
        raise ReadError(f"{source}: not a normalized record - no frontmatter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise ReadError(f"{source}: frontmatter is not terminated")

    try:
        frontmatter = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise ReadError(f"{source}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise ReadError(f"{source}: frontmatter is not a mapping")

    fields = {}
    for name in _REQUIRED_FIELDS:
        if name not in frontmatter:
            raise ReadError(f"{source}: frontmatter is missing {name!r}")
        fields[name] = frontmatter[name]
    for name in _OPTIONAL_FIELDS:
        if name in frontmatter:
            fields[name] = frontmatter[name]
    for key, attr in _ALIASED_OPTIONAL_FIELDS.items():
        if key in frontmatter:
            fields[attr] = frontmatter[key]

    unexpected = (
        set(frontmatter)
        - set(_REQUIRED_FIELDS)
        - set(_OPTIONAL_FIELDS)
        - set(_ALIASED_OPTIONAL_FIELDS)
        - set(_STRUCTURED_OPTIONAL_FIELDS)
    )
    if unexpected:
        # Explicit rather than NormalizedRecord(**frontmatter), which would
        # raise a bare TypeError naming neither the file nor the schema.
        raise ReadError(
            f"{source}: frontmatter carries fields the schema does not define: "
            + ", ".join(sorted(unexpected))
        )

    quoted_excised = frontmatter.get("quoted_excised")
    if quoted_excised is not None:
        quoted_excised = _as_bool(quoted_excised, source)
    attachments = frontmatter.get("attachments")
    if attachments is not None:
        attachments = _as_attachments(attachments, source)

    body = text[end + len("\n---\n") :]
    images = _as_string_list(fields.pop("images"), source) if "images" in fields else None
    record = NormalizedRecord(
        contemporaneous=_as_bool(fields.pop("contemporaneous"), source),
        images=images,
        paragraphs=_parse_paragraphs(body, source),
        quoted_excised=quoted_excised,
        attachments=attachments,
        **{
            name: _as_text(value, name, source, required=name in _REQUIRED_FIELDS)
            for name, value in fields.items()
        },
    )
    _check_anchors(body, record, source)
    return record


def _as_text(
    value: object, name: str, source: str, *, required: bool
) -> str | None:
    """Frontmatter scalars as the schema declares them: strings.

    A schema-legal ``event_date: 1845-10-22`` is a ``datetime.date`` by the
    time yaml is done with it, and would otherwise reach a field declared
    ``str``. Dates are rendered ISO-8601 rather than by ``str()`` so the
    round trip is stable.

    A required field may not be null - ``id:`` with no value used to arrive as
    ``None`` and crash somewhere downstream in ``anchor_id`` - and no field
    may be a list or a mapping. Stringifying those would turn
    ``recorded_date: [a, b]`` into ``"['a', 'b']"`` and call it evidence.
    """
    if value is None:
        if required:
            raise ReadError(f"{source}: {name!r} is required and must not be empty")
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict, set, tuple)):
        raise ReadError(
            f"{source}: {name!r} must be a single value, got {type(value).__name__}"
        )
    return str(value)


def _as_bool(value: object, source: str) -> bool:
    """``contemporaneous`` as a real bool.

    Load-bearing rather than pedantic: it is how the temporal discipline of
    part 05 §6 reaches retrieval (#12), and the string ``"false"`` is true.
    """
    if isinstance(value, bool):
        return value
    raise ReadError(
        f"{source}: 'contemporaneous' must be a YAML boolean, got {value!r}"
    )


def _as_attachments(value: object, source: str) -> list[dict]:
    """``attachments``: a list of ``{filename, type}`` mappings (#78), listed
    by filename and type per the schema - not text, so it does not go
    through ``_as_text`` with the rest of the optional fields."""
    if not isinstance(value, list):
        raise ReadError(
            f"{source}: 'attachments' must be a list, got {type(value).__name__}"
        )
    for item in value:
        if not isinstance(item, dict) or set(item) != {"filename", "type"}:
            raise ReadError(
                f"{source}: each attachment must be a mapping with 'filename' "
                f"and 'type', got {item!r}"
            )
    return value


def _as_string_list(value: object, source: str) -> list[str]:
    """``images`` as a real list of strings.

    A YAML scalar there would be a single name written without the list
    form the schema declares (docs/normalized-record-schema.md, "images").
    """
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ReadError(f"{source}: 'images' must be a list of strings")
    return value


def _parse_paragraphs(body: str, source: str) -> list[str]:
    """Split an anchored body back into its paragraphs, byte for byte.

    A pdf page marker sits between two anchors (or before the first one)
    with no anchor of its own, so it is not found by scanning for anchors.
    It is peeled off the *end* of the segment that trails it instead of
    recovered by blank-line splitting the segment - a real paragraph may
    contain its own internal blank line (AWKWARD in test_read_ref.py), and
    blank-line splitting it would corrupt evidence rather than recover a
    marker.
    """
    anchors = list(_ANCHOR_TAG.finditer(body))
    if not anchors:
        # A record with no paragraphs serializes to an empty body. Not an
        # error: the schema allows it, and an empty record is still a record.
        if body.strip():
            raise ReadError(f"{source}: body has text but no paragraph anchors")
        return []

    paragraphs = []
    leading = body[: anchors[0].start()].strip("\n")
    if leading:
        # Nothing but page markers ever renders before the first real
        # paragraph, so splitting this run on blank lines is safe.
        paragraphs.extend(_BLANK_LINE.split(leading))

    for position, match in enumerate(anchors):
        start = match.end()
        is_last = position + 1 == len(anchors)
        stop = len(body) if is_last else anchors[position + 1].start()
        segment = body[start:stop]
        # Exactly the separators record_to_markdown inserted, and no more.
        if segment.startswith("\n\n"):
            segment = segment[2:]
        if is_last:
            if segment.endswith("\n"):
                segment = segment[:-1]
        elif segment.endswith("\n\n"):
            segment = segment[:-2]

        markers = []
        while (trailing := _TRAILING_MARKER.search(segment)) is not None:
            markers.insert(0, trailing.group(1))
            segment = segment[: trailing.start()]
        paragraphs.append(segment)
        paragraphs.extend(markers)
    return paragraphs


def _check_anchors(body: str, record: NormalizedRecord, source: str) -> None:
    """Every anchor must be the one the ID scheme derives.

    Anchors are positional and derivable, so the parser discards them rather
    than keeping a second copy. Checking first is what stops a hand-edited
    file asserting an anchor its own ID contradicts.

    Scanned over the body alone, so an anchor-shaped string that happens to
    sit in a frontmatter value cannot be mistaken for one.
    """
    found = [match.group("anchor") for match in _ANCHOR_TAG.finditer(body)]
    expected = [record.anchor_id(n) for n in range(1, len(real_paragraphs(record)) + 1)]
    if found != expected:
        raise ReadError(
            f"{source}: paragraph anchors do not match the record's ID - "
            f"expected {expected}, found {found}"
        )


def record_path(repository: Repository, record_id: str) -> Path:
    """Where a record with this ID would live."""
    return repository.root / NORMALIZED_RELATIVE_PATH / f"{record_id}.md"


def load(repository: Repository, record_id: str) -> NormalizedRecord:
    """Read one record off disk.

    A missing directory and a missing file are different failures and get
    different messages: the first means nothing has been normalized, the
    second means this record is not among what was. Distinguishing them is
    what makes an un-normalized checkout an honest empty state rather than an
    error about a file (ADR-0004).
    """
    normalized_root = repository.root / NORMALIZED_RELATIVE_PATH
    if not normalized_root.is_dir():
        raise ReadError(
            f"no normalized records in this repository ({normalized_root} does "
            "not exist) - run `memoria normalize` to produce them, or choose an "
            "evidence corpus (see docs/open-problems.md 2.4)"
        )
    path = record_path(repository, record_id)
    if not path.is_file():
        raise ReadError(f"no such record: {record_id}")
    return parse_record(path.read_text(encoding="utf-8"), source=record_id)


def read_all(repository: Repository) -> list[NormalizedRecord]:
    """Every record on disk, in ID order.

    What ``rebuild`` indexes. Returns an empty list when nothing is
    normalized, for the same reason ``load`` distinguishes its two failures:
    an empty corpus is a value, not an error.
    """
    normalized_root = repository.root / NORMALIZED_RELATIVE_PATH
    if not normalized_root.is_dir():
        return []
    return [
        parse_record(path.read_text(encoding="utf-8"), source=path.name)
        for path in sorted(normalized_root.glob("SRC-*.md"))
    ]


def list_sources(
    repository: Repository,
    *,
    source_type: str | None = None,
    date_confidence: str | None = None,
    contemporaneous: bool | None = None,
) -> list[NormalizedRecord]:
    """Every record on disk, filtered by the §25 list filters (#64).

    Built on ``read_all`` - it inherits the same empty-corpus behaviour, so a
    fresh clone with no ``sources/normalized/`` renders as no sources rather
    than an error (ADR-0004). Filtering lives here, next to ``read_all``,
    rather than in an adapter: it is a rule over the record schema, and
    §40.1's "one core service layer" is what keeps a filter written once
    from becoming a filter written differently by the web layer and a future
    caller.

    All three filters are optional and compose (ANDed together), matching
    ``index.SearchFilters``'s discipline over the same fields.
    """
    records = read_all(repository)
    if source_type is not None:
        records = [r for r in records if r.source_type == source_type]
    if date_confidence is not None:
        records = [r for r in records if r.date_confidence == date_confidence]
    if contemporaneous is not None:
        records = [r for r in records if r.contemporaneous == contemporaneous]
    return records


def _confined(repository: Repository, path: PurePosixPath) -> Path:
    """Resolve a repository-relative path, refusing anything outside the root.

    The second of the two confinement checks. ``references`` refuses a
    reference that *says* it climbs out; this refuses one that turns out to,
    which is the case a symlink makes - the reference is an ordinary relative
    path and only the resolved target leaves the tree.

    Both roots are resolved before comparison so that a symlinked repository
    root - a worktree reached through one, say - is compared like with like
    rather than being refused wholesale.
    """
    return _confined_to(repository.root, path)


def _confined_to(root: Path, path: PurePosixPath) -> Path:
    """``_confined``'s check, generalized to an arbitrary root.

    ``read_raw_source`` confines to ``evidence_root`` rather than
    ``repository.root`` - a different tree, the same escape the check
    guards against.
    """
    resolved = (root / path).resolve()
    root = root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ReadError(f"path escapes the repository: {path}")
    return resolved


@dataclass(frozen=True)
class RawSource:
    """The un-normalized file a record was normalized from, verbatim.

    ``memoria.web``'s "Open original" read (#64/#25): the raw bytes at
    ``original_file``, plus the ``original_locator`` a person follows to
    find the passage within them. Never parsed, per
    ``docs/normalized-record-schema.md``.
    """

    text: str
    original_locator: str


def read_raw_source(repository: Repository, record_id: str) -> RawSource:
    """Serve the un-normalized file ``record_id`` was normalized from.

    Raises ``ReadError`` for an unknown record, a missing file, or an
    original that does not decode as UTF-8 - a binary one (docx, pdf), or a
    text one in another encoding. UTF-8 text is the only payload this
    returns, so such a file is refused naming what went wrong rather than
    handed back as bytes pretending to be text (#113). Raises
    ``NoEvidenceRoot`` (``memoria.repository``) when no evidence corpus is
    configured - the same refusal every evidence read gives, rather than a
    guessed default (``Repository.evidence_root``'s own docstring).
    """
    record = load(repository, record_id)
    evidence_root = require_evidence_root(repository)
    path = _confined_to(evidence_root, PurePosixPath(record.original_file))
    if not path.is_file():
        raise ReadError(f"no such original file: {record.original_file}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReadError(
            f"{record.original_file} does not decode as UTF-8 - it is "
            f"either a binary {path.suffix} file or text in another "
            "encoding, and read_raw_source serves UTF-8 text only"
        ) from exc
    return RawSource(text=text, original_locator=record.original_locator)


class LaunchError(Exception):
    """The host could not open the file - no such opener on this machine,
    or the opener started and immediately gave up on it."""


# How long `_launch` waits for an opener to fail before it declares success.
# Long enough to catch a launcher that exits immediately for lack of a
# registered handler (empirically milliseconds); short enough that a normal
# GUI editor, still starting up, never makes the request wait on it.
_LAUNCH_GRACE_SECONDS = 0.5


def reveal_original_source(repository: Repository, record_id: str) -> Path:
    """Launch ``record_id``'s un-normalized file in the host's editor or
    file manager - "Reveal in editor" (#65), the local convenience
    ``docs/adr/0002-ui-is-a-react-client.md`` split off from
    ``read_raw_source``'s primary job. Resolves and confines the path
    exactly as ``read_raw_source`` does - the same ``ReadError`` for an
    unknown record or a missing file, the same ``NoEvidenceRoot`` for no
    evidence corpus configured - but never reads the bytes: launching is a
    side effect on the host machine, not a read. Raises ``LaunchError`` if
    the opener could not be started at all, or exited immediately with a
    failure.

    Whether this should be attempted at all - is the caller on this machine
    - is an HTTP-request fact this module has no request to inspect, and
    stays the web layer's job (``web.routes``'s locality check, gating
    ``POST /sources/{id}/reveal`` before this is ever called).
    """
    record = load(repository, record_id)
    evidence_root = require_evidence_root(repository)
    path = _confined_to(evidence_root, PurePosixPath(record.original_file))
    if not path.is_file():
        raise ReadError(f"no such original file: {record.original_file}")
    _launch(path)
    return path


def _launch(path: Path) -> None:
    """Hand ``path`` to the host OS's default opener.

    The one part of ``reveal_original_source`` that differs per platform,
    isolated here so a test can monkeypatch it rather than actually
    spawning a GUI editor or file manager. ``Popen``, not ``run`` - this
    does not wait out a slow-to-open GUI, only ``_LAUNCH_GRACE_SECONDS`` for
    an opener that is going to fail, so the request it backs still returns
    promptly either way. Raises ``LaunchError`` for a missing opener binary
    or one that exits within the grace period with a non-zero status -
    both cases this module can actually vouch for, unlike an opener still
    running when the grace period elapses.
    """
    if sys.platform == "darwin":
        argv = ["open", str(path)]
    elif sys.platform == "win32":
        argv = ["explorer", str(path)]
    else:
        argv = ["xdg-open", str(path)]
    try:
        process = subprocess.Popen(argv)
    except FileNotFoundError as exc:
        raise LaunchError(f"no opener available on this host: {argv[0]}") from exc
    try:
        returncode = process.wait(timeout=_LAUNCH_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return
    if returncode != 0:
        raise LaunchError(f"{argv[0]} exited immediately with status {returncode}")


@dataclass(frozen=True)
class Read:
    """What one reference resolved to.

    ``text`` is the payload and nothing else - no header, no citation line, no
    envelope. That is what lets a test assert byte-level agreement with the
    record, and what keeps the superset-of-grep constraint checkable rather
    than merely asserted. Adapters shape; they do not fold anything into this
    field.

    ``overlay`` is the curated overlay a decorated paragraph read carries
    (#20) - ``None`` for every other reference shape, and for a paragraph
    read with ``raw=True``. A new field with a default, so the return shape
    changes additively rather than forcing #11's signature open again.

    ``context_manifest`` (#29) is a bare session read's own manifest -
    ``None`` for every other reference shape, and for a ``#T`` turn of a
    session, which cites what was said rather than what was supplied. Built
    live from ``events.jsonl`` rather than requiring a prior derivation to
    have run; ``None`` too if that build fails, the same best-effort
    degradation ``overlay`` already gives a paragraph read whose index
    cannot be read right now - the transcript is the payload and is not
    conditioned on it.
    """

    ref: str
    citation: str
    text: str
    record: NormalizedRecord | None = None
    paragraph: int | None = None
    overlay: "ReadOverlay | None" = None
    context_manifest: dict | None = None


def read(repository: Repository, ref: str, *, raw: bool = False) -> Read:
    """Serve any stable reference. The single read tool's core (part 11 §25).

    Dispatch is read off the reference, because the ID scheme already names
    the type. What comes back is constrained by ``docs/poc-plan.md`` §7, and
    the constraint may not be weakened: **retrieval is a superset of grep**.
    An evidence read returns verbatim source text, never a summary in its
    place, and the full-source read - a bare ``SRC-`` ID, or a repository
    path - returns the file exactly as it is on disk, which is what keeps
    reading through the tool from ever being worse than ``cat``.

    ``raw=True`` goes one level further than that, in one of two shapes
    depending on what it is given (#20 growing the shape #113 forced ahead
    of schedule, rather than inventing a second parameter):

    - for a whole ``SRC-`` record, it serves the pre-normalization original
      at ``original_file`` through ``read_raw_source`` - the file grep would
      have found before a normalizer ever ran (#113) - rather than the
      normalized record;
    - for one paragraph of a ``SRC-`` record, it serves that paragraph
      **undecorated** - the same text and header a plain read gives, with no
      curated overlay appended, which is what keeps the raw undecorated read
      explicitly reachable once decoration exists rather than reachable only
      by accident (``docs/tool-surface.md``).

    Refused for anything else: a path, a subject, a chapter, a section or a
    change carries neither an ``original_file`` nor an overlay to strip.

    An evidence paragraph read that is *not* ``raw`` carries the curated
    overlay too (#20, part 06 §8.3): which entries this paragraph is linked
    to, which have excluded it, and which settlements cite it
    (``memoria.index.overlay_for_anchor``), on ``Read.overlay`` - appended
    after the text, never folded into it, so ``Read.text`` stays
    byte-identical between a decorated and an undecorated read of the same
    paragraph. ``Read.overlay`` is also ``None`` when the index exists but
    cannot be read right now - a schema older than this build, or a
    concurrent writer holding it locked - because the overlay is best-effort
    decoration and the verbatim text is not conditioned on it: a degraded
    index still returns the paragraph, undecorated, rather than failing the
    read. It resolves no reference kind but ``SRC-``, ``SUB-``, ``CHP-``,
    ``SEC-``, ``CHG-``, ``SES-`` (whole or one ``#T`` turn, #28), ``DEC-``
    and ``RES-`` (#30), and repository paths - the rest exist as a named
    error, not as silence.
    Ledgering the served read is the caller's job (``memoria.ledger``, #13):
    this function has no session to ledger against.

    A bare ``SES-`` read carries its own context manifest (#29) on
    ``Read.context_manifest`` - the same appended-after-the-text convention
    as ``overlay``, and ``None`` for the same best-effort reason: a session
    that has served nothing yet, or whose ledger could not be built, still
    returns the transcript.
    """
    try:
        reference = references.parse(ref)
    except references.BadReference as exc:
        # One error type crosses this boundary. A malformed reference is a
        # read failure like any other, and an adapter that had to catch two
        # exception types would eventually catch one of them.
        raise ReadError(str(exc)) from exc
    citation = references.format_citation(reference)

    if isinstance(reference, references.UnknownReference):
        # Before the ``raw`` guard below: a reference that resolves to no kind
        # at all is the caller's real problem, and naming the raw refusal
        # instead would send them after the wrong one.
        raise ReadError(_unknown_kind_message(reference))

    if raw:
        if not isinstance(reference, references.SourceReference):
            raise ReadError(
                f"raw only serves a SRC- reference - a whole record's "
                f"pre-normalization original, or a paragraph's undecorated "
                f"text - not {citation!r} (see docs/tool-surface.md)"
            )
        if reference.paragraph is None:
            raw_source = read_raw_source(repository, reference.record_id)
            return Read(
                ref=ref,
                citation=f"{citation} raw",
                text=raw_source.text,
                record=load(repository, reference.record_id),
            )
        # A paragraph: falls through to the ordinary paragraph read below,
        # which skips the overlay when `raw` is set - #20's second meaning
        # for the same flag to grow into (docs/tool-surface.md), not a
        # second read path duplicating the paragraph lookup here.

    if isinstance(reference, references.PathReference):
        path = _confined(repository, reference.path)
        if not path.is_file():
            raise ReadError(f"no such file in this repository: {reference.path}")
        return Read(
            ref=ref, citation=citation, text=path.read_text(encoding="utf-8")
        )

    if isinstance(reference, references.ChapterReference):
        try:
            entry = manuscript.resolve_chapter(repository, reference.chapter_id)
        except manuscript.ManuscriptError as exc:
            raise ReadError(str(exc)) from exc
        return Read(
            ref=ref, citation=citation, text=entry.path.read_text(encoding="utf-8")
        )

    if isinstance(reference, references.SectionReference):
        try:
            entry = manuscript.resolve_section(repository, reference.section_id)
        except manuscript.ManuscriptError as exc:
            raise ReadError(str(exc)) from exc
        return Read(
            ref=ref, citation=citation, text=entry.path.read_text(encoding="utf-8")
        )

    if isinstance(reference, references.ChangeReference):
        try:
            commit = changes.resolve(repository, reference.change_id)
        except changes.ChangesError as exc:
            raise ReadError(str(exc)) from exc
        return Read(ref=ref, citation=citation, text=changes.render(commit))

    if isinstance(reference, references.SessionReference):
        try:
            text = sessions.read_session(repository, reference.session_id, reference.turn)
        except sessions.SessionError as exc:
            raise ReadError(str(exc)) from exc
        manifest = None
        if reference.turn is None:
            # A bare session reference surfaces its manifest too (#29); a
            # `#T` turn cites what was said, not what was supplied, so it
            # carries none.
            try:
                manifest = context_manifest.build_context_manifest(
                    repository, reference.session_id
                )
            except sessions.SessionError:
                manifest = None
        return Read(ref=ref, citation=citation, text=text, context_manifest=manifest)

    if isinstance(reference, references.DecisionReference):
        try:
            text = record_extractor.read_decision(repository, reference.decision_id)
        except record_extractor.RecordExtractorError as exc:
            raise ReadError(str(exc)) from exc
        return Read(ref=ref, citation=citation, text=text)

    if isinstance(reference, references.ResearchMemoReference):
        try:
            text = record_extractor.read_research_memo(repository, reference.memo_id)
        except record_extractor.RecordExtractorError as exc:
            raise ReadError(str(exc)) from exc
        return Read(ref=ref, citation=citation, text=text)

    if isinstance(reference, references.SubjectReference):
        # Bare, undecorated, exactly what's on disk - the same full-source
        # contract as a bare SRC- read (#11), extended to SUB- and SUB-x/y
        # (#16).
        #
        # One error type crosses this boundary, the same rule already
        # applied to references.BadReference above: subjects.SubjectError is
        # an internal exception of a different module, and a stray one must
        # not reach a caller that catches ReadError alone (mcp/server.py's
        # ToolError mapping, docs/tool-surface.md's "the adapter maps the
        # core's one error type onto it").
        try:
            if reference.entry_slug is None:
                path = subjects.subject_path(repository, reference.subject_id)
                if not path.is_file():
                    raise ReadError(f"no such subject: {reference.subject_id}")
            else:
                path = subjects.find_entry_path(
                    repository, reference.subject_id, reference.entry_slug
                )
                if path is None:
                    raise ReadError(
                        f"no such entry: {reference.subject_id}/{reference.entry_slug}"
                    )
        except subjects.SubjectError as exc:
            raise ReadError(str(exc)) from exc
        return Read(
            ref=ref, citation=citation, text=path.read_text(encoding="utf-8")
        )

    record = load(repository, reference.record_id)
    if reference.paragraph is None:
        # The full-source read: the record's own bytes, frontmatter and
        # anchors included - what `cat` would give.
        return Read(
            ref=ref,
            citation=citation,
            text=record_path(repository, reference.record_id).read_text(
                encoding="utf-8"
            ),
            record=record,
        )

    # Page markers earn no extraction read - a paragraph number counts real
    # paragraphs only (docs/normalized-record-schema.md, "pdf page markers
    # are not paragraphs").
    reals = real_paragraphs(record)
    if not 1 <= reference.paragraph <= len(reals):
        raise ReadError(
            f"{reference.record_id} has {len(reals)} paragraphs; "
            f"there is no ¶{reference.paragraph}"
        )
    overlay = None
    if not raw:
        # Local import: `memoria.index` imports this module at the top
        # level, so importing it back at this module's top level would
        # cycle (see the `TYPE_CHECKING` note above `Read`).
        from memoria.index import overlay_for_anchor

        overlay = overlay_for_anchor(
            repository, references.anchor(reference.record_id, reference.paragraph)
        )
    return Read(
        ref=ref,
        citation=f"{citation} raw" if raw else citation,
        text=reals[reference.paragraph - 1],
        record=record,
        paragraph=reference.paragraph,
        overlay=overlay,
    )


def _unknown_kind_message(reference: references.UnknownReference) -> str:
    """Name the kind. Never a silent empty result (#11)."""
    if reference.known:
        return (
            f"{reference.kind}- references are not resolvable in this build "
            "yet: read(ref) currently serves SRC- records, SUB- subjects "
            "and entries, and repository paths (see docs/tool-surface.md)"
        )
    return (
        f"unknown reference kind {reference.kind}-: read(ref) serves SRC- "
        "records, SUB- subjects and entries, and repository paths (see "
        "docs/tool-surface.md)"
    )
