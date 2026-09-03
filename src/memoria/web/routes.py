"""The HTTP surface #64, #24, #25 and #65 build: list sources, read one source,
raw source, resolve a reference to a citation, search, list subjects, list one
subject's entries - plus one connection fact (locality) and one action (reveal).

Each route calls ``memoria.*`` and shapes the result into a typed response
model - it holds no rule the CLI or the MCP server does not, opens no
SQLite database and reads no evidence file itself
(``test_web_app.py``'s isolation test).
"""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request

import memoria.references as references
from memoria.index import SearchFilters
from memoria.index import search as search_index
from memoria.records import LaunchError, NormalizedRecord, Read, ReadError
from memoria.records import list_sources as list_sources_core
from memoria.records import load as load_source
from memoria.records import read as read_ref
from memoria.records import read_raw_source as read_raw_source_core
from memoria.records import real_paragraphs
from memoria.records import reveal_original_source as reveal_original_source_core
from memoria.repository import NoEvidenceRoot, Repository
from memoria.subjects import load_all_entries, load_all_subjects
from memoria.web.dependencies import get_repository
from memoria.web.schemas import (
    CitationOut,
    EntryListResponse,
    EntrySummary,
    LocalityOut,
    Paragraph,
    RawSourceResponse,
    ReadOverlayOut,
    RevealSourceResponse,
    SearchResponse,
    SearchResultOut,
    SourceDetail,
    SourceListResponse,
    SourceSummary,
    SubjectListResponse,
    SubjectSummary,
)

router = APIRouter()

# A loopback peer address is the one fact an HTTP server can check for
# "is the browser on this machine" without trusting anything the client
# claims - a header is just text the client sent. #65's locality gate.


def _is_local(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        # Not a parseable IP address at all (ASGI test doubles included) -
        # fails closed, same as any other address `is_loopback` says no to.
        return False


def _to_summary(record: NormalizedRecord) -> SourceSummary:
    return SourceSummary(
        id=record.id,
        source_type=record.source_type,
        recorded_date=record.recorded_date,
        event_date=record.event_date,
        date_confidence=record.date_confidence,
        contemporaneous=record.contemporaneous,
        original_file=record.original_file,
        original_locator=record.original_locator,
    )


def _to_detail(record: NormalizedRecord) -> SourceDetail:
    return SourceDetail(
        **_to_summary(record).model_dump(),
        paragraphs=[
            Paragraph(anchor=record.anchor_id(number), text=text)
            for number, text in enumerate(real_paragraphs(record), start=1)
        ],
        # No editorial record is ever linked to the one it annotates today -
        # see SourceDetail.apparatus's docstring.
        apparatus=[],
    )


@router.get("/sources")
def list_sources(
    source_type: str | None = None,
    date_confidence: str | None = None,
    contemporaneous: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    repository: Repository = Depends(get_repository),
) -> SourceListResponse:
    """List sources, filterable and paginated. Frontmatter only."""
    records = list_sources_core(
        repository,
        source_type=source_type,
        date_confidence=date_confidence,
        contemporaneous=contemporaneous,
    )
    page = records[offset : offset + limit]
    return SourceListResponse(
        items=[_to_summary(record) for record in page],
        total=len(records),
        limit=limit,
        offset=offset,
    )


@router.get("/sources/{record_id}")
def read_source(
    record_id: str, repository: Repository = Depends(get_repository)
) -> SourceDetail:
    """Read one source: frontmatter, paragraphs with anchors, apparatus."""
    try:
        record = load_source(repository, record_id)
    except ReadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_detail(record)


@router.get("/sources/{record_id}/raw")
def raw_source(
    record_id: str, repository: Repository = Depends(get_repository)
) -> RawSourceResponse:
    """The un-normalized file this record was normalized from. "Open
    original" (#25).
    """
    try:
        raw = read_raw_source_core(repository, record_id)
    except (ReadError, NoEvidenceRoot) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RawSourceResponse(text=raw.text, original_locator=raw.original_locator)


@router.get("/locality")
def locality(request: Request) -> LocalityOut:
    """Whether this connection is local - the one fact "Reveal in editor"
    (#65) needs to decide whether to exist on this client at all. General
    on purpose: any future locality-gated action reads this same fact
    rather than each route re-deriving it (ADR-0002: no other surface may
    acquire a client-locality condition of its own).
    """
    return LocalityOut(is_local=_is_local(request))


@router.post("/sources/{record_id}/reveal")
def reveal_source(
    record_id: str, request: Request, repository: Repository = Depends(get_repository)
) -> RevealSourceResponse:
    """"Reveal in editor" (#65): launch the un-normalized file this record
    was normalized from in the host's editor or file manager.

    Refused for a non-local request even if the UI never should have shown
    the button that reached this - the server never trusts the client's
    own idea of whether it is local, only the same peer-address check
    ``/locality`` reports. This is what keeps the action purely additive
    (ADR-0002): a hosted client gets a plain 403, never a launch on a
    machine it is not sitting at.

    ``opened: true`` is only ever returned once the launch has actually
    survived its grace period (``records._launch``) - a missing opener
    binary or one that exits immediately both raise ``LaunchError`` here,
    reported as a real error response rather than a 500 traceback or a
    claim this route cannot back up.
    """
    if not _is_local(request):
        raise HTTPException(status_code=403, detail="reveal is local-only")
    try:
        reveal_original_source_core(repository, record_id)
    except (ReadError, NoEvidenceRoot) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LaunchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RevealSourceResponse(opened=True)


def _to_citation(ref: str, result: Read) -> CitationOut:
    return CitationOut(
        ref=ref,
        citation=result.citation,
        text=result.text,
        record=_to_summary(result.record) if result.record is not None else None,
        paragraph=result.paragraph,
        anchor=result.record.anchor_id(result.paragraph)
        if result.record is not None and result.paragraph is not None
        else None,
        overlay=ReadOverlayOut(
            entry_links=result.overlay.entry_links,
            exclusions=result.overlay.exclusions,
            citing_settlements=result.overlay.citing_settlements,
        )
        if result.overlay is not None
        else None,
    )


def _is_citable(reference: references.Reference) -> bool:
    """Whether ``reference`` is one of the two shapes the citation panel
    actually cites - a ``SRC-`` record or paragraph, or a ``SUB-x/y`` entry -
    rather than the wider set ``memoria.records.read`` resolves for the MCP
    tool surface (chapters, sections, changes, sessions, decisions, research
    memos, a bare ``SUB-`` subject, or a repository path). #145: that wider
    contract was never something the panel needed, and left standing it is
    the kind of thing that becomes load-bearing by accident - ``GET
    /api/read?ref=.git/config`` served the file.
    """
    if isinstance(reference, references.SourceReference):
        return True
    return (
        isinstance(reference, references.SubjectReference)
        and reference.entry_slug is not None
    )


@router.get("/read")
def read(ref: str, repository: Repository = Depends(get_repository)) -> CitationOut:
    """Resolve one reference - the slide-over citation panel's read (§19.9).

    Wraps ``memoria.records.read``, the same composed core the MCP tool
    surface's ``read(ref)`` calls, but narrower: a ``SRC-`` paragraph anchor
    (a search hit's or a paragraph's own ``anchor``) serves the cited text,
    its record and its curated-overlay backlinks (#20); a ``SUB-x/y`` entry
    reference - an overlay's own ``entry_links``/``exclusions`` - serves the
    entry's raw text, so a backlink is clickable into the same panel in both
    directions (#25's acceptance criteria) without a second read shape.
    Anything else - including a bare ``SUB-`` subject or a repository path
    that would otherwise resolve - is a 404: this route is not the MCP
    ``read(ref)`` tool and does not owe it the same contract (#145,
    ``_is_citable``). Ledgering the served read is the caller's job
    (``memoria.records.read``'s own docstring) - this route never imports
    ``memoria.ledger``, so an author's own read here writes nothing to
    ``events.jsonl``.
    """
    try:
        reference = references.parse(ref)
    except references.BadReference:
        reference = None
    if reference is not None and not _is_citable(reference):
        raise HTTPException(
            status_code=404,
            detail=f"{ref!r} is not a citable reference: /api/read serves "
            "SRC- records and paragraphs, and SUB-x/y entries, only",
        )
    try:
        result = read_ref(repository, ref)
    except ReadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_citation(ref, result)


@router.get("/subjects")
def list_subjects(repository: Repository = Depends(get_repository)) -> SubjectListResponse:
    """The `SUBJECTS` tree's top level: the subjects on disk, each with its
    entry count computed from the entries actually there (#24) - an
    un-seeded repository (`memoria seed-subjects` never run) is an empty
    list, not an error, the same honesty ``list_sources`` keeps for an
    un-normalized one.
    """
    subjects = load_all_subjects(repository)
    counts: dict[str, int] = {}
    for entry_id in load_all_entries(repository):
        subject_id = entry_id.split("/", 1)[0]
        counts[subject_id] = counts.get(subject_id, 0) + 1
    return SubjectListResponse(
        items=[
            SubjectSummary(id=subject.id, entry_count=counts.get(subject.id, 0))
            for subject in subjects
        ]
    )


@router.get("/subjects/{subject_id}/entries")
def list_entries(
    subject_id: str, repository: Repository = Depends(get_repository)
) -> EntryListResponse:
    """One subject's entries, for the `SUBJECTS` tree's second level."""
    known_ids = {subject.id for subject in load_all_subjects(repository)}
    if subject_id not in known_ids:
        raise HTTPException(status_code=404, detail=f"no such subject: {subject_id}")
    entries = load_all_entries(repository)
    items = [
        EntrySummary(id=entry.id, match_terms=entry.match_terms)
        for entry_id, entry in sorted(entries.items())
        if entry_id.split("/", 1)[0] == subject_id
    ]
    return EntryListResponse(items=items)


@router.get("/search")
def search(
    q: str,
    event_date: str | None = None,
    recorded_date: str | None = None,
    source_type: str | None = None,
    contemporaneous: bool | None = None,
    repository: Repository = Depends(get_repository),
) -> SearchResponse:
    """Full-text search, wrapping ``memoria.index.search`` (#12).

    The route applies no filter of its own: ``SearchFilters`` is built here
    only to carry the query params across the boundary, and every hit is
    ``memoria.index.search``'s own result, unmodified - no hydration, no SQL,
    written in this package (#64's acceptance criteria).

    ``snippet=True`` is the one thing this route asks for that the MCP tool
    does not: the search dialog draws a fragment per hit (part 19 §19.8) and
    the core computes it, so the adapter still opens no database and reads no
    evidence. It is a locator, not evidence - #95.
    """
    filters = SearchFilters(
        event_date=event_date,
        recorded_date=recorded_date,
        source_type=source_type,
        contemporaneous=contemporaneous,
    )
    results = search_index(repository, q, filters, snippet=True)
    return SearchResponse(
        results=[
            SearchResultOut(
                src_id=result.src_id,
                anchor=result.anchor,
                source_type=result.source_type,
                snippet=result.snippet,
            )
            for result in results
        ]
    )
