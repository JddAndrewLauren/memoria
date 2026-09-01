"""Validate the raw evidence corpus against its acquisition manifest, and
the repo's own normalized source records for dangling SRC- ID references.
"""

import hashlib
import re
from pathlib import Path

import yaml

MANIFEST_RELATIVE_PATH = "raw/gutenberg/manifest.yaml"
NORMALIZED_RELATIVE_PATH = "sources/normalized"
ANSWER_KEY_RELATIVE_PATH = "benchmark/answer-key.yaml"

_SRC_ID_RE = re.compile(r"SRC-\d{6}", re.IGNORECASE)
# A record's body is a run of `<a id="src-000184-p17"></a>` anchors, each
# followed by its paragraph - the form _record_to_markdown writes.
_ANCHOR_RE = re.compile(r'<a id="(?P<anchor>[a-z0-9-]+)"></a>')


def validate(evidence_root: Path, repo_root: Path | None = None) -> list[str]:
    """Verify every raw file listed in the manifest matches its recorded hash,
    that every SRC- ID referenced in a normalized record resolves to an
    actual record, and that the answer key still describes the corpus it was
    built from.

    Returns a list of human-readable error messages; an empty list means the
    corpus matches the manifest exactly, no SRC- ID is left unresolved, and
    every answer-key row still quotes the paragraphs it names.
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
    errors.extend(_validate_answer_key(repo_root))

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


def _read_paragraphs(path: Path) -> dict[str, str]:
    """Map anchor id to paragraph text for one normalized record file."""
    content = path.read_text(encoding="utf-8")
    paragraphs: dict[str, str] = {}
    matches = list(_ANCHOR_RE.finditer(content))
    for n, match in enumerate(matches):
        end = matches[n + 1].start() if n + 1 < len(matches) else len(content)
        paragraphs[match.group("anchor")] = content[match.end() : end].strip()
    return paragraphs


def _validate_answer_key(repo_root: Path) -> list[str]:
    """Check the answer key still describes the corpus it was built from.

    The key is committed while the normalized records it points into are
    derived and gitignored, so the two can drift apart silently - a
    normalizer change that renumbers a paragraph would leave every affected
    row quoting text that is no longer at the anchor it names. The key
    carries the target text verbatim precisely so that drift is detectable
    rather than merely possible: this compares the two.
    """
    key_path = repo_root / ANSWER_KEY_RELATIVE_PATH
    normalized_dir = repo_root / NORMALIZED_RELATIVE_PATH
    if not key_path.is_file() or not normalized_dir.is_dir():
        return []

    key = yaml.safe_load(key_path.read_text(encoding="utf-8"))
    cache: dict[str, dict[str, str]] = {}

    def paragraphs_for(record_id: str) -> dict[str, str] | None:
        if record_id not in cache:
            path = normalized_dir / f"{record_id}.md"
            if not path.is_file():
                return None
            cache[record_id] = _read_paragraphs(path)
        return cache[record_id]

    errors = []
    for link in key.get("links", []):
        link_id = link["link_id"]
        source = paragraphs_for(link["source_record_id"])
        if source is None:
            errors.append(
                f"answer key {link_id}: source record "
                f"{link['source_record_id']} does not exist"
            )
        elif link["source_anchor"] not in source:
            errors.append(
                f"answer key {link_id}: source anchor {link['source_anchor']} "
                "does not exist"
            )
        if link["status"] != "resolved":
            continue
        quoted = []
        for anchor in link["target_anchors"]:
            record_id = anchor.rsplit("-p", 1)[0].upper()
            target = paragraphs_for(record_id)
            if target is None or anchor not in target:
                errors.append(
                    f"answer key {link_id}: target anchor {anchor} does not exist"
                )
                quoted = None
                break
            quoted.append(target[anchor])
        if quoted is not None and "\n\n".join(quoted) != link["target_text"]:
            errors.append(
                f"answer key {link_id}: target_text no longer matches the "
                "paragraphs at its anchors"
            )
    return errors
