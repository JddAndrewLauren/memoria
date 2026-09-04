"""Context manifests (#29, part 07 §10.3, part 11 §33).

A session's manifest is the record of what Memoria actually supplied to
it: which records were loaded, which entries were resolved, which searches
ran, and - the useful part - which of a search's hits were never followed
up by a read. It is a **projection of `events.jsonl`** (#13), never a
separate declaration of intent: nothing here is invented, and a session
that ran no tool call gets an empty manifest rather than a stale one.

``scope_resolutions`` is a different kind of entry than the rest: not a read
or a search, but ``memoria.assembly.assemble``'s own report of what a
declared scope resolved to (#38, §33.1) - which entries, their gathered
sets' sources, and which unpromoted candidates it fell back to. Recorded
here rather than on the section itself, per CONTEXT.md's "Declared scope":
"the resolution is never written back onto the section."

**The completeness claim is conditioned on the routed layout** (§33).
`events.jsonl` records every read and search the tool surface served; it
says nothing about a read made some other way - a development session
working directly in this repository, or Bash going around the tools. The
manifest states that basis explicitly (``BASIS`` below) rather than
claiming more than the routing can support.

**Token counts are a development instrument, never an author-facing
figure** (ADR-0001, part 14 §40). They are measured once, at the moment a
read is served (``memoria.ledger.append_read``), and carried on the
ledger line itself - not re-derived here from whatever the evidence looks
like by the time the manifest is built - so a count always describes what
was actually supplied, not a later edit. This module only aggregates them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from memoria import references
from memoria.repository import Repository
from memoria.sessions import SessionError, session_dir

MANIFEST_FILENAME = "context-manifest.json"

BASIS = (
    "Recorded from events.jsonl: every read and search the tool surface "
    "served to this session (§10.4). This claims tool-mediated retrieval "
    "only - a read made outside the routed layout (a development session "
    "working directly in this repository, or Bash going around the tools) "
    "is not recorded here, and this manifest makes no claim about it (§33)."
)


@dataclass(frozen=True)
class ManifestResult:
    """What ``derive_context_manifest`` did, for a caller to report - the
    same shape ``sessions.DerivationResult`` gives ``derive_session``."""

    session_id: str
    manifest_path: Path
    changed: bool


def manifest_path(repository: Repository, session_id: str) -> Path:
    """Where this session's manifest lives - beside ``events.jsonl`` and
    ``transcript.md`` (part 04 §2)."""
    return session_dir(repository, session_id) / MANIFEST_FILENAME


def build_context_manifest(repository: Repository, session_id: str) -> dict:
    """Project this session's ``events.jsonl`` into the manifest shape.

    A pure function of the ledger: rebuildable at any point in a session's
    life, and always exactly what has been served so far - which is what
    lets ``memoria.records.read`` surface it live, with no dependency on a
    prior derivation having run.
    """
    events = _load_events(repository, session_id)

    records_loaded: list[dict] = []
    entries_resolved: list[dict] = []
    other_reads: list[dict] = []
    read_records: set[str] = set()
    read_paragraphs: set[tuple[str, int]] = set()

    for event in events:
        if event.get("tool") != "read":
            continue
        ref = event.get("ref", "")
        served = event.get("served") or []
        citation = served[0] if served else ref
        item = {"ref": citation, "tokens": event.get("tokens", 0)}
        try:
            reference = references.parse(ref)
        except references.BadReference:
            other_reads.append(item)
            continue
        if isinstance(reference, references.SourceReference):
            records_loaded.append(item)
            if reference.paragraph is None:
                read_records.add(reference.record_id)
            else:
                read_paragraphs.add((reference.record_id, reference.paragraph))
        elif isinstance(reference, references.SubjectReference):
            entries_resolved.append(item)
        else:
            other_reads.append(item)

    scope_resolutions: list[dict] = [
        {
            "entries": event.get("entries", []),
            "fallbacks": event.get("fallbacks", []),
            "unconfirmed": event.get("unconfirmed", False),
            "empty": event.get("empty", False),
            # The style file assembly loaded as voice guidance (ADR-0009),
            # or None - a fact about what was supplied, never its text.
            "writing_style": event.get("writing_style"),
        }
        for event in events
        if event.get("tool") == "assemble"
    ]

    searches: list[dict] = []
    for event in events:
        tool = event.get("tool")
        if tool not in ("search_text", "search_global"):
            continue
        results = [
            {"anchor": anchor, "read": _anchor_was_read(anchor, read_records, read_paragraphs)}
            for anchor in (event.get("served") or [])
        ]
        entry = {
            "tool": tool,
            "query": event.get("query"),
            "filters": event.get("filters"),
            "results": results,
        }
        if tool == "search_global":
            entry["summarize"] = event.get("summarize")
            entry["summary_served"] = event.get("summary_served")
            entry["clusters"] = event.get("clusters", [])
        searches.append(entry)

    return {
        "session_id": session_id,
        "basis": BASIS,
        "records_loaded": records_loaded,
        "entries_resolved": entries_resolved,
        "other_reads": other_reads,
        "searches": searches,
        "scope_resolutions": scope_resolutions,
    }


def _anchor_was_read(
    anchor: str, read_records: set[str], read_paragraphs: set[tuple[str, int]]
) -> bool:
    """Whether a searched paragraph was also read - directly, or as part of
    a whole-record read that necessarily served it too. Anything that never
    appears here at all (no search hit, no read) is simply absent from the
    manifest: material never reached, distinguished from this by presence
    rather than by a flag."""
    try:
        record_id, paragraph = references.split_anchor(anchor)
    except references.BadReference:
        return False
    return record_id in read_records or (record_id, paragraph) in read_paragraphs


def derive_context_manifest(repository: Repository, session_id: str) -> ManifestResult:
    """Write ``context-manifest.json``, the durable form of
    ``build_context_manifest``.

    Refuses rather than overwrites when a prior derivation's file does not
    match this one byte for byte - the same immutability
    ``sessions.derive_session`` holds transcripts to (part 04 §3), for the
    same reason: a session's record does not silently change under a
    reader. Returns ``changed=False`` on an exact no-op re-derivation.
    """
    manifest = build_context_manifest(repository, session_id)
    text = json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    path = manifest_path(repository, session_id)

    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing != text:
            raise SessionError(
                f"{session_id}: {MANIFEST_FILENAME} already exists and "
                "differs from this derivation - session records are "
                "immutable once derived (part 04 §3)"
            )
        return ManifestResult(session_id, path, False)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return ManifestResult(session_id, path, True)


def _load_events(repository: Repository, session_id: str) -> list[dict]:
    """Every line of this session's ``events.jsonl``, or none for a session
    that has not served anything yet. Same shape as
    ``sessions._load_events``, duplicated rather than imported: importing
    ``sessions`` here is already a one-way dependency (records.py needs
    both), and reaching back into its private helper would make that
    dependency two things instead of one."""
    path = session_dir(repository, session_id) / "events.jsonl"
    if not path.is_file():
        return []
    parsed = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SessionError(f"{path}: line {number} is not valid JSON ({exc})") from exc
    return parsed
