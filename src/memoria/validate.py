"""Validate the raw evidence corpus against its evidence manifest - which is
also the SRC- ID ledger (ADR-0006, ``memoria.manifest``) - and the repo's own
normalized source records for dangling SRC- ID references and stale
``raw_sha256`` provenance.
"""

import hashlib
import re
import subprocess
from datetime import datetime
from pathlib import Path

from memoria.audit import DRAFT_FILENAME
from memoria.authorship import AUTHORIZED_BY_TRAILER
from memoria.changes import CHANGE_ID_TRAILER
from memoria.index import list_overlay
from memoria.manuscript import BOOK_RELATIVE_PATH, BRIEF_FILENAMES, CHAPTERS_RELATIVE_PATH
from memoria.manifest import (
    DEFAULT_MANIFEST_RELATIVE_PATH,
    check_ledger,
    load_converter_pins,
    load_manifest,
)
from memoria.record_extractor import (
    ASSERTION_BADGES,
    RecordExtractorError,
    check_author_evidence,
    check_provenance,
    statement_provenance,
)
from memoria.normalize import EMAIL_CONVERTER_VERSION
from memoria.records import NORMALIZED_RELATIVE_PATH, ReadError
from memoria.records import read as read_ref
from memoria.repository import Repository
from memoria.sessions import SessionError
from memoria.subjects import (
    SUBJECTS_RELATIVE_PATH,
    SubjectError,
    parse_entry,
    parse_statements,
    parse_subject,
)

_SRC_ID_RE = re.compile(r"SRC-\d{6}", re.IGNORECASE)
_RAW_SHA256_RE = re.compile(r"^raw_sha256:\s*(\S+)\s*$", re.MULTILINE)
# A `SES-...#T017` citation (#28, part 04 §4) - the two required parts, a
# session id and a turn, matched loosely enough to catch a suffixed id
# (memoria.ledger's own generated form) as well as the plain one part 04 §4
# shows.
_SESSION_TURN_CITATION_RE = re.compile(
    r"SES-\d{8}-\d{4}(?:-[0-9a-fA-F]+)?#T\d+", re.IGNORECASE
)
# Where a `#T` citation can plausibly appear. Not a repo-wide scan: the
# archive's own plan docs (docs/plan/04-repository-and-identity.md) quote
# this exact form as an illustration, and flagging that as an unresolved
# citation would be a false positive doing the opposite of this check's job.
_SESSION_CITATION_LOCATIONS = ("decisions.md", "questions.md", "research", SUBJECTS_RELATIVE_PATH)

# The two trailers §41 tells manuscript commits apart by (ADR-0008,
# memoria.authorship): a human-authored commit carries `change-id:`, an AI
# manuscript commit `authorized-by:` naming its authorizing turn.
_CHANGE_ID_TRAILER_RE = re.compile(rf"^{CHANGE_ID_TRAILER}: \S+$", re.MULTILINE)
_AUTHORIZED_BY_TRAILER_RE = re.compile(
    rf"^{AUTHORIZED_BY_TRAILER}: (?P<citation>.*)$", re.MULTILINE
)
_SESSION_TURN_CITATION_EXACT_RE = re.compile(
    rf"^{_SESSION_TURN_CITATION_RE.pattern}$", re.IGNORECASE
)
# The two ways `git log` fails that mean "no history here" rather than "a
# broken repository" - the same pair `memoria.changes` accepts.
_NO_HISTORY = ("not a git repository", "does not have any commits yet")

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
    resolves to an actual record, that every record's ``raw_sha256``
    still matches what the manifest records for its raw unit, and that
    every ``SES-...#T017`` citation names a turn an actual session
    transcript carries (#28), and that every badged assertion in an entry
    body carries provenance that terminates in original material, with an
    ``[author]`` statement citing an author-spoken turn (#31, part 15 §23).

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
    errors.extend(_validate_entry_statements(repo_root))
    errors.extend(_validate_converter_pins(repo_root, manifest_path))
    errors.extend(_validate_gather_overlay(repo_root))
    errors.extend(_validate_session_turns(repo_root))
    errors.extend(_validate_manuscript_authorization(repo_root))

    return errors


def validate_warnings(
    evidence_root: Path, manifest_relative_path: str = DEFAULT_MANIFEST_RELATIVE_PATH
) -> list[str]:
    """Non-fatal findings alongside ``validate()``'s errors - today, just the
    manifest's failed-conversion units (#106). A unit whose converter raised
    gets no record and no ``validate()`` error either (there is nothing to
    check it against); reporting it here, not in ``validate()``'s own list,
    is what lets a corpus with one corrupt pdf still validate.

    Empty when the manifest is missing (``validate()`` already reports that
    as an error) or lists no failed unit.
    """
    evidence_root = Path(evidence_root)
    manifest_path = evidence_root / manifest_relative_path
    if not manifest_path.is_file():
        return []
    entries = load_manifest(manifest_path)
    failed_ids = sorted(
        entry.id for entry in entries if not entry.deleted and "failed" in entry.extra
    )
    if not failed_ids:
        return []
    return [
        f"{len(failed_ids)} unit(s) failed to convert and have no record: "
        + ", ".join(failed_ids)
    ]


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
    converter for is not an error: nothing has converted it yet.

    The email converter (``.eml``/``.mbox``/``.msg``, #104) is the
    standard library plus this package's own code, so its pin is
    ``normalize.EMAIL_CONVERTER_VERSION`` rather than a pyproject.toml
    line; a manifest recording an older ``email N`` is the same drift."""
    manifest_converters = load_converter_pins(manifest_path)
    if not manifest_converters:
        return []
    pinned = _pinned_converter_versions(repo_root)
    pinned["email"] = EMAIL_CONVERTER_VERSION

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


def _validate_session_turns(repo_root: Path) -> list[str]:
    """Every ``SES-...#T017`` citation names a turn that actually exists in
    that session's transcript (#28).

    A citation naming a session with no transcript, or a turn number the
    transcript does not have, is the same failure `_validate_normalized_src_ids`
    catches for a dangling ``SRC-`` ID: a durable record pointing at
    evidence that is not (or no longer) there.
    """
    repository = Repository(root=repo_root)
    errors = []
    for relative in _SESSION_CITATION_LOCATIONS:
        target = repo_root / relative
        if target.is_file():
            paths = [target]
        elif target.is_dir():
            paths = sorted(target.rglob("*.md"))
        else:
            continue
        for path in paths:
            content = path.read_text(encoding="utf-8")
            citations = sorted(set(_SESSION_TURN_CITATION_RE.findall(content)))
            for citation in citations:
                try:
                    read_ref(repository, citation)
                except ReadError as exc:
                    errors.append(
                        f"missing transcript turn: {citation} referenced in "
                        f"{path.relative_to(repo_root)} ({exc})"
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


def _validate_entry_statements(repo_root: Path) -> list[str]:
    """Every assertion badge in an entry body carries provenance, every
    provenance reference is original material, and an ``[author]`` statement
    cites an author-spoken transcript turn (#31, part 15 §23) - through the
    same ``record_extractor`` rules the write itself refuses on, so what the
    extractor may not write is what a hand edit may not leave behind either.

    ``[open]`` is not checked: part 06 §9.4's own example carries no
    provenance, and §23 names the three assertion badges. An entry that does
    not parse is ``_validate_subjects``'s finding; a cited turn that does not
    resolve is ``_validate_session_turns``'s. Neither is repeated here.
    """
    subjects_dir = repo_root / SUBJECTS_RELATIVE_PATH
    if not subjects_dir.is_dir():
        return []
    repository = Repository(root=repo_root)

    errors = []
    for entry_path in sorted(subjects_dir.glob("*/*.md")):
        if entry_path.name == "_subject.md":
            continue
        try:
            entry = parse_entry(entry_path.read_text(encoding="utf-8"), source=str(entry_path))
        except SubjectError:
            continue
        where = entry_path.relative_to(repo_root).as_posix()
        for statement in parse_statements(entry.body):
            if statement.badge not in ASSERTION_BADGES:
                continue
            label = f"[{statement.badge}] {statement.text.splitlines()[0][:60]}"
            provenance = statement_provenance(statement)
            if not provenance:
                errors.append(f"{where}: no provenance on {label!r}")
                continue
            citations = []
            for ref in provenance:
                try:
                    citations.append(check_provenance(ref))
                except RecordExtractorError as exc:
                    errors.append(f"{where}: {label!r} cites {exc}")
            if statement.badge == "author":
                try:
                    check_author_evidence(repository, tuple(citations))
                except RecordExtractorError as exc:
                    if not isinstance(exc.__cause__, SessionError):
                        errors.append(f"{where}: {label!r} - {exc}")
    return errors


def _validate_manuscript_authorization(repo_root: Path) -> list[str]:
    """Every AI manuscript write carries an identifiable authorization (#42,
    part 15 §23, Invariant 9) - **including a write to a brief**, which is
    manuscript-class and has an AI write path of its own.

    Git history is the record (§41): a commit touching a manuscript file -
    a section's ``draft.md`` or one of the three briefs - is human-authored
    if it carries a ``change-id:`` trailer (ADR-0008: every human-authored
    commit does, checkpoints and surface writes alike) and is otherwise an
    AI manuscript write, which must carry ``authorized-by:`` naming a
    ``SES-...#T`` turn. A commit with neither is exactly the write this
    check exists to fail, and the message names both readings, because git
    cannot tell an AI write that skipped ``memoria.authorship`` from a hand
    commit that skipped the checkpoint - and by ADR-0008 the second is not
    a human-authored commit either.

    The turn must resolve once the session is derived: a citation naming a
    turn its transcript does not carry is not identifiable. Before
    derivation - the session that wrote it may still be running - the
    citation's form is what can be checked, and the transcript check takes
    over when ``derive-session`` lands the record.
    """
    repository = Repository(root=repo_root)
    try:
        commits = _manuscript_commits(repo_root)
    except _GitLogFailed as exc:
        return [str(exc)]
    errors = []
    for sha, short_sha, body in commits:
        if _CHANGE_ID_TRAILER_RE.search(body):
            continue
        for path in _files_for(repo_root, sha):
            kind = _manuscript_file_kind(path)
            if kind is None:
                continue
            what = "AI write to a brief" if kind == "brief" else "AI manuscript write"
            trailer = _AUTHORIZED_BY_TRAILER_RE.search(body)
            if trailer is None:
                errors.append(
                    f"unauthorized {what}: commit {short_sha} touches {path} with "
                    f"no {AUTHORIZED_BY_TRAILER} trailer - an AI manuscript write "
                    f"names the SES-...#T turn that authorized it, and a human "
                    f"change carries a {CHANGE_ID_TRAILER}"
                )
                continue
            citation = trailer.group("citation").strip()
            if not _SESSION_TURN_CITATION_EXACT_RE.match(citation):
                errors.append(
                    f"unauthorized {what}: commit {short_sha} touches {path} with "
                    f"an {AUTHORIZED_BY_TRAILER} trailer that is not a SES-...#T "
                    f"citation: {citation!r}"
                )
                continue
            session_id = citation.split("#", 1)[0]
            if not _transcript_exists(repository, session_id):
                continue
            try:
                read_ref(repository, citation)
            except ReadError as exc:
                errors.append(
                    f"unauthorized {what}: commit {short_sha} touches {path}, "
                    f"authorized by {citation}, a turn that session's transcript "
                    f"does not carry ({exc})"
                )
    return errors


def _manuscript_file_kind(path: str) -> str | None:
    """``"brief"``, ``"prose"``, or ``None`` for a file that is not
    manuscript-class. Only what a chapter or section directory holds under
    the brief filenames or ``draft.md`` counts - ``manuscript`` owns those
    names and this only asks it."""
    if path == BOOK_RELATIVE_PATH:
        return "brief"
    if not path.startswith(f"{CHAPTERS_RELATIVE_PATH}/"):
        return None
    name = path.rsplit("/", 1)[-1]
    if name in BRIEF_FILENAMES:
        return "brief"
    if name == DRAFT_FILENAME:
        return "prose"
    return None


class _GitLogFailed(Exception):
    """``git log`` failed for a reason other than "no history here"."""


def _manuscript_commits(repo_root: Path) -> list[tuple[str, str, str]]:
    """``(sha, short_sha, message)`` for every non-merge commit reachable
    from ``HEAD`` that touches a manuscript path. Empty - not an error - for
    a directory that is not a git repository or has no commits yet; any
    other git failure is ``_GitLogFailed``, reported as one error rather
    than passed off as a clean history."""
    result = subprocess.run(
        [
            "git", "log", "--no-merges", "--format=%H%x1f%h%x1f%B%x1e",
            "--", BOOK_RELATIVE_PATH, CHAPTERS_RELATIVE_PATH,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        reason = " ".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        if any(phrase in reason for phrase in _NO_HISTORY):
            return []
        raise _GitLogFailed(f"git log failed: {reason}")
    commits = []
    for block in result.stdout.split("\x1e"):
        block = block.strip("\n")
        if not block:
            continue
        sha, short_sha, body = block.split("\x1f", 2)
        commits.append((sha, short_sha, body))
    return commits


def _files_for(repo_root: Path, sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _transcript_exists(repository: Repository, session_id: str) -> bool:
    from memoria.sessions import transcript_path

    return transcript_path(repository, session_id).is_file()
