"""Validate the raw evidence corpus against its acquisition manifest, and
the repo's own normalized source records for dangling SRC- ID references.
"""

import hashlib
import re
from pathlib import Path

import yaml

from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.subjects import SUBJECTS_RELATIVE_PATH, SubjectError, parse_entry, parse_subject

# Where the acquisition manifest sits inside the evidence repo. A default,
# not a constant of the system: it was "raw/gutenberg/manifest.yaml" while the
# corpus was Thoreau's Gutenberg texts, and a different archive will lay
# itself out differently. Override per call.
DEFAULT_MANIFEST_RELATIVE_PATH = "raw/manifest.yaml"

_SRC_ID_RE = re.compile(r"SRC-\d{6}", re.IGNORECASE)


def validate(
    evidence_root: Path,
    repo_root: Path | None = None,
    manifest_relative_path: str = DEFAULT_MANIFEST_RELATIVE_PATH,
) -> list[str]:
    """Verify every raw file listed in the manifest matches its recorded hash,
    and that every SRC- ID referenced in a normalized record resolves to an
    actual record.

    Returns a list of human-readable error messages; an empty list means the
    corpus matches the manifest exactly and no SRC- ID is left unresolved.

    The answer-key staleness check that used to run here is gone with the
    answer key itself (docs/open-problems.md §2.4).
    """
    evidence_root = Path(evidence_root)
    repo_root = Path(repo_root) if repo_root is not None else Path(".")

    manifest_path = evidence_root / manifest_relative_path
    manifest = yaml.safe_load(manifest_path.read_text())

    errors = []
    for entry in manifest["files"]:
        # path: entries are relative to the evidence repo root, not the
        # manifest's own directory.
        file_path = evidence_root / entry["path"]
        if not file_path.is_file():
            errors.append(f"missing: {entry['path']}")
            continue
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            errors.append(f"hash mismatch: {entry['path']}")

    errors.extend(_validate_normalized_src_ids(repo_root))
    errors.extend(_validate_subjects(repo_root))

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
