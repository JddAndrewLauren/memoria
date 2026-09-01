"""Validate the raw evidence corpus against its evidence manifest - which is
also the SRC- ID ledger (ADR-0006, ``memoria.manifest``) - and the repo's own
normalized source records for dangling SRC- ID references and stale
``raw_sha256`` provenance.
"""

import hashlib
import re
from pathlib import Path

from memoria.manifest import DEFAULT_MANIFEST_RELATIVE_PATH, check_ledger, load_manifest
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.subjects import SUBJECTS_RELATIVE_PATH, SubjectError, parse_entry, parse_subject

_SRC_ID_RE = re.compile(r"SRC-\d{6}", re.IGNORECASE)
_RAW_SHA256_RE = re.compile(r"^raw_sha256:\s*(\S+)\s*$", re.MULTILINE)


def validate(
    evidence_root: Path,
    repo_root: Path | None = None,
    manifest_relative_path: str = DEFAULT_MANIFEST_RELATIVE_PATH,
) -> list[str]:
    """Verify every raw unit listed in the manifest matches its recorded
    hash, that the ledger itself is dense, monotonic and free of duplicate
    IDs (ADR-0006), that every SRC- ID referenced in a normalized record
    resolves to an actual record, and that every record's ``raw_sha256``
    still matches what the manifest records for its raw unit.

    Returns a list of human-readable error messages; an empty list means the
    corpus matches the manifest exactly and no SRC- ID is left unresolved.

    A raw unit marked ``deleted`` in the ledger is not checked against disk -
    its number stays reserved, and its absence is exactly what deletion
    means (ADR-0006) - so a deleted unit's gap is accepted, not reported.

    The answer-key staleness check that used to run here is gone with the
    answer key itself (docs/open-problems.md §2.4).
    """
    evidence_root = Path(evidence_root)
    repo_root = Path(repo_root) if repo_root is not None else Path(".")

    manifest_path = evidence_root / manifest_relative_path
    if not manifest_path.is_file():
        # load_manifest treats an absent file as an empty ledger, which is
        # right for `sync`'s bootstrap (a brand-new evidence root has no
        # manifest yet) but wrong here: `validate` checks a corpus against
        # its manifest, and a corpus with no manifest at all is not one that
        # "matches exactly" - it is unconfigured, and silence about that
        # would be indistinguishable from `validate: OK`.
        return [f"no manifest: {manifest_relative_path}"]
    entries = load_manifest(manifest_path)

    errors = []
    for entry in entries:
        if entry.deleted:
            continue
        # path: entries are relative to the evidence repo root, not the
        # manifest's own directory.
        file_path = evidence_root / entry.path
        if not file_path.is_file():
            errors.append(f"missing: {entry.path}")
            continue
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != entry.sha256:
            errors.append(f"hash mismatch: {entry.path}")

    errors.extend(check_ledger(entries))
    errors.extend(_validate_normalized_src_ids(repo_root))
    errors.extend(_validate_raw_sha256_matches_manifest(repo_root, entries))
    errors.extend(_validate_subjects(repo_root))

    return errors


def _validate_raw_sha256_matches_manifest(repo_root: Path, entries) -> list[str]:
    normalized_dir = repo_root / NORMALIZED_RELATIVE_PATH
    if not normalized_dir.is_dir():
        return []

    manifest_by_id = {entry.id: entry for entry in entries if not entry.deleted}

    errors = []
    for path in sorted(normalized_dir.glob("*.md")):
        entry = manifest_by_id.get(path.stem)
        if entry is None:
            continue
        match = _RAW_SHA256_RE.search(path.read_text(encoding="utf-8"))
        if match is None:
            # No raw_sha256 field at all: a record that predates the ledger
            # convention, not a staleness this check can speak to.
            continue
        record_hash = match.group(1)
        if record_hash != entry.sha256:
            errors.append(
                f"raw_sha256 mismatch: {path.name} says {record_hash!r}, "
                f"manifest says {entry.sha256!r}"
            )
    return errors


def _validate_normalized_src_ids(repo_root: Path) -> list[str]:
    normalized_dir = repo_root / NORMALIZED_RELATIVE_PATH
    if not normalized_dir.is_dir():
        return []

    record_paths = sorted(normalized_dir.glob("*.md"))
    known_ids = {path.stem for path in record_paths}

    errors = []
    for path in record_paths:
        content = path.read_text(encoding="utf-8")
        # Case-insensitive: a citation like [SRC-000184 ¶17](...#src-000184-p17)
        # carries the same ID in both an uppercase frontmatter/prose form and
        # a lowercase anchor-fragment form; both must resolve.
        referenced_ids = {match.upper() for match in _SRC_ID_RE.findall(content)}
        for referenced_id in sorted(referenced_ids):
            if referenced_id not in known_ids:
                errors.append(
                    f"unresolved SRC- ID: {referenced_id} referenced in "
                    f"{path.name}"
                )
    return errors


def _validate_subjects(repo_root: Path) -> list[str]:
    """Every subject prompt carries its four required declarations, and
    every entry's match terms are one of the three shapes (issue #16)."""
    subjects_dir = repo_root / SUBJECTS_RELATIVE_PATH
    if not subjects_dir.is_dir():
        return []

    errors = []
    for subject_dir in sorted(p for p in subjects_dir.iterdir() if p.is_dir()):
        subject_prompt = subject_dir / "_subject.md"
        if subject_prompt.is_file():
            try:
                parse_subject(
                    subject_prompt.read_text(encoding="utf-8"),
                    source=str(subject_prompt),
                )
            except SubjectError as exc:
                errors.append(str(exc))

        for entry_path in sorted(subject_dir.glob("*.md")):
            if entry_path.name == "_subject.md":
                continue
            try:
                parse_entry(entry_path.read_text(encoding="utf-8"), source=str(entry_path))
            except SubjectError as exc:
                errors.append(str(exc))

    return errors
