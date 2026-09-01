"""Where a Memoria repository is, as a value.

ADR-0004 settles the read side as module-level functions taking a frozen
``Repository`` value rather than one repository object with methods. This
module owns that value and the two ways of getting at what it carries.

The value exists so that the invariant "every read, search and write in one
process sees the same roots" has an owner. Three adapters - the CLI, the MCP
server (#11) and the FastAPI app (#64) - would otherwise each construct roots
independently, which is how a half-configured server ends up reading records
from one checkout and evidence from another.

It is frozen, and therefore hashable, so ``functools.lru_cache`` keyed on it
is available for read-only derived tables without a stateful holder and
without a process-global that tests cannot reset. Nothing uses that yet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


class NoEvidenceRoot(Exception):
    """Raised when something that reads evidence has no corpus configured."""


@dataclass(frozen=True)
class Repository:
    """Where this repository's state lives.

    ``root`` is the book repository - the one that holds ``sources/``,
    ``.memoria/`` and the manuscript. ``evidence_root`` is where raw evidence
    lives, which is *configuration* rather than a second co-equal root: part 05
    §5.1 puts raw evidence at ``sources/raw/`` inside the repository, and the
    sibling-repo arrangement is PoC scaffolding. Modelling it as a field means
    a change of corpus - or the arrival of one, since none is currently chosen
    (``docs/open-problems.md`` §2.4) - is a value change rather than a
    signature change across three adapters.

    ``evidence_root`` is optional on purpose. Reading normalized records needs
    only ``root``; requiring a corpus to *construct* the value would stop the
    MCP server starting over a path none of its tools read. Callers that
    genuinely read evidence go through ``require_evidence_root``.
    """

    root: Path
    evidence_root: Path | None = None

    def __post_init__(self) -> None:
        # Coerced so that a caller holding a string - an argv value, a config
        # entry - does not have to import pathlib to build one. Frozen, hence
        # object.__setattr__.
        object.__setattr__(self, "root", Path(self.root))
        if self.evidence_root is not None:
            object.__setattr__(self, "evidence_root", Path(self.evidence_root))


def from_env(start: str | Path | None = None) -> Repository:
    """Build the value from the environment and the filesystem.

    A module-level function rather than a classmethod: the value stays a plain
    data carrier a test can build from two ``tmp_path``s, with no environment
    to monkeypatch.
    """
    configured = os.environ.get(EVIDENCE_ROOT_ENV_VAR)
    return Repository(
        root=discover_root(start),
        evidence_root=Path(configured) if configured else None,
    )


def discover_root(start: str | Path | None = None) -> Path:
    """Locate the repository root by walking up looking for pyproject.toml.

    Resolved, because an MCP server's working directory is not a documented
    contract - the server is spawned by its client, and passing ``--repo-root``
    explicitly is what this function's result is checked against. Falls back to
    the starting directory rather than raising, as the CLI's own walk did.
    """
    candidate = (Path(start) if start is not None else Path.cwd()).resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    return candidate


def require_evidence_root(repository: Repository) -> Path:
    """The evidence root, or a clear refusal.

    The point of use, and the only place the absence of a corpus becomes an
    error. There is no default: one used to point at a sibling checkout that
    was correct only when run from beside it, and a default aimed at a path
    that is not there fails later and less clearly than refusing here.
    """
    if repository.evidence_root is None:
        raise NoEvidenceRoot(
            f"{EVIDENCE_ROOT_ENV_VAR} is not set, and there is no default: "
            "no evidence corpus is currently chosen "
            "(see docs/open-problems.md 2.4). Set it to the absolute path of "
            "an evidence repository to run this command."
        )
    return repository.evidence_root
