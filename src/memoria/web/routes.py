"""The four reads #64 builds: list sources, read one source, raw source,
search.

Each route calls ``memoria.*`` and shapes the result into a typed response
model - it holds no rule the CLI or the MCP server does not, opens no
SQLite database and reads no evidence file itself
(``test_web_app.py``'s isolation test). Subjects and entries (#24) are not
here: they wait on #16.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from memoria.index import SearchFilters
from memoria.index import search as search_index
from memoria.records import NormalizedRecord, ReadError
from memoria.records import list_sources as list_sources_core
from memoria.records import load as load_source
from memoria.records import read_raw_source as read_raw_source_core
from memoria.records import real_paragraphs
from memoria.repository import NoEvidenceRoot, Repository
from memoria.web.dependencies import get_repository
from memoria.web.schemas import (
    Paragraph,
    RawSourceResponse,
    SearchResponse,
    SearchResultOut,
    SourceDetail,
    SourceListResponse,
    SourceSummary,
)

router = APIRouter()


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
