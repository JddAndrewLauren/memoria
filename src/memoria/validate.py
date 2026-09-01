"""Validate the raw evidence corpus against its acquisition manifest."""

import hashlib
from pathlib import Path

import yaml

MANIFEST_RELATIVE_PATH = "raw/gutenberg/manifest.yaml"


def validate(evidence_root: Path) -> list[str]:
    """Verify every raw file listed in the manifest matches its recorded hash.

    Returns a list of human-readable error messages; an empty list means the
    corpus matches the manifest exactly.
    """
    evidence_root = Path(evidence_root)
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

    return errors
