"""``memoria normalize``: the skip-unchanged normalization run (part 05 §5.4).

Reads the evidence root, appends newly-discovered raw units to the manifest
ledger (``memoria.manifest``, ADR-0006), and converts a unit only when the
manifest's hash for it, or the pinned version of the converter that would
handle it, differs from what the existing record's ``raw_sha256`` /
``converter`` frontmatter says (``docs/normalized-record-schema.md``). The
record is the state; there is no second store of what was converted when.

**The converter seam.** ``CONVERTERS`` maps a raw file's suffix to a
``Converter`` - a plain function from raw bytes to a ``ConversionDraft``.
#76 registered a plain-text converter; #77 adds docx and pdf here without
otherwise touching this module, and #78 registers email converters the same
way. A raw unit whose suffix has no registered converter is left in the
ledger - its ID is still allocated - but produces no record yet, the same
way a future stub-record format will.

**Email is a finer-grained raw unit** (#78, part 05 §5.1-5.2): a message
inside an ``.mbox`` or ``.eml`` export, not the export file itself. That
does not fit the one-file-in, one-record-out ``Converter`` shape above -
resolving a message's ``in_reply_to``/``thread_id`` needs every sibling
message's assigned ID, which only exists once the whole export has been
walked - so email is handled by ``_process_email_containers`` instead,
which gives each message (and each attachment it carries) its own ledger
entry before the main loop below ever sees them, and pre-builds each
message's ``ConversionDraft``.
"""

from __future__ import annotations

import base64
import email
import hashlib
import io
import mailbox
import re
import zipfile
from dataclasses import dataclass, field, replace
from email.message import Message
from email.utils import parsedate_to_datetime
from importlib.metadata import version as _pkg_version
from pathlib import Path, PurePosixPath
from typing import Callable

from memoria.manifest import (
    DEFAULT_MANIFEST_RELATIVE_PATH,
    ManifestEntry,
    format_id,
    id_number,
    load_converter_pins,
    save_manifest,
    sync,
)
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    ReadError,
    is_page_marker,
    parse_record,
    record_to_markdown,
)
from memoria.repository import Repository


@dataclass(frozen=True)
class ConversionDraft:
    """What a converter contributes; the loop fills in the ID and manifest
    provenance fields (``id``, ``original_file``, ``raw_sha256``,
    ``converter``) that are not the converter's to decide.

    The email-only fields and the docx-only ``images`` field below (part 05
    §5.2/§5.4, ``docs/normalized-record-schema.md``) are ``None`` for every
    draft that does not apply.
    """

    source_type: str
    recorded_date: str
    event_date: str
    date_confidence: str
    contemporaneous: bool
    original_locator: str
    paragraphs: list[str]
    thread_id: str | None = None
    subject: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    email_cc: str | None = None
    in_reply_to: str | None = None
    quoted_excised: bool | None = None
    attachments: list[dict] | None = None
    # docx only (part 05 §5.4): embedded images by name. None for every
    # other converter, matching ``NormalizedRecord.images`` (docs/
    # normalized-record-schema.md, "images").
    images: list[str] | None = None


Converter = Callable[[bytes], ConversionDraft]

# Blank-line paragraph boundaries, same rule the record schema documents for
# splitting a normalized record's body (docs/normalized-record-schema.md).
_BLANK_LINE = re.compile(r"\n[ \t]*\n+")


def _decode_text(raw_bytes: bytes) -> str:
    """UTF-8, or cp1252 when the bytes are not UTF-8.

    Found walking the M1 gate (#15) over the Enron slice: one ``.txt``
    attachment was Windows-1252 (byte 0x82, a smart quote), the decode
    raised, and the whole pass stopped with every unit after it unwritten.
    cp1252 is what a Windows-era text file that is not UTF-8 almost always
    is, and ``errors="replace"`` means a stray byte costs one character, not
    the corpus. Every input that decoded before decodes identically, so the
    converter pin is unchanged.
    """
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("cp1252", errors="replace")


def convert_plain_text(raw_bytes: bytes) -> ConversionDraft:
    """The plain-text converter this issue ships.

    No metadata to read from a bare text file: date fields are left empty
    with ``date_confidence: unresolved`` per the schema's "no invented date"
    rule, and paragraphs are split on blank lines with no reflow -
    whitespace policy applies to every converter alike, not only the richer
    ones #77/#78 add.
    """
    text = _decode_text(raw_bytes).replace("\r\n", "\n")
    paragraphs = [p.strip() for p in _BLANK_LINE.split(text) if p.strip()]
    return ConversionDraft(
        source_type="document",
        recorded_date="",
        event_date="",
        date_confidence="unresolved",
        contemporaneous=True,
        original_locator="(whole file)",
        paragraphs=paragraphs,
    )


# A markdown image reference and nothing else on its line - what MarkItDown
# emits in place of a docx's embedded image (a data URI truncated to
# "..."). Matched whole, so an image reference embedded mid-sentence in
# real prose (not a paragraph MarkItDown itself ever produces) is left
# alone rather than silently edited.
_MARKDOWN_IMAGE = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")


def convert_docx(raw_bytes: bytes) -> ConversionDraft:
    """The docx converter (part 05 §5.4): MarkItDown, no stripping pass.

    Keeps whatever MarkItDown emits - headings, lists, tables, links, bold,
    italic - verbatim, split into paragraphs on blank lines like every other
    converter. Embedded images are the one exception: MarkItDown inlines
    them as a data URI, which is "embedded" and the schema forbids it, so a
    paragraph that is nothing but an image reference is dropped rather than
    kept. The image's name is not recoverable from that data URI anyway -
    it comes from the docx's own ``word/media/`` entries instead, listed in
    the `images` field, docx's document body being a zip archive.

    ``markitdown`` is imported here, not at module level: it is an optional
    ``convert`` extra (pyproject.toml), and importing it eagerly would make
    ``memoria.normalize`` - and therefore ``memoria.cli``, which imports it
    unconditionally - fail on a core-only install even for subcommands that
    never touch a docx.
    """
    from markitdown import MarkItDown, StreamInfo

    result = MarkItDown().convert(
        io.BytesIO(raw_bytes), stream_info=StreamInfo(extension=".docx")
    )
    text = result.markdown.replace("\r\n", "\n")
    paragraphs = [
        p.strip()
        for p in _BLANK_LINE.split(text)
        if p.strip() and not _MARKDOWN_IMAGE.match(p.strip())
    ]
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        images = sorted(
            PurePosixPath(name).name
            for name in archive.namelist()
            if name.startswith("word/media/")
        )
    return ConversionDraft(
        source_type="document",
        recorded_date="",
        event_date="",
        date_confidence="unresolved",
        contemporaneous=True,
        original_locator="(whole file)",
        paragraphs=paragraphs,
        images=images,
    )


def convert_pdf(raw_bytes: bytes) -> ConversionDraft:
    """The pdf converter (part 05 §5.4): pdfplumber, page by page.

    MarkItDown's own pdf path drops page boundaries, so this reads pages
    directly and writes a ``<!-- page N -->`` marker between them - not a
    paragraph, per ``docs/normalized-record-schema.md``'s "pdf page markers
    are not paragraphs", and never produced for page 1, which needs no
    marker to be found. A pdf with no extractable text on any page is a
    stub record: no paragraphs, no markers either, since a marker with
    nothing to locate is not worth carrying. OCR is out of scope.

    ``pdfplumber`` is imported here, not at module level, for the same
    core-only-install reason as ``convert_docx``'s ``markitdown`` import.
    """
    import pdfplumber

    blocks: list[str] = []
    has_text = False
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            if page_number > 1:
                blocks.append(f"<!-- page {page_number} -->")
            text = (page.extract_text() or "").replace("\r\n", "\n")
            page_paragraphs = [p.strip() for p in _BLANK_LINE.split(text) if p.strip()]
            if page_paragraphs:
                has_text = True
            blocks.extend(page_paragraphs)
    return ConversionDraft(
        source_type="document",
        recorded_date="",
        event_date="",
        date_confidence="unresolved",
        contemporaneous=True,
        original_locator="(whole file)",
        paragraphs=blocks if has_text else [],
    )


# suffix -> (converter, pinned version string written to the record's
# `converter` field). The version is part of the pin: a future bump to this
# converter's behaviour changes the string, which is what makes "a changed
# converter version reconverts exactly that unit" possible without a code
# diff also being required to trigger it. docx/pdf pin the installed library
# version rather than a literal, so the string always matches what actually
# ran; #79 pins the library version itself exactly in pyproject.toml.
#
# The pin is a zero-arg callable, not a precomputed string: resolving it
# calls ``_pkg_version`` on the docx/pdf extras' distributions, which raises
# if they are not installed. Building this dict is core-only-install-safe
# only if that resolution stays deferred to conversion time, per unit
# actually processed - never at module import.
_Pin = Callable[[], str]

CONVERTERS: dict[str, tuple[Converter, _Pin]] = {
    ".txt": (convert_plain_text, lambda: "plain-text 1"),
    ".docx": (convert_docx, lambda: f"markitdown {_pkg_version('markitdown')}"),
    ".pdf": (convert_pdf, lambda: f"pdfplumber {_pkg_version('pdfplumber')}"),
}

# The pinned version for every email message record, whether it came from an
# `.mbox` export or a standalone `.eml` file - both go through the same
# quoted-reply splitter and header handling (`_convert_email_message`).
# Bumped 1 -> 2 on the M1 gate walk (#15, #108): the header repair and the
# footer cut below change the paragraphs of most Enron records, and the
# drift report is how that cost is shown before the extraction re-reads them.
# Bumped 2 -> 3 (#115): Thread-Index threading, the `subject` field, and the
# `-----Original Message-----` marker no longer surviving the quoted-reply
# cut all change frontmatter or paragraphs, so one pin bump shows the whole
# cost at once.
EMAIL_CONVERTER_VERSION = "email 3"

# Suffixes `_process_email_containers` treats as an "export": a file holding
# one or more raw email-message units. `.eml` holds exactly one - handling
# it the same way as `.mbox` (rather than through `CONVERTERS`) is what
# gives a standalone message the same attachment handling an `.mbox`
# message gets, at the cost of one reserved SRC- number for the file itself
# that never becomes a record (ADR-0006 already tolerates such gaps).
_EMAIL_CONTAINER_SUFFIXES = (".mbox", ".eml")


def _paragraph_hash(paragraph: str) -> str:
    """The extraction's memo key for one paragraph (part 06 §8.12): a sha256
    of its exact text. Converter output that shifts by a space changes this,
    which is the drift #79's report exists to surface (part 05 §5.4)."""
    return hashlib.sha256(paragraph.encode("utf-8")).hexdigest()


def _real_paragraph_hashes(paragraphs: list[str]) -> set[str]:
    """Paragraph hashes for a draft's or a record's real paragraphs - page
    markers excluded, since they earn no anchor and no extraction read
    (``docs/normalized-record-schema.md``, "pdf page markers are not
    paragraphs").

    A set, not a list: the drift count this feeds is "how many distinct
    memo keys need re-extraction", not a positional diff. The accepted gap
    is two genuinely identical paragraphs in one record - they collapse to
    one hash, same as they would in the extraction's own cache.
    """
    return {_paragraph_hash(p) for p in paragraphs if not is_page_marker(p)}


@dataclass
class NormalizeReport:
    added_units: list[str]
    converted: list[str]
    skipped: list[str]
    unconvertible: list[str]
    # Record id -> count of paragraph hashes that changed against the
    # record this run replaced (#79). Only entries that had a prior,
    # parseable record are counted - a brand new record's paragraphs are
    # new content, not drift. Absent (never zero) for a record with no
    # drift, so ``len(...)`` is "how many records changed" and
    # ``sum(...values())`` is "how many paragraph hashes changed" - the
    # two numbers the drift report gates a converter bump on.
    paragraph_drift: dict[str, int] = field(default_factory=dict)
    # Units whose converter raised, by ID, with the exception's text. The
    # pass goes on past them (found on the Enron slice, #106: a corrupt pdf
    # attachment stopped the whole run and left every later record
    # unwritten). No record is written for a failed unit, and it is retried
    # on the next run because nothing on disk says it was skipped.
    failed: dict[str, str] = field(default_factory=dict)


def normalize(
    repository: Repository,
    evidence_root: Path,
    *,
    force_all: bool = False,
    manifest_relative_path: str = DEFAULT_MANIFEST_RELATIVE_PATH,
) -> NormalizeReport:
    """Run one normalization pass.

    ``force_all=True`` forces every convertible unit to reconvert,
    regardless of whether its hash or converter version changed.
    """
    evidence_root = Path(evidence_root)
    manifest_path = evidence_root / manifest_relative_path
    entries, added = sync(evidence_root, manifest_relative_path)
    entries, email_added, email_drafts = _process_email_containers(evidence_root, entries)

    # The pinned converter version for every suffix actually present on disk
    # (#79, part 05 §5.4), merged onto whatever a prior run recorded so a
    # suffix with no unit in the current corpus keeps its last known pin
    # rather than losing it. `validate` compares this against pyproject.toml.
    suffixes_present = {
        Path(entry.path).suffix for entry in entries if not entry.deleted
    }
    converters = load_converter_pins(manifest_path)
    converters.update(
        {
            suffix: pin()
            for suffix, (_converter, pin) in CONVERTERS.items()
            if suffix in suffixes_present
        }
    )
    save_manifest(manifest_path, entries, converters=converters)

    output_root = repository.root / NORMALIZED_RELATIVE_PATH

    converted = []
    skipped = []
    unconvertible = []
    paragraph_drift: dict[str, int] = {}
    failed: dict[str, str] = {}
    for entry in entries:
        if entry.deleted:
            continue

        email_draft = email_drafts.get(entry.id)
        if email_draft is not None:
            pinned_version = EMAIL_CONVERTER_VERSION
            get_draft: Callable[[], ConversionDraft] = lambda draft=email_draft: draft
        else:
            registration = CONVERTERS.get(Path(entry.path).suffix)
            if registration is None:
                unconvertible.append(entry.id)
                continue
            converter, pin = registration
            pinned_version = pin()
            get_draft = lambda c=converter, e=entry: c((evidence_root / e.path).read_bytes())

        record_path = output_root / f"{entry.id}.md"
        # Read whatever record is already there, force_all or not: the
        # drift report below needs the prior paragraphs to compare against
        # regardless of why this unit is reconverting.
        existing = _try_parse(record_path) if record_path.is_file() else None
        if (
            not force_all
            and existing is not None
            and existing.raw_sha256 == entry.sha256
            and existing.converter == pinned_version
        ):
            skipped.append(entry.id)
            continue

        try:
            draft = get_draft()
        except Exception as exc:  # noqa: BLE001 - one bad unit must not end the pass
            failed[entry.id] = f"{type(exc).__name__}: {exc}"
            continue
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
            thread_id=draft.thread_id,
            subject=draft.subject,
            email_from=draft.email_from,
            email_to=draft.email_to,
            email_cc=draft.email_cc,
            in_reply_to=draft.in_reply_to,
            quoted_excised=draft.quoted_excised,
            attachments=draft.attachments,
            images=draft.images,
        )
        if existing is not None:
            changed = len(
                _real_paragraph_hashes(draft.paragraphs)
                - _real_paragraph_hashes(existing.paragraphs)
            )
            if changed:
                paragraph_drift[entry.id] = changed

        output_root.mkdir(parents=True, exist_ok=True)
        record_path.write_text(record_to_markdown(record), encoding="utf-8")
        converted.append(entry.id)

    return NormalizeReport(
        added_units=added + email_added,
        converted=converted,
        skipped=skipped,
        unconvertible=unconvertible,
        paragraph_drift=paragraph_drift,
        failed=failed,
    )


def _try_parse(record_path: Path) -> NormalizedRecord | None:
    """A record that fails to parse is treated as needing reconversion
    rather than crashing the run - a hand-corrupted file should not block
    every other unit."""
    try:
        return parse_record(record_path.read_text(encoding="utf-8"), source=record_path.name)
    except ReadError:
        return None


# --- email: raw units finer than the file (#78, part 05 §5.1-5.4) ---------


def _process_email_containers(
    evidence_root: Path, entries: list[ManifestEntry]
) -> tuple[list[ManifestEntry], list[str], dict[str, ConversionDraft]]:
    """Expand every raw email export into one ledger entry per message, and
    one per attachment it carries, then pre-build each message's
    ``ConversionDraft``.

    Message sub-entries share the container's own ``path`` rather than a
    synthetic one: that is what lets ``sync``'s per-entry file-existence
    check keep resolving them, deleted or not, without this module reaching
    into ``sync``'s own bookkeeping. They are told apart from the
    container's own entry, and from each other, by
    ``extra["email_message_index"]`` - the "locator for an email message
    unit" ``manifest.ManifestEntry`` already reserves ``extra`` for.
    ``sync``'s blind per-path rehash overwrites a message entry's hash with
    the whole container's; this function corrects it back to the one
    message's own bytes on every call, which is also what makes "only the
    changed message reconverts" true.

    An attachment, once extracted, is an ordinary raw file at a real, unique
    path - indistinguishable from any other raw unit - so its own ledger
    entry is created the same way, and a later run's plain ``sync`` will
    maintain it without this function's help.
    """
    others = [e for e in entries if "email_message_index" not in e.extra]
    prior_messages = {
        (e.path, e.extra["email_message_index"]): e
        for e in entries
        if "email_message_index" in e.extra
    }
    by_path = {e.path: e for e in entries}

    next_number = max((id_number(e.id) for e in entries), default=0) + 1
    added_ids: list[str] = []
    new_entries: dict[str, ManifestEntry] = {}
    drafts: dict[str, ConversionDraft] = {}

    for container in others:
        if container.deleted or Path(container.path).suffix not in _EMAIL_CONTAINER_SUFFIXES:
            # A container this pass does not read (deleted, or no longer an
            # export) still owns message IDs from a prior run. Carry them
            # forward as deleted, the same rule `sync` applies to a raw file
            # that vanished - otherwise they fall out of `combined` below and
            # their numbers get reissued.
            for key, prior in prior_messages.items():
                if key[0] == container.path:
                    new_entries[prior.id] = replace(prior, deleted=True)
            continue
        messages = _read_container_messages(evidence_root / container.path)

        # Pass 1: one ledger entry per message, reusing a prior run's ID and
        # refreshing its hash to its own bytes.
        seen_keys = set()
        entry_id_by_index: dict[int, str] = {}
        for index, message in enumerate(messages):
            key = (container.path, index)
            seen_keys.add(key)
            sha256 = hashlib.sha256(message.as_bytes()).hexdigest()
            prior = prior_messages.get(key)
            if prior is None:
                message_entry = ManifestEntry(
                    id=format_id(next_number),
                    path=container.path,
                    sha256=sha256,
                    extra={"email_message_index": index},
                )
                next_number += 1
                added_ids.append(message_entry.id)
            else:
                message_entry = replace(prior, sha256=sha256, deleted=False)
            new_entries[message_entry.id] = message_entry
            entry_id_by_index[index] = message_entry.id
        # A message no longer present (the export shrank) keeps its number
        # reserved - `sync`'s own rule for a removed raw file, applied at
        # this finer grain so the ledger stays dense and monotonic
        # (`check_ledger`).
        for key, prior in prior_messages.items():
            if key[0] == container.path and key not in seen_keys:
                new_entries[prior.id] = replace(prior, deleted=True)

        # Pass 2: attachments, materialized under raw/ and ledgered like any
        # other raw file; listed on the message record by filename and type.
        attachments_by_index: dict[int, list[dict]] = {}
        for index, message in enumerate(messages):
            attachments_meta = []
            for attachment_index, (filename, part) in enumerate(_iter_attachments(message)):
                storage_path = _attachment_storage_path(
                    container.path, index, attachment_index, filename
                )
                payload = part.get_payload(decode=True) or b""
                full_path = evidence_root / storage_path
                if not full_path.is_file() or full_path.read_bytes() != payload:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_bytes(payload)
                sha256 = hashlib.sha256(payload).hexdigest()
                existing_attachment = by_path.get(storage_path)
                if existing_attachment is None:
                    attachment_entry = ManifestEntry(
                        id=format_id(next_number), path=storage_path, sha256=sha256
                    )
                    next_number += 1
                    added_ids.append(attachment_entry.id)
                elif existing_attachment.sha256 != sha256 or existing_attachment.deleted:
                    attachment_entry = replace(existing_attachment, sha256=sha256, deleted=False)
                else:
                    attachment_entry = existing_attachment
                new_entries[attachment_entry.id] = attachment_entry
                by_path[storage_path] = attachment_entry
                attachments_meta.append(
                    {"filename": filename, "type": _attachment_type(filename)}
                )
            attachments_by_index[index] = attachments_meta

        # Pass 3: threading - needs every sibling's ID from pass 1.
        message_ids = [_clean_message_id(m.get("Message-ID")) for m in messages]
        id_index_by_message_id = {mid: i for i, mid in enumerate(message_ids) if mid}
        thread_indexes = [_thread_index_bytes(m.get("Thread-Index")) for m in messages]
        parent_index: list[int | None] = []
        for message in messages:
            in_reply_to_mid = _clean_message_id(message.get("In-Reply-To"))
            parent_index.append(
                id_index_by_message_id.get(in_reply_to_mid) if in_reply_to_mid else None
            )

        def _root_index(i: int, visited: set[int] | None = None) -> int:
            visited = visited or set()
            parent = parent_index[i]
            if parent is None or parent in visited:
                return i
            visited.add(i)
            return _root_index(parent, visited)

        def _thread_index_parent(i: int) -> int | None:
            """The sibling whose ``Thread-Index`` is the longest proper
            prefix of message ``i``'s own (finding 2) - ``None`` when no
            such sibling is in the export."""
            own = thread_indexes[i]
            best: int | None = None
            best_len = -1
            for j, other in enumerate(thread_indexes):
                if j == i or other is None or len(other) >= len(own):
                    continue
                if own.startswith(other) and len(other) > best_len:
                    best, best_len = j, len(other)
            return best

        # In-Reply-To absent, Thread-Index present (#115): fold the sibling
        # found by `_thread_index_parent` into `parent_index` itself as a
        # fallback parent *edge*, rather than deriving thread_id separately
        # from the raw Thread-Index bytes. A root message has no such
        # sibling (its Thread-Index is the shortest in the thread), so it
        # keeps `parent_index[i] = None` and resolves its own Message-ID as
        # `thread_id` below - the same single mechanism a reply uses to
        # reach it, so a root/reply pair can no longer split into two
        # thread_id namespaces (one hex fingerprint, one Message-ID).
        for index, message in enumerate(messages):
            if parent_index[index] is not None:
                continue
            if _clean_message_id(message.get("In-Reply-To")) is not None:
                continue
            own_thread_index = thread_indexes[index]
            if own_thread_index is not None and len(own_thread_index) >= _THREAD_INDEX_ROOT_LEN:
                parent_index[index] = _thread_index_parent(index)

        for index, message in enumerate(messages):
            parent_idx = parent_index[index]
            in_reply_to_value = (
                entry_id_by_index[parent_idx] if parent_idx is not None else ""
            )
            root = _root_index(index)
            thread_id_value = message_ids[root] or entry_id_by_index[root]
            draft = _convert_email_message(
                message,
                message_index=index,
                message_count=len(messages),
                in_reply_to=in_reply_to_value,
                thread_id=thread_id_value,
                attachments=attachments_by_index[index],
            )
            drafts[entry_id_by_index[index]] = draft

    # An attachment ledgered by a prior run is already in `others` (sync
    # found its file) *and* in `new_entries` (pass 2 reused its entry). Keep
    # one: before this, every run appended a second copy of every
    # attachment entry, and `validate` reported the duplicates (#108).
    combined = [e for e in others if e.id not in new_entries] + list(new_entries.values())
    combined.sort(key=lambda e: id_number(e.id))
    return combined, added_ids, drafts


# ZL's production wrote this bare line into the header block of two in five
# Enron messages (docs/corpora/enron.md, finding 1). It has no colon, so the
# standard library reads it as the header/body separator and silently reads
# every header below it - From, To, Subject, Thread-Index - as body text.
# Deleting the one line before parsing is the whole repair; a message
# without it is unchanged. Applied to `.eml` only: an mbox goes through
# `mailbox`, which parses on its own.
_BOGUS_HEADER_LINE = re.compile(rb"^Microsoft Mail Internet Headers Version [\d.]+\r?\n", re.MULTILINE)

# The producer's attribution footer, appended to every body in the export and
# fenced by asterisk rules (docs/corpora/enron.md, finding 4). Not the
# sender's words: left in, every record gains a paragraph that says nothing
# and every paragraph hash depends on it. Cut before the quoted-reply split
# so neither the splitter nor the paragraph splitter ever sees it.
_ZL_FOOTER = re.compile(
    r"\n?\*{5,}[ \t]*\nEDRM Enron Email Data Set has been produced .*?\n\*{5,}[ \t]*\n?",
    re.DOTALL,
)


def _read_container_messages(path: Path) -> list[Message]:
    """Every message inside a raw email export, in file order - the order
    ``email_message_index`` numbers them by."""
    if path.suffix == ".eml":
        return [email.message_from_bytes(_BOGUS_HEADER_LINE.sub(b"", path.read_bytes(), count=1))]
    box = mailbox.mbox(str(path), create=False)
    try:
        return list(box)
    finally:
        box.close()


def _clean_message_id(value: str | None) -> str | None:
    """A ``Message-ID``/``In-Reply-To`` header, angle brackets and
    surrounding whitespace stripped - the form both headers share, so they
    compare equal."""
    if not value:
        return None
    return value.strip().strip("<>") or None


# Outlook's `Thread-Index` header (#115, docs/corpora/enron.md finding 2):
# the first 22 bytes identify the conversation and each reply appends
# exactly five more, making a reply's own bytes minus its last five its
# parent's - the substitute used when `In-Reply-To` is absent.
_THREAD_INDEX_ROOT_LEN = 22


def _thread_index_bytes(value: str | None) -> bytes | None:
    """``Thread-Index``, base64-decoded, or ``None`` when absent or not
    valid base64 - a message without one gets no substitute threading."""
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return base64.b64decode(stripped + "=" * (-len(stripped) % 4))
    except ValueError:
        return None


# "On ... wrote:" - the top-posting quote marker (part 05 §5.4). Matched
# whole-line: it introduces a solid quoted block, not more of the sender's
# own words, so everything from here on is cut.
_ON_WROTE_RE = re.compile(r"^On .+ wrote:\s*$")

# Outlook's own "-----Original Message-----" marker, prepended to the
# forwarded/replied "From:\nSent:\n..." header block it introduces (#115,
# `outlook-original-message` fixture). The block after it is already cut by
# `_is_outlook_header_start`; this line precedes that block and, left
# unmatched, survives as a paragraph of its own that says nothing.
_ORIGINAL_MESSAGE_RE = re.compile(r"^-+\s*Original Message\s*-+\s*$", re.IGNORECASE)


def _is_outlook_header_start(lines: list[str], i: int) -> bool:
    """An Outlook "From:\\nSent:\\n..." forwarded/replied header block,
    identified by its first two lines so an ordinary "From:" in a reply's
    own prose is not mistaken for one."""
    return (
        i + 1 < len(lines)
        and re.match(r"^From:\s", lines[i]) is not None
        and re.match(r"^Sent:\s", lines[i + 1]) is not None
    )


def _split_quoted_reply(body: str) -> tuple[str, bool]:
    """The deterministic quoted-reply splitter (part 05 §5.4).

    A `>`-prefixed line is dropped wherever it occurs, which is what makes
    an interleaved reply - the sender's own unprefixed lines running between
    quoted ones - come out with the quoted lines gone and its own lines kept
    in order. An "On ... wrote:" line, a "-----Original Message-----" line,
    or an Outlook header block instead introduces a solid quoted block
    appended to the message, so everything from there on is cut rather than
    filtered line by line.
    """
    lines = body.split("\n")
    kept = []
    excised = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            _ON_WROTE_RE.match(line.strip())
            or _ORIGINAL_MESSAGE_RE.match(line.strip())
            or _is_outlook_header_start(lines, i)
        ):
            excised = True
            break
        if line.startswith(">"):
            excised = True
            i += 1
            continue
        kept.append(line)
        i += 1
    return "\n".join(kept).strip("\n"), excised


def _email_body_text(message: Message) -> str | None:
    """The message's plain-text body, or ``None`` for an HTML-only body.

    MarkItDown's HTML converter (part 05 §5.4) is not wired in here - out of
    scope this pass (see the PR/issue notes) - so such a message produces no
    paragraphs, the same outcome an unreadable pdf gets (a stub record).
    """
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename() is not None:
                continue  # an attachment, not the body
            if part.get_content_type() == "text/plain":
                return _decode_part(part)
        return None
    if message.get_content_type() == "text/plain":
        return _decode_part(message)
    return None


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").replace("\r\n", "\n")


def _iter_attachments(message: Message):
    """Every attachment part: one with a filename, that is not the body."""
    if not message.is_multipart():
        return
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if filename:
            yield filename, part


def _attachment_type(filename: str) -> str:
    suffix = Path(filename).suffix.lstrip(".").lower()
    return suffix or "unknown"


def _attachment_storage_path(
    container_path: str, message_index: int, attachment_index: int, filename: str
) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"{container_path}.attachments/{message_index:04d}-{attachment_index:02d}-{safe_name}"


def _convert_email_message(
    message: Message,
    *,
    message_index: int,
    message_count: int,
    in_reply_to: str,
    thread_id: str,
    attachments: list[dict],
) -> ConversionDraft:
    """One message's ``ConversionDraft`` (part 05 §5.2, §5.4).

    ``in_reply_to``/``thread_id`` and the extracted ``attachments`` are the
    caller's (``_process_email_containers``) to resolve - they need every
    sibling message in the export, which a single message cannot see on its
    own.
    """
    body_text = _email_body_text(message)
    if body_text is None:
        paragraphs: list[str] = []
        quoted_excised = False
    else:
        clean_body, quoted_excised = _split_quoted_reply(_ZL_FOOTER.sub("\n", body_text))
        paragraphs = [p.strip() for p in _BLANK_LINE.split(clean_body) if p.strip()]

    date_header = message.get("Date")
    recorded_date = ""
    event_date = ""
    date_confidence = "unresolved"
    if date_header:
        try:
            parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            pass
        else:
            # The source's own verbatim date, unchanged - it already states
            # its own year, so `event_date` is `recorded_date` unchanged
            # (docs/normalized-record-schema.md's `event_date` rule).
            recorded_date = date_header
            event_date = date_header
            date_confidence = "exact"

    return ConversionDraft(
        source_type="email",
        recorded_date=recorded_date,
        event_date=event_date,
        date_confidence=date_confidence,
        contemporaneous=True,
        original_locator=f"message {message_index + 1} of {message_count}",
        paragraphs=paragraphs,
        thread_id=thread_id,
        subject=message.get("Subject", ""),
        email_from=message.get("From", ""),
        email_to=message.get("To", ""),
        email_cc=message.get("Cc", ""),
        in_reply_to=in_reply_to,
        quoted_excised=quoted_excised,
        attachments=attachments,
    )
