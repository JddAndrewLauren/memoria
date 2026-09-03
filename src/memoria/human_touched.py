"""The human-touched flag (#32, part 08 §14.2): the backstop for the one
case ownership by badge cannot see - the author editing a badged statement
in place.

**What it is.** An index flag on a statement, set at Curator-pass time on
every badged statement a *non-Curator* commit changed since the previous
pass. "Set once, monotonic, never recomputed - reflow cannot unset it, so
the ratchet points toward the author." The Curator never rewrites a flagged
statement; a conflict with one becomes a Memoria note instead
(``memoria.record_extractor.revise_statement``).

**Defined over commits, not over blame.** Nothing here, or anywhere in the
codebase, infers ownership from ``git blame`` - a test holds that. The pass
walks the commits since the last one it recorded, keeps those whose author
is not the Curator, and compares each entry file before and after: a badged
statement present after that was not present before is one that commit
changed. An author's edit through a surface commits as theirs (ADR-0003) and
an Obsidian edit reaches history as a ``CHG-`` checkpoint (ADR-0008), so
both count; a Curator write commits as the Curator and does not.

**The key is the statement, reflowed or not.** A statement has no durable
identity (part 04 §4.1), so the flag is keyed by ``statement_key``: the
badge and the paragraph's text with its whitespace collapsed. Re-wrapping
the lines of a flagged statement leaves its key where it was, which is the
whole reason git-blame span inference was retired - there is no attribution
for a reflow to destroy. An edit to the *words* moves the key, but that edit
is itself a non-Curator commit, and the next pass flags the new text.

**Losing the table is recoverable; that is not a licence to drop it.** The
rows live in a preserved table (``memoria.index.PRESERVED_TABLES``) that
``memoria rebuild`` never touches. A pass with no recorded baseline walks
the whole history, so a deleted index (``--reset-cache``) re-derives every
flag from git - the ledger of truth is the commit record, and the flag is a
cached reading of it that is only ever added to.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime

from memoria import index
from memoria.repository import Repository
from memoria.subjects import Statement, SubjectError, parse_entry, parse_statements
from memoria.write import Actor

# Where entry files live, as a git pathspec; the subject prompt
# (`_subject.md`) carries no statements and is filtered out below.
_ENTRY_PATHSPEC = "subjects/"
_SUBJECT_PROMPT = "_subject.md"
# git's well-known empty tree, the "before" of a root commit.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_HEAD_KEY = "human_touched_head"
# The badges the flag is defined over: a badged statement is the Curator's
# to rewrite unless flagged, so those are the ones a flag protects. A
# Memoria note is neither the author's nor a statement, and testimony needs
# no flag.
_BADGED = ("author", "source", "inferred", "open")


class HumanTouchedError(Exception):
    """Raised when git itself fails under the pass - never for an absent
    history, which is an empty pass rather than an error."""


@dataclass(frozen=True)
class Flagged:
    """One statement the pass flagged, and the non-Curator commit that
    changed it."""

    entry_id: str
    statement: str
    commit_sha: str


@dataclass(frozen=True)
class FlagReport:
    """What one pass did: the ``HEAD`` it read up to (``None`` on a
    repository with no commits), how many non-Curator commits it examined,
    and the statements it newly flagged. A statement already flagged is not
    repeated here - the flag is set once."""

    head: str | None
    commits: int
    flagged: tuple[Flagged, ...]


def statement_key(statement: Statement) -> str:
    """The reflow-stable identity of a badged statement: its badge and its
    text with every run of whitespace collapsed to one space."""
    return f"[{statement.badge}] {' '.join(statement.text.split())}"


def flag(repository: Repository, curator: Actor | None = None) -> FlagReport:
    """The pass-time step: flag every badged statement a non-Curator commit
    changed since the last pass, and record ``HEAD`` as the new baseline.

    ``curator`` is who does *not* count - ``record_extractor.CURATOR`` by
    default, imported lazily because the record extractor is the caller
    this flag gates and the dependency runs that way, not this one. A commit
    is the Curator's by its author email; everything else is a non-Curator
    commit, whether it carries a ``change-id:`` trailer (an app write, a
    checkpoint) or not (a hand ``git commit``). Both are the author's.
    """
    if curator is None:
        from memoria.record_extractor import CURATOR

        curator = CURATOR

    head = _rev_parse_head(repository)
    if head is None:
        return FlagReport(head=None, commits=0, flagged=())

    con = index.connect(repository)
    try:
        baseline = _baseline(con)
        if baseline is not None and not _is_commit(repository, baseline):
            # The recorded baseline is gone from history (a rebase). Walk
            # everything: over-examining fails toward the author, and the
            # flag is set-once so nothing is flagged twice.
            baseline = None
        commits = 0
        flagged: list[Flagged] = []
        now = datetime.now().isoformat(timespec="seconds")
        for sha, parent, email in _commits(repository, baseline, head):
            if email == curator.email:
                continue
            commits += 1
            for entry_id, key in _statements_changed_by(repository, parent, sha):
                inserted = con.execute(
                    "INSERT OR IGNORE INTO human_touched "
                    "(entry_id, statement, commit_sha, flagged_at) VALUES (?, ?, ?, ?)",
                    (entry_id, key, sha, now),
                ).rowcount
                if inserted:
                    flagged.append(Flagged(entry_id=entry_id, statement=key, commit_sha=sha))
        con.execute(
            "INSERT OR REPLACE INTO memoria_schema (key, value) VALUES (?, ?)",
            (_HEAD_KEY, head),
        )
        con.commit()
    finally:
        con.close()
    return FlagReport(head=head, commits=commits, flagged=tuple(flagged))


def flagged_statements(repository: Repository, entry_id: str) -> frozenset[str]:
    """Every statement key flagged on ``entry_id``."""
    con = index.connect(repository)
    try:
        rows = con.execute(
            "SELECT statement FROM human_touched WHERE entry_id = ?", (entry_id,)
        ).fetchall()
    finally:
        con.close()
    return frozenset(row[0] for row in rows)


def is_human_touched(repository: Repository, entry_id: str, statement: Statement) -> bool:
    """Whether ``statement``, as it stands in ``entry_id``'s body now, is
    flagged. Testimony carries no badge and needs no flag - it is the
    author's by definition (part 06 §9.5) - so it is never flagged and never
    reported as such; the write matrix already forbids the Curator touching it."""
    if statement.badge is None:
        return False
    return statement_key(statement) in flagged_statements(repository, entry_id)


# --- git ---------------------------------------------------------------------


def _baseline(con) -> str | None:
    row = con.execute("SELECT value FROM memoria_schema WHERE key = ?", (_HEAD_KEY,)).fetchone()
    return row[0] if row else None


def _rev_parse_head(repository: Repository) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "HEAD"],
        cwd=repository.root, capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _is_commit(repository: Repository, sha: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=repository.root, capture_output=True, text=True,
    )
    return result.returncode == 0


def _commits(
    repository: Repository, baseline: str | None, head: str
) -> list[tuple[str, str, str]]:
    """``(sha, first parent or the empty tree, author email)`` for every
    commit after ``baseline`` up to ``head`` that touched an entry file.
    A merge is compared against its first parent, the same view ``git log
    --first-parent`` gives of what landed on the branch."""
    revisions = f"{baseline}..{head}" if baseline else head
    out = _git(
        repository,
        ["log", "--format=%H%x1f%P%x1f%ae", revisions, "--", _ENTRY_PATHSPEC],
    )
    commits = []
    for line in out.splitlines():
        sha, parents, email = line.split("\x1f")
        parent = parents.split()[0] if parents else _EMPTY_TREE
        commits.append((sha, parent, email))
    return commits


def _statements_changed_by(
    repository: Repository, parent: str, sha: str
) -> list[tuple[str, str]]:
    """The ``(entry_id, statement key)`` pairs ``sha`` added or changed
    relative to ``parent``: badged statements in an entry file after the
    commit that were not in it before. A deleted statement needs no flag -
    there is nothing left to protect - and a rename (``R``) is compared
    against the file's old path, so moving an entry does not by itself
    flag every statement in it."""
    out = _git(
        repository,
        ["diff-tree", "-r", "-M", "--name-status", parent, sha, "--", _ENTRY_PATHSPEC],
    )
    changed = []
    for line in out.splitlines():
        parts = line.split("\t")
        status, paths = parts[0], parts[1:]
        if status.startswith("D") or not paths:
            continue
        before_path, after_path = (paths[0], paths[-1])
        if not _is_entry_file(after_path):
            continue
        before = _statement_keys(repository, parent, before_path if status.startswith("R") else after_path)
        after_entry_id, after = _entry_statement_keys(repository, sha, after_path)
        if after_entry_id is None:
            continue
        for key in sorted(after - before):
            changed.append((after_entry_id, key))
    return changed


def _is_entry_file(path: str) -> bool:
    parts = path.split("/")
    return (
        len(parts) == 3
        and parts[0] == _ENTRY_PATHSPEC.rstrip("/")
        and parts[2].endswith(".md")
        and parts[2] != _SUBJECT_PROMPT
    )


def _statement_keys(repository: Repository, revision: str, path: str) -> set[str]:
    return _entry_statement_keys(repository, revision, path)[1]


def _entry_statement_keys(
    repository: Repository, revision: str, path: str
) -> tuple[str | None, set[str]]:
    """The entry id and its badged statements' keys at ``revision`` - or
    ``(None, set())`` when the file is absent there or is not a parseable
    entry, since a statement that cannot be read cannot be flagged."""
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=repository.root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None, set()
    try:
        entry = parse_entry(result.stdout, source=path)
    except SubjectError:
        return None, set()
    keys = {
        statement_key(s) for s in parse_statements(entry.body) if s.badge in _BADGED
    }
    return entry.id, keys



def _git(repository: Repository, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repository.root, capture_output=True, text=True
    )
    if result.returncode != 0:
        reason = " ".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        raise HumanTouchedError(f"git {' '.join(args)} failed: {reason}")
    return result.stdout
