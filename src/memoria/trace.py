"""``trace(ref)``: write-time provenance, composed rather than stored (#42,
part 04 §4.1, part 10 §20, part 11 §26).

Why does a paragraph say what it says? Nothing durable points at a
paragraph of manuscript prose (§4.1), so nothing here is looked up - the
chain is reassembled on demand from facts that already exist:

    paragraph  --git blame-->            the commit(s) that last touched its lines
    commit     --commit trailers-->      human (change-id) or AI (authorized-by)
    AI commit  --authorized-by-->        the session, and the turn that authorized it
    session    --transcript.md #T-->     what the author actually said
    session    --events.jsonl (§33)-->   the context manifest: what was loaded to write from

The turn is the answer to "why": it is where the author said "rewrite it
using the corrected timeline". The manifest is the answer to "from what".
A human commit stops at its ``CHG-`` id - what changed is in the commit,
and Memoria must not invent why it changed (part 07 §40).

**The accepted cost is that blame coarsens under reflow.** ``git blame`` is
always right about which commit last touched a line and can be coarse about
which paragraph that line belongs to: a human rewrap after an AI rewrite
attributes every rewrapped line to the rewrap, and the AI commit drops out
of the paragraph's chain. That loses precision, never correctness - the
rewrap *is* the last thing that touched those lines - and a test pins the
behaviour so the loss is documented rather than discovered. Part 10 §20
names the falsifying observation: blame attributing a paragraph so badly
that provenance misleads.

Uncommitted lines (an edit not yet checkpointed) have no commit to walk
from; they are counted, not traced.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from memoria import authorship, context_manifest, references, sessions
from memoria.changes import CHANGE_ID_TRAILER
from memoria.repository import Repository

_UNCOMMITTED_SHA = "0" * 40
_BLAME_LINE = re.compile(r"^(?P<sha>[0-9a-f]{40}) \d+ \d+(?: \d+)?$")
_CHANGE_ID_LINE = re.compile(rf"^{CHANGE_ID_TRAILER}: (?P<id>CHG-\d{{8}}-\d{{3}})$", re.MULTILINE)
_AUTHORIZED_BY_LINE = re.compile(
    rf"^{authorship.AUTHORIZED_BY_TRAILER}: (?P<citation>\S+)$", re.MULTILINE
)
_AUTHORIZED_SCOPE_LINE = re.compile(
    rf"^{authorship.AUTHORIZED_SCOPE_TRAILER}: (?P<scope>.+)$", re.MULTILINE
)


class TraceError(Exception):
    """Raised when a reference cannot be traced - not a paragraph of prose,
    a section or paragraph that does not exist, or git failing outright."""


@dataclass(frozen=True)
class TraceStep:
    """One commit in a paragraph's blame, and what it composes to.

    ``change_id`` is set for a human-authored commit (ADR-0008) and the AI
    fields are ``None``. For an AI manuscript commit ``authorized_by`` is the
    ``SES-...#T`` citation its trailer names and ``authorized_scope`` what
    that write covered; ``authorizing_turn`` is that turn's text when the
    session's transcript has been derived, ``None`` before; and
    ``assembled_from`` is what the session's context manifest says was
    loaded - entries resolved, then records loaded - empty when the session
    has no ledger.
    """

    sha: str
    date: str
    author: str
    lines: int
    change_id: str | None = None
    authorized_by: str | None = None
    authorized_scope: str | None = None
    authorizing_turn: str | None = None
    assembled_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class Trace:
    """A paragraph's provenance: the paragraph as it is now, and the commits
    that last touched its lines, most recent first."""

    citation: str
    path: str
    text: str
    steps: tuple[TraceStep, ...]
    uncommitted_lines: int


def trace(repository: Repository, ref: str) -> Trace:
    """Compose the provenance of one paragraph of manuscript prose.

    ``ref`` is a section paragraph - ``SEC-0001 ¶7`` or ``SEC-0001 P7``
    (``memoria.references``). Anything else is a ``TraceError`` naming what
    trace does take: provenance is composed from ``git blame``, and only
    prose has lines to blame.
    """
    try:
        reference = references.parse(ref)
    except references.BadReference as exc:
        raise TraceError(str(exc)) from exc
    if not isinstance(reference, references.SectionReference) or reference.paragraph is None:
        raise TraceError(
            f"trace takes one paragraph of a section's prose (SEC-0001 ¶7), not {ref!r}"
        )
    citation = references.format_citation(reference)

    try:
        _, relative, path = authorship._draft(repository, reference.section_id)
    except authorship.AuthorshipError as exc:
        raise TraceError(str(exc)) from exc
    if not path.is_file():
        raise TraceError(f"{reference.section_id} has no prose yet: no {relative}")
    text = path.read_text(encoding="utf-8")
    spans = authorship.paragraph_spans(text)
    if not 1 <= reference.paragraph <= len(spans):
        raise TraceError(
            f"{reference.section_id} has {len(spans)} paragraph(s); "
            f"there is no ¶{reference.paragraph}"
        )
    start, end = spans[reference.paragraph - 1]
    first_line = text.count("\n", 0, start) + 1
    last_line = text.count("\n", 0, end) + 1

    lines_by_sha = _blame(repository, relative, first_line, last_line)
    uncommitted = lines_by_sha.pop(_UNCOMMITTED_SHA, 0)
    steps = [_step(repository, sha, count) for sha, count in lines_by_sha.items()]
    steps.sort(key=lambda step: step.date, reverse=True)
    return Trace(
        citation=citation,
        path=relative,
        text=text[start:end],
        steps=tuple(steps),
        uncommitted_lines=uncommitted,
    )


# --- git blame, then the commit -------------------------------------------------


def _blame(repository: Repository, relative: str, first: int, last: int) -> dict[str, int]:
    """How many of lines ``first``..``last`` each commit last touched, in
    first-appearance order. Blames the working tree, so an edit not yet
    committed shows as the all-zero sha rather than being read as its last
    commit's. Porcelain output so the sha is unambiguous; ``-w`` so a
    whitespace-only touch does not claim a line. A draft git has never
    seen at all is every line uncommitted."""
    if not _git(repository, ["ls-files", "--", relative]).strip():
        return {_UNCOMMITTED_SHA: last - first + 1}
    output = _git(
        repository,
        ["blame", "--porcelain", "-w", "-L", f"{first},{last}", "--", relative],
    )
    counts: dict[str, int] = {}
    for line in output.splitlines():
        match = _BLAME_LINE.match(line)
        if match:
            sha = match.group("sha")
            counts[sha] = counts.get(sha, 0) + 1
    return counts


def _step(repository: Repository, sha: str, lines: int) -> TraceStep:
    output = _git(
        repository,
        [
            "show", "-s", "--date=format:%Y-%m-%d %H:%M",
            "--format=%h%x1f%ad%x1f%an%x1f%B", sha,
        ],
    )
    short_sha, date, author, body = output.split("\x1f", 3)
    change = _CHANGE_ID_LINE.search(body)
    authorized = _AUTHORIZED_BY_LINE.search(body)
    scope = _AUTHORIZED_SCOPE_LINE.search(body)
    step = TraceStep(
        sha=short_sha,
        date=date,
        author=author,
        lines=lines,
        change_id=change.group("id") if change else None,
        authorized_by=authorized.group("citation") if authorized else None,
        authorized_scope=scope.group("scope") if scope else None,
    )
    if authorized is None:
        return step
    return _compose_session(repository, step)


def _compose_session(repository: Repository, step: TraceStep) -> TraceStep:
    """The session half of the chain: the authorizing turn's text and the
    manifest's loaded references, each best-effort - a session not yet
    derived has no transcript, one that served nothing has no ledger, and
    the commit's own facts are not conditioned on either."""
    try:
        reference = references.parse(step.authorized_by or "")
    except references.BadReference:
        return step
    if not isinstance(reference, references.SessionReference) or reference.turn is None:
        return step

    turn_text = None
    try:
        turn_text = sessions.read_session(repository, reference.session_id, reference.turn)
    except sessions.SessionError:
        pass

    assembled: list[str] = []
    try:
        manifest = context_manifest.build_context_manifest(repository, reference.session_id)
    except sessions.SessionError:
        manifest = None
    if manifest is not None:
        # Entries first, then records (docs/tool-surface.md): what the
        # session read, and what assembly resolved for it - a draft written
        # from the assembled context (#38) was written from the entries and
        # the sources the `assemble` line names, whether or not the session
        # went on to read any of them, so both halves of the manifest count.
        # The M5 gate walk is where the assembled half was found missing.
        entries = [item["ref"] for item in manifest.get("entries_resolved", [])]
        sources = [item["ref"] for item in manifest.get("records_loaded", [])]
        for resolution in manifest.get("scope_resolutions", []):
            for entry in resolution.get("entries", []):
                entries.append(entry.get("entry_id", ""))
                sources.extend(_source_citation(anchor) for anchor in entry.get("sources", []))
        for ref in entries + sources:
            if ref and ref not in assembled:
                assembled.append(ref)

    return TraceStep(
        sha=step.sha,
        date=step.date,
        author=step.author,
        lines=step.lines,
        change_id=step.change_id,
        authorized_by=step.authorized_by,
        authorized_scope=step.authorized_scope,
        authorizing_turn=turn_text,
        assembled_from=tuple(assembled),
    )


def _source_citation(anchor: str) -> str:
    """An assembled entry's source is ledgered as a paragraph anchor
    (``src-000184-p12``); the trace names it the way every other reference
    here is named, as the citation ``read(ref)`` accepts."""
    try:
        return references.format_citation(references.parse(anchor))
    except references.BadReference:
        return anchor


def _git(repository: Repository, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repository.root, capture_output=True, text=True
    )
    if result.returncode != 0:
        reason = " ".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        raise TraceError(f"git {' '.join(args[:1])} failed: {reason}")
    return result.stdout
