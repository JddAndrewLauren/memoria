"""The supplied context, for one section (#61, ADR-0001, part 11 §33.1).

For each session that assembled a section, an account of the **working
context** assembly produced - the brief it loaded, the entries the declared
scope resolved to, the unpromoted candidates it fell back to - and, held
apart from it, **every read served since**. It discharges §33.1's first
obligation, "assembly must report what it resolved", on a surface; the
search half's scope note (§19.2) discharges the same obligation elsewhere.

**A projection of ``events.jsonl``, nothing more** (#13). Assembly ledgers
its resolution against the session and names the section it resolved
(``memoria.ledger.append_assembly``); nothing is written back onto the
section (CONTEXT.md's "Declared scope"), so the ledger line is the only
place the link from a section to the sessions that assembled it exists,
and this module reads it there. Like ``memoria.context_manifest`` it
invents nothing: a section no session has assembled has no account.

**It claims what Memoria supplied, never what a model holds.** The ledger
records reads Memoria served; it cannot record what the client compacted
away. Every field here is therefore an account of what was *served* to the
session, and the name of the thing - "supplied context" - is that
boundary (CONTEXT.md's "Supplied context"; ADR-0001's consequences).

**Countable domain units only.** A ``read`` ledger line carries a token
figure for the context manifest (#29, a development instrument). This
module never copies it: no field of the value below holds a token, byte,
percentage or capacity figure, and ``tests/test_supplied_context.py``
asserts the account of a session whose ledger carries one still does not.
The separation is a file boundary, not a setting (ADR-0001).

**The two halves are kept apart.** ``entries`` and ``fallbacks`` are what
one ``assemble`` call resolved; ``served_since`` is every read the tool
surface served after it - a paragraph, a search's hits, an extraction
batch - as the references it served, never the text. A session that
assembled the same section again is reported once: the latest assembly is
the working context (a re-assembly at the same revision answers the same
way, #38), and ``served_since`` runs from the *first* assembly, so a read
served between two assemblies is not dropped from the account - an account
that under-describes what was supplied is the failure §33 names.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from memoria.manuscript import resolve_section
from memoria.repository import Repository

SESSIONS_RELATIVE_PATH = "sessions"
EVENTS_FILENAME = "events.jsonl"


@dataclass(frozen=True)
class AssembledEntry:
    """One entry the declared scope resolved to, as the ledger recorded it:
    which phrase named it, and its gathered set's anchors - the sources
    behind it, reported as identifiers, never loaded (#38)."""

    entry_id: str
    matched_by: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Fallback:
    """A phrase the scope named that resolved to no entry, and the
    unpromoted candidate assembly fell back to instead - named explicitly,
    never passed over in silence (part 06 §8.4)."""

    subject_id: str
    candidate_id: str
    label: str


@dataclass(frozen=True)
class ServedSince:
    """One read served after assembly: which tool, what reference it was
    asked for (a ``read``), and what it served - the references the ledger
    line carries, which are the same strings ``read(ref)`` accepts."""

    tool: str
    ref: str | None
    served: tuple[str, ...]


@dataclass(frozen=True)
class SessionSuppliedContext:
    """The supplied context for one session on one section: the working
    context assembly produced, then what was served since. ``briefs`` names
    the briefs assembly loaded - the section's own, today the only one
    ``assemble`` reads. ``assembled_at`` is the ledger's own timestamp."""

    session_id: str
    assembled_at: str
    briefs: tuple[str, ...]
    entries: tuple[AssembledEntry, ...]
    fallbacks: tuple[Fallback, ...]
    unconfirmed: bool
    empty: bool
    served_since: tuple[ServedSince, ...]


@dataclass(frozen=True)
class SuppliedContext:
    """Every session that assembled this section, latest assembly first."""

    section_id: str
    sessions: tuple[SessionSuppliedContext, ...]


def _ledgers(repository: Repository) -> list[tuple[Path, list[dict]]]:
    """Every session ledger under ``sessions/``, in either nesting form
    ``memoria.ledger.event_path`` writes. A line that does not parse is
    skipped, not fatal - the same tolerance ``memoria.section`` shows the
    same file."""
    root = repository.root / SESSIONS_RELATIVE_PATH
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.rglob(EVENTS_FILENAME)):
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        found.append((path, events))
    return found


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _account(path: Path, events: list[dict], section_id: str) -> SessionSuppliedContext | None:
    assemblies = [
        (position, event)
        for position, event in enumerate(events)
        if event.get("tool") == "assemble" and event.get("section_id") == section_id
    ]
    if not assemblies:
        return None
    first_position, _ = assemblies[0]
    _, latest = assemblies[-1]

    session_id = next(
        (event["session_id"] for event in events if isinstance(event.get("session_id"), str)),
        path.parent.name,
    )
    served_since = tuple(
        ServedSince(
            tool=str(event.get("tool")),
            ref=event["ref"] if isinstance(event.get("ref"), str) else None,
            served=_strings(event.get("served")),
        )
        for event in events[first_position + 1 :]
        if isinstance(event.get("served"), list)
    )
    return SessionSuppliedContext(
        session_id=session_id,
        assembled_at=str(latest.get("timestamp", "")),
        briefs=(section_id,),
        entries=tuple(
            AssembledEntry(
                entry_id=str(entry.get("entry_id", "")),
                matched_by=_strings(entry.get("matched_by")),
                sources=_strings(entry.get("sources")),
            )
            for entry in latest.get("entries") or []
            if isinstance(entry, dict)
        ),
        fallbacks=tuple(
            Fallback(
                subject_id=str(fallback.get("subject_id", "")),
                candidate_id=str(fallback.get("candidate_id", "")),
                label=str(fallback.get("label", "")),
            )
            for fallback in latest.get("fallbacks") or []
            if isinstance(fallback, dict)
        ),
        unconfirmed=bool(latest.get("unconfirmed", False)),
        empty=bool(latest.get("empty", False)),
        served_since=served_since,
    )


def supplied_context(repository: Repository, section_id: str) -> SuppliedContext:
    """The supplied context for one ``SEC-`` id, composed at this call from
    the ledgers on disk - live: what has been served so far, every time it
    is asked, with nothing cached between calls.

    Raises ``memoria.manuscript.ManuscriptError`` for an id no section
    carries, the same error ``read(SEC-...)`` gives.
    """
    section = resolve_section(repository, section_id)
    accounts = [
        account
        for path, events in _ledgers(repository)
        if (account := _account(path, events, section.brief.id)) is not None
    ]
    accounts.sort(key=lambda account: account.assembled_at, reverse=True)
    return SuppliedContext(section_id=section.brief.id, sessions=tuple(accounts))
