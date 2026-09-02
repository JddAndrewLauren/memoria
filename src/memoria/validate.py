"""Validate the raw evidence corpus against its evidence manifest - which is
also the SRC- ID ledger (ADR-0006, ``memoria.manifest``) - and the repo's own
normalized source records for dangling SRC- ID references and stale
``raw_sha256`` provenance.
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path

from memoria.index import list_overlay
from memoria.manifest import (
    DEFAULT_MANIFEST_RELATIVE_PATH,
    check_ledger,
    load_converter_pins,
    load_manifest,
)
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.repository import Repository
from memoria.subjects import SUBJECTS_RELATIVE_PATH, SubjectError, parse_entry, parse_subject

_SRC_ID_RE = re.compile(r"SRC-\d{6}", re.IGNORECASE)
_RAW_SHA256_RE = re.compile(r"^raw_sha256:\s*(\S+)\s*$", re.MULTILINE)

# The `convert` extra's own array in pyproject.toml (#79, part 05 §5.4), and
# an exact `name[extras]==version` pin within it. Read with a small regex
# rather than a toml parser: pyproject.toml has no other dependency this
# repo pins exactly, and adding a parser dependency (`tomllib` needs Python
# 3.11, which `requires-python = ">=3.10"` does not guarantee) for one array
# in a file this repo already owns is not worth it. Closes on a `]` at the
# start of its own line, not the first `]` at all - a dependency's own
# extras marker (`markitdown[docx]`) closes with one too, before the
# array's real end.
_CONVERT_EXTRA_RE = re.compile(r"convert\s*=\s*\[(.*?)^\]", re.DOTALL | re.MULTILINE)
_PIN_RE = re.compile(r'"([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([^"]+)"')


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
        if "email_message_index" in entry.extra:
            # A message inside an email export (#78, part 05 §5.1) shares
            # its `path` with the export file - that is what lets `sync`'s
            # per-entry file check keep resolving it - but its `sha256` is
            # the one message's own bytes, not the whole file's, so there is
            # nothing at `path` to hash a whole-file match against here.
            # The export's own entry (present alongside these) is what
            # covers presence/hash of the file itself.
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
    errors.extend(_validate_converter_pins(repo_root, manifest_path))
    errors.extend(_validate_gather_overlay(repo_root))

    return errors


def _pinned_converter_versions(repo_root: Path) -> dict[str, str]:
    """The exact converter versions pyproject.toml's ``convert`` extra pins,
    as ``{package: "package version"}`` - the same ``"name version"`` form a
    record's own ``converter`` field and ``raw/manifest.yaml``'s
    ``converters`` mapping use. Empty if pyproject.toml is missing, has no
    ``convert`` extra, or pins nothing with ``==``."""
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return {}
    match = _CONVERT_EXTRA_RE.search(pyproject_path.read_text(encoding="utf-8"))
    if match is None:
        return {}
    return {
        name: f"{name} {version}"
        for name, version in _PIN_RE.findall(match.group(1))
    }


def _validate_converter_pins(repo_root: Path, manifest_path: Path) -> list[str]:
    """A manifest that recorded a converter version pyproject.toml no
    longer pins (#79, part 05 §5.4) - a pin bumped without the
    ``memoria normalize`` run that would have reconverted against it, or a
    manifest edited by hand. A suffix the manifest has never recorded a
    converter for is not an error: nothing has converted it yet."""
    manifest_converters = load_converter_pins(manifest_path)
    if not manifest_converters:
        return []
    pinned = _pinned_converter_versions(repo_root)

    errors = []
    for suffix, recorded in sorted(manifest_converters.items()):
        package = recorded.split(" ", 1)[0]
        expected = pinned.get(package)
        if expected is not None and expected != recorded:
            errors.append(
                f"converter pin mismatch: manifest records {recorded!r} for "
                f"{suffix!r}, pyproject.toml pins {expected!r}"
            )
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


def _validate_gather_overlay(repo_root: Path) -> list[str]:
    """Every pin and exclusion carries actor and timestamp attribution
    (issue #18, part 06 §8.3's overlay; stored on the entry file itself
    since #21). ``pin``/``exclude`` themselves now refuse to write an empty
    ``actor_name``/``actor_email`` (``index._record_overlay``), but a
    hand-edited entry file still can, so this is the check that actually
    holds the requirement against that case."""
    errors = []
    for overlay in list_overlay(Repository(root=repo_root)):
        if not overlay.actor_name.strip() or not overlay.actor_email.strip():
            errors.append(
                f"{overlay.action} of {overlay.anchor} on {overlay.entry_id} "
                "is missing actor attribution"
            )
            continue
        try:
            datetime.fromisoformat(overlay.at)
        except ValueError:
            errors.append(
                f"{overlay.action} of {overlay.anchor} on {overlay.entry_id} "
                f"has an unparseable timestamp: {overlay.at!r}"
            )
    return errors


def _validate_subjects(repo_root: Path) -> list[str]:
    """Every subject prompt carries its four required declarations, every
    entry's match terms are one of the three shapes (issue #16), and - #91's
    three gaps found reviewing that fix - a subject directory has a prompt at
    all, an entry's frontmatter ``id`` agrees with the directory it sits in,
    and a relation match term is diagnosed as one even without a verb."""
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
        else:
            # A subject whose prompt was never written, or was deleted, used
            # to be invisible to `validate` rather than an error - the
            # directory's entries were still checked below, but nothing said
            # the subject itself was missing.
            errors.append(f"{subject_prompt}: missing subject prompt")

        expected_subject_id = f"SUB-{subject_dir.name}"
        for entry_path in sorted(subject_dir.glob("*.md")):
            if entry_path.name == "_subject.md":
                continue
            try:
                entry = parse_entry(
                    entry_path.read_text(encoding="utf-8"), source=str(entry_path)
                )
            except SubjectError as exc:
                errors.append(str(exc))
                continue
            entry_subject_id = entry.id.split("/", 1)[0]
            if entry_subject_id != expected_subject_id:
                errors.append(
                    f"{entry_path}: entry id {entry.id!r} does not match its "
                    f"directory - expected subject {expected_subject_id!r}"
                )

    return errors
