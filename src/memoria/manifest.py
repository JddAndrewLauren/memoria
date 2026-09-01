"""The evidence manifest, which is also the SRC- ID ledger (ADR-0006).

A raw unit - today, a raw file; a future email export message (#78) is the
same idea at finer grain - is numbered the first time the manifest lists it,
keeps that number forever, and keeps it reserved if the unit is later
deleted. Nothing is reused. The manifest is the only place that state lives:
there is no separate allocation file (ADR-0006 rejected one as a second
store), so the next ID is always ``len(entries) + 1`` over a ledger that is
dense and monotonic by construction.

This module owns the ledger's shape and its two operations: reading it off
disk, and reconciling it against what is actually on disk under the evidence
root's raw tree (``sync``). It does not convert anything - that is
``memoria.normalize``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

# Where raw units live relative to the evidence root, and where the manifest
# itself sits within that tree. A default, like validate.py's own - the
# layout is PoC scaffolding, not a constant of the system.
RAW_RELATIVE_PATH = "raw"
DEFAULT_MANIFEST_RELATIVE_PATH = "raw/manifest.yaml"


@dataclass(frozen=True)
class ManifestEntry:
    """One raw unit's row in the ledger.

    ``path`` is relative to the evidence root, ``raw/...`` prefix included -
    the same convention ``memoria validate`` already uses for the acquisition
    manifest. ``deleted`` is set, never removed, when the raw file that used
    to back this ID is no longer on disk: the ID stays reserved.
    """

    id: str
    path: str
    sha256: str
    deleted: bool = False


def id_number(record_id: str) -> int:
    """The ledger's ordinal for a ``SRC-NNNNNN`` ID."""
    return int(record_id.removeprefix("SRC-"))


def format_id(number: int) -> str:
    """The six-digit zero-padded ``SRC-`` form (``docs/normalized-record-schema.md``)."""
    return f"SRC-{number:06d}"


def load_manifest(manifest_path: Path) -> list[ManifestEntry]:
    """The ledger as it stands on disk. An absent file is an empty ledger."""
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        return []
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    return [
        ManifestEntry(
            id=row["id"],
            path=row["path"],
            sha256=row["sha256"],
            deleted=bool(row.get("deleted", False)),
        )
        for row in data.get("units", [])
    ]


def save_manifest(manifest_path: Path, entries: list[ManifestEntry]) -> None:
    """Write the ledger back, one row per entry, in ID order."""
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in entries:
        row = {"id": entry.id, "path": entry.path, "sha256": entry.sha256}
        if entry.deleted:
            row["deleted"] = True
        rows.append(row)
    manifest_path.write_text(
        yaml.safe_dump({"units": rows}, sort_keys=False), encoding="utf-8"
    )


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync(evidence_root: Path, manifest_relative_path: str = DEFAULT_MANIFEST_RELATIVE_PATH) -> tuple[list[ManifestEntry], list[str]]:
    """Reconcile the ledger against the raw files actually on disk.

    Returns the updated ledger (not yet written - callers persist it, so a
    read-only caller such as ``validate`` can reconcile without writing) and
    the IDs of units newly appended by this call.

    - A raw file the ledger already lists: its hash is refreshed and it is
      un-deleted if it had been marked so (a file that came back).
    - A raw file with no ledger entry: appended with the next ID, in sorted
      path order among the new files - this is what makes "a new unit that
      sorts before existing ones renumbers nothing" true, since existing
      entries are never touched, only appended after.
    - A ledger entry whose file is gone: marked ``deleted``; its ID stays in
      the ledger, reserved, forever.
    """
    evidence_root = Path(evidence_root)
    manifest_path = evidence_root / manifest_relative_path
    raw_root = evidence_root / Path(manifest_relative_path).parent

    entries = load_manifest(manifest_path)
    by_path = {entry.path: entry for entry in entries}

    on_disk = sorted(
        p for p in raw_root.rglob("*") if p.is_file() and p != manifest_path
    )
    seen_paths = set()
    updated: list[ManifestEntry] = []
    for entry in entries:
        file_path = evidence_root / entry.path
        if file_path.is_file():
            updated.append(
                replace(entry, sha256=_hash_file(file_path), deleted=False)
            )
        else:
            updated.append(replace(entry, deleted=True))

    next_number = len(entries) + 1
    new_ids = []
    for file_path in on_disk:
        rel_path = file_path.relative_to(evidence_root).as_posix()
        if rel_path in by_path:
            continue
        new_entry = ManifestEntry(
            id=format_id(next_number), path=rel_path, sha256=_hash_file(file_path)
        )
        updated.append(new_entry)
        new_ids.append(new_entry.id)
        next_number += 1

    return updated, new_ids


def check_ledger(entries: list[ManifestEntry]) -> list[str]:
    """Ledger-shape errors: duplicate IDs, and a ledger that is not dense and
    monotonic - i.e. is not exactly ``SRC-000001 .. SRC-{len(entries)}`` in
    order of first appearance.
    """
    errors = []
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            errors.append(f"duplicate ID in manifest: {entry.id}")
        seen.add(entry.id)

    numbers = [id_number(entry.id) for entry in entries]
    expected = list(range(1, len(entries) + 1))
    if numbers != expected:
        errors.append(
            "manifest ledger is not dense and monotonic: expected IDs in "
            f"order of first appearance to be {format_id(1)}.."
            f"{format_id(len(entries))}, got "
            + ", ".join(entry.id for entry in entries)
        )
    return errors
