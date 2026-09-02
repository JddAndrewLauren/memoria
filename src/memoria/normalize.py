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

import email
import hashlib
import mailbox
import re
from dataclasses import dataclass, replace
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable

from memoria.manifest import (
    DEFAULT_MANIFEST_RELATIVE_PATH,
    ManifestEntry,
    format_id,
    id_number,
    save_manifest,
    sync,
)
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
    ``converter``) that are not the converter's to decide.

    The email-only fields below (part 05 §5.2, ``docs/normalized-record-
    schema.md``) are ``None`` for every non-email draft.
    """

    source_type: str
    recorded_date: str
    event_date: str
    date_confidence: str
    contemporaneous: bool
    original_locator: str
    paragraphs: list[str]
    thread_id: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    email_cc: str | None = None
    in_reply_to: str | None = None
    quoted_excised: bool | None = None
    attachments: list[dict] | None = None


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


# suffix -> (converter, pinned version string written to the record's
# `converter` field). The version is part of the pin: a future bump to this
# converter's behaviour changes the string, which is what makes "a changed
# converter version reconverts exactly that unit" possible without a code
# diff also being required to trigger it.
CONVERTERS: dict[str, tuple[Converter, str]] = {
    ".txt": (convert_plain_text, "plain-text 1"),
}

# The pinned version for every email message record, whether it came from an
# `.mbox` export or a standalone `.eml` file - both go through the same
# quoted-reply splitter and header handling (`_convert_email_message`).
EMAIL_CONVERTER_VERSION = "email 1"

# Suffixes `_process_email_containers` treats as an "export": a file holding
# one or more raw email-message units. `.eml` holds exactly one - handling
# it the same way as `.mbox` (rather than through `CONVERTERS`) is what
# gives a standalone message the same attachment handling an `.mbox`
# message gets, at the cost of one reserved SRC- number for the file itself
# that never becomes a record (ADR-0006 already tolerates such gaps).
_EMAIL_CONTAINER_SUFFIXES = (".mbox", ".eml")


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
    save_manifest(manifest_path, entries)

    output_root = repository.root / NORMALIZED_RELATIVE_PATH

    converted = []
    skipped = []
    unconvertible = []
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
            converter, pinned_version = registration
            get_draft = lambda c=converter, e=entry: c((evidence_root / e.path).read_bytes())

        record_path = output_root / f"{entry.id}.md"
        if not force_all and record_path.is_file():
            existing = _try_parse(record_path)
            if (
                existing is not None
                and existing.raw_sha256 == entry.sha256
                and existing.converter == pinned_version
            ):
                skipped.append(entry.id)
                continue

        draft = get_draft()
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
            email_from=draft.email_from,
            email_to=draft.email_to,
            email_cc=draft.email_cc,
            in_reply_to=draft.in_reply_to,
            quoted_excised=draft.quoted_excised,
            attachments=draft.attachments,
        )
        output_root.mkdir(parents=True, exist_ok=True)
        record_path.write_text(record_to_markdown(record), encoding="utf-8")
        converted.append(entry.id)

    return NormalizeReport(
        added_units=added + email_added,
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

        for index, message in enumerate(messages):
            parent_idx = parent_index[index]
            in_reply_to_value = entry_id_by_index[parent_idx] if parent_idx is not None else ""
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

    combined = others + list(new_entries.values())
    combined.sort(key=lambda e: id_number(e.id))
    return combined, added_ids, drafts


def _read_container_messages(path: Path) -> list[Message]:
    """Every message inside a raw email export, in file order - the order
    ``email_message_index`` numbers them by."""
    if path.suffix == ".eml":
        return [email.message_from_bytes(path.read_bytes())]
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


# "On ... wrote:" - the top-posting quote marker (part 05 §5.4). Matched
# whole-line: it introduces a solid quoted block, not more of the sender's
# own words, so everything from here on is cut.
_ON_WROTE_RE = re.compile(r"^On .+ wrote:\s*$")


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
    in order. An "On ... wrote:" line or an Outlook header block instead
    introduces a solid quoted block appended to the message, so everything
    from there on is cut rather than filtered line by line.
    """
    lines = body.split("\n")
    kept = []
    excised = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if _ON_WROTE_RE.match(line.strip()) or _is_outlook_header_start(lines, i):
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
        clean_body, quoted_excised = _split_quoted_reply(body_text)
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
        email_from=message.get("From", ""),
        email_to=message.get("To", ""),
        email_cc=message.get("Cc", ""),
        in_reply_to=in_reply_to,
        quoted_excised=quoted_excised,
        attachments=attachments,
    )
