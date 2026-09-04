"""Ingestion status: what the ledger, the normalized records and the index
say about each raw unit - derived, model-free, and never recorded.

Part 05 §5.4 is explicit that "the record is the state - there is no second
store of what was done", and this module keeps that: it writes nothing and
holds nothing. Every fact below is read fresh from three stores that already
exist for their own reasons -

- the manifest ledger (``raw/manifest.yaml``, ADR-0006), which numbers every
  raw unit and carries ``normalize``'s failure marker for a unit whose
  converter raised;
- the normalized records under ``sources/normalized/``, whose frontmatter
  carries the raw hash and converter pin they were produced from;
- the index (``.memoria/index.db``), whose ``paragraphs`` table says what
  ``memoria rebuild`` indexed and whose ``memo`` table says which paragraphs
  the extraction has read under the current subject prompts.

Joined per unit, they answer the three questions an author asks of an
ingest: was this converted, is it in the index, has the extraction read it.
The same posture as ``memoria.health`` (#44): computed without a model,
``None`` for "not checked" rather than an empty tuple for "checked, nothing
wrong", and safe to call at any time.

The two run wrappers at the bottom exist for the web adapter, which may
launch a model-free derived-state pass on the author's own machine
(ADR-0011) but must not compute one itself. They run the same functions the
CLI runs, under one process-wide lock so two clicks cannot run two passes
over the same ledger at once. ``run_rebuild`` passes no embedder on purpose
- embeddings enter by choice (ADR-0007), and the CLI's ``memoria rebuild``
stays the only path that loads the model - and it does not write the
``changes/`` projection, which is likewise the CLI's alone.

``add_raw_unit`` (ADR-0013) is the one thing here that writes: a raw unit's
bytes placed under ``raw/`` from the app, so the author need not copy a file
into the archive by hand. Original state outside the write path, never
committed and never numbered here - the status above stays derived.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from typing import Literal

from memoria.extraction import paragraph_memo_key, subject_prompts_digest
from memoria.index import connect, is_built
from memoria.index import rebuild as rebuild_index
from memoria.manifest import DEFAULT_MANIFEST_RELATIVE_PATH, ManifestEntry, load_manifest
from memoria.normalize import (
    NormalizeReport,
    expected_converter_pin,
    is_email_container,
    is_email_message,
)
from memoria.normalize import normalize as run_normalize_pass
from memoria.records import NormalizedRecord, is_normalized, read_all, real_paragraphs
from memoria.repository import Repository, require_evidence_root
from memoria.subjects import load_all_subjects

# The conversion states a raw unit can be in, in the order the counts line
# prints them. Each is a fact about the ledger entry and its record, never a
# stored label:
#
#   current            a record exists and its raw hash and converter pin
#                      match the ledger and the registered converter
#   out_of_date        a record exists but the raw bytes or the converter
#                      pin moved since - the next normalize reconverts it
#   not_yet_converted  ledgered, convertible, and no record yet
#   failed             the converter raised on it; the ledger carries the
#                      reason, and no record was written
#   unconvertible      no converter is registered for its suffix
#   container          an email export's own reserved number - the messages
#                      inside it are listed as units of their own
#   stub               converted to frontmatter and no body (a scanned pdf,
#                      §5.2) - nothing for the index or the extraction to see
#   deleted            gone from disk; its number stays reserved (ADR-0006)
ConvertedState = Literal[
    "current",
    "out_of_date",
    "not_yet_converted",
    "failed",
    "unconvertible",
    "container",
    "stub",
    "deleted",
]

CONVERTED_STATES: tuple[ConvertedState, ...] = (
    "current",
    "out_of_date",
    "not_yet_converted",
    "failed",
    "unconvertible",
    "container",
    "stub",
    "deleted",
)

# The states the health report's "unprocessed source additions" bullet
# (§47) names: a unit that is in the ledger and that no record accounts
# for. An out-of-date record is not among them - the unit was processed,
# and what changed since is a reconversion, not an addition.
UNPROCESSED_STATES: frozenset[str] = frozenset({"not_yet_converted", "failed", "unconvertible"})


@dataclass(frozen=True)
class UnitStatus:
    """One raw unit's row: its ledger identity and the three stages."""

    id: str
    path: str
    deleted: bool
    converted: ConvertedState
    # ``normalize``'s failure marker, verbatim (``"ExcType: message"``).
    failure_reason: str | None
    # Real paragraphs on the record (page markers left out - what every
    # anchor, index row and extraction read counts against). ``None`` when
    # there is no record.
    record_paragraphs: int | None
    # Rows in the index's ``paragraphs`` table for this unit. ``None`` when
    # the index has never been built - "not checked", not zero.
    indexed_paragraphs: int | None
    # How many of ``record_paragraphs`` the extraction has read under the
    # current subject prompts. ``None`` when there is no record.
    extracted_paragraphs: int | None
    # Which message inside an email export this is, for display.
    email_message_index: int | None


@dataclass(frozen=True)
class IngestionStatus:
    """The whole ledger's rows and their tallies, as of ``generated_at``."""

    # ``None`` when no evidence corpus is configured - the ledger lives
    # under the evidence root, so without one there is nothing to check.
    units: tuple[UnitStatus, ...] | None
    # One count per ``ConvertedState`` (zero included, so the keys are the
    # same on every report), plus ``indexed`` (units whose every real
    # paragraph is in the index) and ``extracted_complete`` (units whose
    # every real paragraph the extraction has read).
    counts: dict[str, int]
    # Files under ``raw/`` the ledger has not numbered yet - dropped in by
    # hand, fetched by a script, or added from the app (ADR-0013) with no
    # normalize since. The one fact about the archive the ledger cannot
    # carry, and the reason an author sees "already in the archive" for a
    # file no other surface shows. Ledger-relative paths (``raw/...``),
    # sorted as ``manifest.sync`` will number them; ``None`` with ``units``.
    unnumbered: tuple[str, ...] | None
    is_normalized: bool
    is_indexed: bool
    generated_at: str


def _unnumbered_paths(evidence_root: Path, entries: list[ManifestEntry]) -> tuple[str, ...]:
    """The same walk ``manifest.sync`` makes, without the hashing or the
    append: every file under ``raw/`` but the ledger itself, less the
    paths the ledger lists."""
    manifest_path = evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH
    raw_root = manifest_path.parent
    listed = {entry.path for entry in entries}
    return tuple(
        sorted(
            p.relative_to(evidence_root).as_posix()
            for p in raw_root.rglob("*")
            if p.is_file() and p != manifest_path and p.relative_to(evidence_root).as_posix() not in listed
        )
    )


def _converted_state(
    entry: ManifestEntry, record: NormalizedRecord | None
) -> tuple[ConvertedState, str | None]:
    if entry.deleted:
        return "deleted", None
    failure = entry.extra.get("failed")
    if record is None and isinstance(failure, dict):
        return "failed", str(failure.get("reason", ""))
    if is_email_container(entry):
        return "container", None
    pin = expected_converter_pin(entry)
    if pin is None and not is_email_message(entry) and record is None:
        return "unconvertible", None
    if record is None:
        return "not_yet_converted", None
    if record.raw_sha256 != entry.sha256 or (pin is not None and record.converter != pin):
        return "out_of_date", None
    if not real_paragraphs(record):
        return "stub", None
    return "current", None


def _indexed_counts(repository: Repository) -> dict[str, int] | None:
    # ``is_built`` first: ``connect`` creates the index file, and a status
    # read must never be the thing that flips "never indexed" to "indexed".
    if not is_built(repository):
        return None
    con = connect(repository)
    try:
        return dict(
            con.execute("SELECT src_id, COUNT(*) FROM paragraphs GROUP BY src_id").fetchall()
        )
    finally:
        con.close()


def _memo_keys(repository: Repository) -> set[str]:
    if not is_built(repository):
        return set()
    con = connect(repository)
    try:
        return {row[0] for row in con.execute("SELECT key FROM memo WHERE kind = 'paragraph'")}
    finally:
        con.close()


def ingestion_status(repository: Repository) -> IngestionStatus:
    """Every raw unit in the ledger with its conversion, index and
    extraction state. Read-only, model-free, computed fresh on every call.

    The extraction stage is ``memoria.extraction.pending_paragraphs``
    grouped by record - the same memo keys under the same subject-prompts
    digest - so this and ``extraction_status()`` agree on what is left to
    read; it does not scan the corpus a second way.
    """
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    built = is_built(repository)
    normalized = is_normalized(repository)
    if repository.evidence_root is None:
        return IngestionStatus(
            units=None,
            counts=_tally(()),
            unnumbered=None,
            is_normalized=normalized,
            is_indexed=built,
            generated_at=generated_at,
        )

    entries = load_manifest(repository.evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH)
    records = {record.id: record for record in read_all(repository)}
    indexed = _indexed_counts(repository)
    memo_keys = _memo_keys(repository)
    digest = subject_prompts_digest(load_all_subjects(repository))

    units = []
    for entry in entries:
        record = records.get(entry.id)
        state, reason = _converted_state(entry, record)
        paragraphs = real_paragraphs(record) if record is not None else None
        units.append(
            UnitStatus(
                id=entry.id,
                path=entry.path,
                deleted=entry.deleted,
                converted=state,
                failure_reason=reason,
                record_paragraphs=len(paragraphs) if paragraphs is not None else None,
                indexed_paragraphs=(
                    None if indexed is None or record is None else indexed.get(entry.id, 0)
                ),
                extracted_paragraphs=(
                    None
                    if paragraphs is None
                    else sum(1 for p in paragraphs if paragraph_memo_key(p, digest) in memo_keys)
                ),
                email_message_index=_message_index(entry),
            )
        )
    return IngestionStatus(
        units=tuple(units),
        counts=_tally(units),
        unnumbered=_unnumbered_paths(repository.evidence_root, entries),
        is_normalized=normalized,
        is_indexed=built,
        generated_at=generated_at,
    )


def _message_index(entry: ManifestEntry) -> int | None:
    value = entry.extra.get("email_message_index")
    return int(value) if isinstance(value, int) else None


def _tally(units) -> dict[str, int]:
    counts: dict[str, int] = {state: 0 for state in CONVERTED_STATES}
    counts["indexed"] = 0
    counts["extracted_complete"] = 0
    for unit in units:
        counts[unit.converted] += 1
        if unit.record_paragraphs:
            if unit.indexed_paragraphs == unit.record_paragraphs:
                counts["indexed"] += 1
            if unit.extracted_paragraphs == unit.record_paragraphs:
                counts["extracted_complete"] += 1
    return counts


def unprocessed_units(repository: Repository) -> tuple[str, ...] | None:
    """The ids §47's "unprocessed source additions" names: ledgered units no
    record accounts for. ``None`` when no evidence corpus is configured.
    Owned here so the health report and the ingestion surface name the
    same units for the same reason - both derive the state from
    ``_converted_state``. This reads only the ledger and the records that
    state needs, not the index or extraction columns ``ingestion_status``
    computes for its table, so the health report does not pay for a full
    status derivation to filter three states."""
    if repository.evidence_root is None:
        return None
    entries = load_manifest(repository.evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH)
    records = {record.id: record for record in read_all(repository)}
    return tuple(
        entry.id
        for entry in entries
        if _converted_state(entry, records.get(entry.id))[0] in UNPROCESSED_STATES
    )


# --- the two runs the web adapter may launch (ADR-0011) -------------------------


class RunInProgress(Exception):
    """A normalize or rebuild is already running in this process."""


# One lock for both passes: a rebuild reads the records a normalize writes,
# so they must not overlap either.
_RUN_LOCK = threading.Lock()


@dataclass(frozen=True)
class RunOutcome:
    """What one launched pass did, in the counts its own report carries."""

    kind: Literal["normalize", "rebuild"]
    summary: dict[str, int]
    elapsed_seconds: float


def _acquire() -> None:
    if not _RUN_LOCK.acquire(blocking=False):
        raise RunInProgress("a normalize or rebuild is already running - try again when it finishes")


def run_normalize(repository: Repository) -> RunOutcome:
    """One normalization pass over the evidence corpus, as ``memoria
    normalize`` runs it (no ``--all``). Raises ``NoEvidenceRoot`` when no
    corpus is configured and ``RunInProgress`` while another pass holds the
    lock."""
    evidence_root = require_evidence_root(repository)
    _acquire()
    started = time.monotonic()
    try:
        report: NormalizeReport = run_normalize_pass(repository, evidence_root)
    finally:
        _RUN_LOCK.release()
    return RunOutcome(
        kind="normalize",
        summary={
            "added_units": len(report.added_units),
            "converted": len(report.converted),
            "skipped": len(report.skipped),
            "unconvertible": len(report.unconvertible),
            "failed": len(report.failed),
            "skipped_failed": len(report.skipped_failed),
            "records_with_drift": len(report.paragraph_drift),
        },
        elapsed_seconds=time.monotonic() - started,
    )


def run_rebuild(repository: Repository) -> RunOutcome:
    """Regenerate the index from the records on disk, as ``memoria rebuild``
    does but with no embedder (ADR-0007: the web never loads the model) and
    without the ``changes/`` projection (CLI-only). Raises ``RunInProgress``
    while another pass holds the lock; ``IndexBuildError`` and
    ``IndexSchemaError`` propagate as they do from ``rebuild``."""
    _acquire()
    started = time.monotonic()
    try:
        report = rebuild_index(repository, embed_fn=None)
    finally:
        _RUN_LOCK.release()
    return RunOutcome(
        kind="rebuild",
        summary={
            "records": len(report.records),
            "paragraphs": sum(len(real_paragraphs(record)) for record in report.records),
            "placements": int(getattr(report.counts, "placements", 0)),
            "appearances": int(getattr(report.appearances, "appearances", 0)),
        },
        elapsed_seconds=time.monotonic() - started,
    )


# --- adding a raw unit from the web (ADR-0013) ----------------------------------
#
# The one write in this module, and deliberately not a durable one: ``raw/``
# is Original state outside ``write.DURABLE_PATHS``, the evidence root may
# live outside the book repository, and nothing is committed - the same
# posture as ``normalize`` materializing an email attachment. The manifest
# is not touched: the ledger numbers a unit on first sight (ADR-0006), so
# the next normalize pass mints the id, never the caller.


class RawUnitError(ValueError):
    """A path a raw unit may not be written at."""


class RawUnitExists(Exception):
    """A raw unit already sits at that path; nothing was written."""

    def __init__(self, path: str) -> None:
        super().__init__(f"{path} already exists - nothing was written")
        self.path = path


@dataclass(frozen=True)
class AddedRawUnit:
    """One raw unit placed under ``raw/``, at the path the ledger will record."""

    path: str
    size: int


def _validated_relative_path(relative_path: str) -> PurePosixPath:
    if "\\" in relative_path or "\0" in relative_path:
        raise RawUnitError(f"{relative_path!r} is not a forward-slash relative path")
    rel = PurePosixPath(relative_path)
    if not relative_path.strip() or rel.is_absolute() or not rel.parts:
        raise RawUnitError(f"{relative_path!r} is not a relative path under raw/")
    for part in rel.parts:
        if part == "..":
            raise RawUnitError(f"{relative_path!r} may not climb out of raw/")
        if part.startswith("."):
            raise RawUnitError(
                f"{relative_path!r} names a hidden file or folder - the ledger numbers "
                "every file under raw/, so a dotfile is refused rather than numbered"
            )
    if str(rel) == PurePosixPath(DEFAULT_MANIFEST_RELATIVE_PATH).name:
        raise RawUnitError(f"{relative_path!r} is the ledger itself")
    return rel


def add_raw_unit(repository: Repository, relative_path: str, data: bytes) -> AddedRawUnit:
    """Place one raw unit's bytes at ``raw/<relative_path>`` under the
    evidence root, creating parent folders so a dropped folder keeps its
    shape. Refuses a path already taken (``RawUnitExists``) rather than
    overwriting, and a path that is absolute, climbs out, or names a dotfile
    (``RawUnitError``). Raises ``NoEvidenceRoot`` when no corpus is
    configured. The manifest is not touched: the next normalize pass numbers
    the unit (ADR-0006)."""
    evidence_root = require_evidence_root(repository)
    rel = _validated_relative_path(relative_path)
    raw_root = (evidence_root / "raw").resolve()
    target = (raw_root / rel).resolve()
    if not target.is_relative_to(raw_root):
        raise RawUnitError(f"{relative_path!r} may not climb out of raw/")
    ledger_path = f"raw/{rel}"
    if target.exists():
        raise RawUnitExists(ledger_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, target)
    except BaseException:
        os.unlink(tmp)
        raise
    return AddedRawUnit(path=ledger_path, size=len(data))
