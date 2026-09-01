"""The CHG- ledger: minting, resolving and rendering human-authored commits.

ADR-0008 settles the shape. Git history is the ledger - a commit's
``change-id:`` trailer is minted by counting the day's existing trailers, and
there is no allocation file to drift from it. **One renderer, two callers**:
``resolve`` calls it against git for ``read(CHG-...)`` (``memoria.records``),
and ``rebuild`` calls it in a loop to write the gitignored ``changes/``
projection - a browsing convenience the read path never consults, so it has
no staleness semantics at all.

``memoria.write`` mints every ``change-id:`` a commit receives, through
``next_change_id`` here rather than a second counter, so minting and
resolving read the same history the same way.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime

from memoria.repository import Repository

CHANGE_ID_TRAILER = "change-id"
CHANGES_RELATIVE_PATH = "changes"

# The two ways `git log` fails that mean "there is no history here yet"
# rather than "this repository is broken": no repository at all, and a
# repository before its first commit. ADR-0008 requires both to succeed with
# nothing (`rebuild` on a bare clone); everything else has to be reported.
_NO_HISTORY = ("not a git repository", "does not have any commits yet")

_CHANGE_ID_LINE = re.compile(
    rf"^{CHANGE_ID_TRAILER}: (CHG-\d{{8}}-\d{{3}})$", re.MULTILINE
)


class ChangesError(Exception):
    """Raised when a ``CHG-`` id names no commit, or git itself fails."""


@dataclass(frozen=True)
class ChangeCommit:
    """A resolved human-authored commit, ready to render as the §11
    projection."""

    change_id: str
    sha: str
    date: str
    files: tuple[str, ...]
    diff: str


def render(commit: ChangeCommit) -> str:
    """The §11 projection: heading, ``Date:``, ``Commit:``, ``Files:``, and a
    ``## Diff`` section. The single function both ``resolve`` and ``rebuild``
    call, so the read path and the ``changes/`` file always agree."""
    lines = [
        f"# {commit.change_id}",
        "",
        f"Date: {commit.date}",
        f"Commit: {commit.sha}",
        "Files:",
    ]
    lines.extend(f"- {path}" for path in commit.files)
    lines.append("")
    lines.append("## Diff")
    lines.append("")
    lines.append(commit.diff)
    return "\n".join(lines) + "\n"


def resolve(repository: Repository, change_id: str) -> ChangeCommit:
    """Locate the commit carrying ``change_id``'s trailer and render it.

    Never an empty result (#11's own rule, restated in the brief): an id with
    no matching commit is a named ``ChangesError``, the same shape
    ``UnknownReference`` already gives an unbuilt kind.
    """
    for entry_id, sha, short_sha, date in _ledger(repository):
        if entry_id == change_id:
            return ChangeCommit(
                change_id=change_id,
                sha=short_sha,
                date=date,
                files=_files_for(repository, sha),
                diff=_diff_for(repository, sha),
            )
    raise ChangesError(f"no commit found for {change_id}")


def rebuild(repository: Repository) -> list[str]:
    """Regenerate ``changes/`` from git history alone (§42).

    History ships inside the clone, so this needs no evidence root and no
    corpus, and succeeds on a repository with no commits at all - it just
    writes nothing. Deletes any existing ``changes/`` first, the same
    clean-regeneration discipline ``index.build_index`` uses, so a stale file
    from a since-rewritten commit is never left behind.
    """
    changes_dir = repository.root / CHANGES_RELATIVE_PATH
    if changes_dir.exists():
        shutil.rmtree(changes_dir)
    entries = _ledger(repository)
    if not entries:
        return []
    changes_dir.mkdir(parents=True, exist_ok=True)
    change_ids = []
    for change_id, sha, short_sha, date in entries:
        commit = ChangeCommit(
            change_id=change_id,
            sha=short_sha,
            date=date,
            files=_files_for(repository, sha),
            diff=_diff_for(repository, sha),
        )
        (changes_dir / f"{change_id}.md").write_text(
            render(commit), encoding="utf-8"
        )
        change_ids.append(change_id)
    return sorted(change_ids)


def next_change_id(repository: Repository) -> str:
    """Mint the next ``CHG-YYYYMMDD-NNN`` id: a per-day sequence counted from
    today's existing trailers in the ledger (ADR-0008). There is no
    allocation file - minting and resolving both read git history."""
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"CHG-{today}-"
    count = sum(1 for change_id, *_ in _ledger(repository) if change_id.startswith(prefix))
    return f"{prefix}{count + 1:03d}"


def _ledger(repository: Repository) -> list[tuple[str, str, str, str]]:
    """``(change_id, full_sha, short_sha, date)`` for every human-authored
    commit reachable from ``HEAD``, as git already recorded it.

    Empty for a repository with no git history at all - not a real
    repository yet, or a bare clone before its first commit - which is what
    lets ``rebuild`` succeed with nothing to render instead of failing. Any
    *other* git failure is a ``ChangesError`` quoting both streams, the
    idiom ``write._git`` already uses: a repository git cannot read is not a
    history that happens to hold no changes.
    """
    result = subprocess.run(
        [
            "git",
            "log",
            "--date=format:%Y-%m-%d %H:%M",
            "--format=%H%x1f%h%x1f%ad%x1f%B%x1e",
        ],
        cwd=repository.root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        reason = " ".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        if not any(phrase in reason for phrase in _NO_HISTORY):
            raise ChangesError(f"git log failed: {reason}")
        return []
    entries = []
    for block in result.stdout.split("\x1e"):
        block = block.strip("\n")
        if not block:
            continue
        sha, short_sha, date, body = block.split("\x1f", 3)
        match = _CHANGE_ID_LINE.search(body)
        if match:
            entries.append((match.group(1), sha, short_sha, date))
    return entries


def _files_for(repository: Repository, sha: str) -> tuple[str, ...]:
    output = _git_output(
        repository, ["diff-tree", "--no-commit-id", "--name-only", "-r", sha]
    )
    return tuple(sorted(line for line in output.splitlines() if line))


def _diff_for(repository: Repository, sha: str) -> str:
    return _git_output(repository, ["show", "--format=", "--patch", sha]).strip("\n")


def _git_output(repository: Repository, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repository.root, capture_output=True, text=True
    )
    if result.returncode != 0:
        reason = " ".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        raise ChangesError(f"git {' '.join(args)} failed: {reason}")
    return result.stdout
