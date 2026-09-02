#!/usr/bin/env python3
"""Fetch the pinned Enron custodian archives into an evidence root.

The corpus itself is never committed. This script plus
``docs/corpora/enron-acquisition.yaml`` are the corpus: given the pins, any
machine can reproduce the same bytes, and the recorded hashes are what makes
that claim checkable. See ``docs/corpora/enron.md`` for provenance and the
licence, and ``docs/open-problems.md`` §2.4 for why the evidence corpus is
still an open question rather than a settled one.

Archives land under ``<dest>/.archives`` and are unpacked to
``<dest>/raw/enron/<custodian>/``, so a later ``memoria normalize`` sees them
under ``raw/**`` where the manifest sync walks. Raw units are written once and
never rewritten; re-running the script re-verifies and reports no change.

Nothing here allocates a ``SRC-`` ID. That is the manifest ledger's job
(ADR-0006), and the email converter that would give these messages records at
all is #78, unbuilt.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PINS = Path(__file__).resolve().parent.parent / "docs/corpora/enron-acquisition.yaml"
CHUNK = 1 << 20


@dataclass
class Archive:
    """One pinned custodian archive."""

    custodian: str
    role: str
    file: str
    url: str
    bytes: int
    sha1: str
    sha256: str | None


def load_pins(path: Path) -> tuple[dict, list[Archive]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    archives = [
        Archive(
            custodian=a["custodian"],
            role=a.get("role", ""),
            file=a["file"],
            url=a["url"],
            bytes=int(a["bytes"]),
            sha256=a.get("sha256") or None,
            sha1=a["sha1"],
        )
        for a in doc["archives"]
    ]
    return doc, archives


def hash_file(path: Path) -> tuple[str, str]:
    """``(sha1, sha256)`` of a file, in one pass."""
    h1, h256 = hashlib.sha1(), hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(CHUNK):
            h1.update(block)
            h256.update(block)
    return h1.hexdigest(), h256.hexdigest()


def download(url: str, target: Path, expected_bytes: int) -> None:
    """Download to ``target``, resuming a partial file if one is there.

    The Internet Archive answers with a 302 to a ``dn*.archive.org`` node;
    urllib follows it. A partial file from an interrupted run is continued
    with a Range request rather than started over - these archives run to
    hundreds of megabytes.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    have = target.stat().st_size if target.exists() else 0
    if have == expected_bytes:
        return
    if have > expected_bytes:
        target.unlink()
        have = 0

    request = urllib.request.Request(url, headers={"User-Agent": "memoria-corpus-fetch/1"})
    mode = "wb"
    if have:
        request.add_header("Range", f"bytes={have}-")
        mode = "ab"

    with urllib.request.urlopen(request) as response:
        if have and response.status != 206:
            # The server ignored the range; start clean rather than append
            # a second copy of the head onto the partial file.
            mode, have = "wb", 0
        with target.open(mode) as fh:
            while block := response.read(CHUNK):
                fh.write(block)
                have += len(block)
                print(f"\r  {target.name}: {have / 1e6:.1f} / {expected_bytes / 1e6:.1f} MB",
                      end="", file=sys.stderr, flush=True)
    print("", file=sys.stderr)


def extract(archive_path: Path, into: Path) -> int:
    """Unpack the ``.eml`` members of a custodian archive.

    Each archive also ships the same messages as ``text_*`` plain text, an XML
    load file, and loose attachment copies. Only the ``.eml`` are raw units;
    everything under ``raw/**`` gets a ``SRC-`` ID from the manifest sync
    (ADR-0006) and never gives it back, so the sidecars stay in the zip.
    Refuses any member that escapes ``into``.
    """
    into.mkdir(parents=True, exist_ok=True)
    root = into.resolve()
    count = 0
    with zipfile.ZipFile(archive_path) as zf:
        for member in zf.infolist():
            if member.is_dir() or not member.filename.lower().endswith(".eml"):
                continue
            destination = (root / member.filename).resolve()
            if not destination.is_relative_to(root):
                raise SystemExit(f"{archive_path.name}: member escapes the target dir: {member.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", default=os.environ.get("MEMORIA_EVIDENCE_ROOT"),
                        help="evidence root (default: $MEMORIA_EVIDENCE_ROOT)")
    parser.add_argument("--pins", type=Path, default=DEFAULT_PINS)
    parser.add_argument("--custodian", action="append", default=[],
                        help="fetch only these custodians (repeatable)")
    parser.add_argument("--role", help="fetch only archives with this role, e.g. control")
    args = parser.parse_args()

    if not args.dest:
        parser.error("no --dest and MEMORIA_EVIDENCE_ROOT is not set")
    dest = Path(args.dest).expanduser()

    doc, archives = load_pins(args.pins)
    if args.custodian:
        archives = [a for a in archives if a.custodian in args.custodian]
    if args.role:
        archives = [a for a in archives if a.role == args.role]
    if not archives:
        parser.error("no archives selected")

    archive_dir = dest / ".archives"
    base = dest / doc.get("base", "raw/enron")
    changed = False
    learned: dict[str, str] = {}

    for archive in archives:
        print(f"{archive.custodian} ({archive.bytes / 1e6:.1f} MB)")
        local = archive_dir / archive.file
        stamp = archive_dir / f"{archive.file}.extracted"

        if not local.exists():
            download(archive.url, local, archive.bytes)
            changed = True

        sha1, sha256 = hash_file(local)
        if sha1 != archive.sha1:
            raise SystemExit(
                f"  {archive.file}: sha1 mismatch\n"
                f"    pinned   {archive.sha1}\n"
                f"    on disk  {sha1}\n"
                f"  The file is not what was pinned. Delete it and re-run to refetch."
            )
        if archive.sha256 and sha256 != archive.sha256:
            raise SystemExit(
                f"  {archive.file}: sha256 mismatch\n"
                f"    pinned   {archive.sha256}\n"
                f"    on disk  {sha256}"
            )
        if not archive.sha256:
            learned[archive.file] = sha256

        if stamp.exists() and stamp.read_text(encoding="utf-8").strip() == sha256:
            print("  already unpacked")
            continue
        target = base / archive.custodian
        if target.exists():
            shutil.rmtree(target)
        count = extract(local, target)
        stamp.write_text(sha256 + "\n", encoding="utf-8")
        print(f"  unpacked {count} .eml to {target}")
        changed = True

    if learned:
        write_back(args.pins, learned)
        print(f"\npinned sha256 for {len(learned)} archive(s) in {args.pins}")

    if not changed:
        print("\nno change")
    else:
        print(f"\nevidence root: export MEMORIA_EVIDENCE_ROOT={dest}")
    return 0


def write_back(pins: Path, learned: dict[str, str]) -> None:
    """Fill in the empty ``sha256:`` lines, leaving the file otherwise as written.

    A line edit rather than a YAML round-trip: the pin file carries comments
    that explain the licence and the PII caveat, and PyYAML would drop them.
    """
    lines = pins.read_text(encoding="utf-8").splitlines()
    current = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("file: "):
            current = stripped.removeprefix("file: ").strip()
        elif stripped == "sha256:" and current in learned:
            lines[i] = line.replace("sha256:", f"sha256: {learned[current]}")
    pins.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
