"""Validate the raw evidence corpus against its acquisition manifest, and
the repo's own normalized source records for dangling SRC- ID references.
"""

import hashlib
import re
from pathlib import Path

import yaml

MANIFEST_RELATIVE_PATH = "raw/gutenberg/manifest.yaml"
NORMALIZED_RELATIVE_PATH = "sources/normalized"

_SRC_ID_RE = re.compile(r"SRC-\d{6}", re.IGNORECASE)


def validate(evidence_root: Path, repo_root: Path | None = None) -> list[str]:
    """Verify every raw file listed in the manifest matches its recorded hash,
    and that every SRC- ID referenced in a normalized record resolves to an
    actual record.

    Returns a list of human-readable error messages; an empty list means the
    corpus matches the manifest exactly and no SRC- ID is left unresolved.
    """
    evidence_root = Path(evidence_root)
    repo_root = Path(repo_root) if repo_root is not None else Path(".")

    manifest_path = evidence_root / MANIFEST_RELATIVE_PATH
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
