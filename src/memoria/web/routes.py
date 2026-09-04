"""The HTTP surface #64, #24, #25, #65, #148, #157 and #26 build: list sources,
read one source, raw source, resolve a reference to a citation, search, list
subjects, list one subject's entries, read one entry with its gathered set and
its appearances, edit an entry's match terms - plus one connection fact
(locality) and one action (reveal).

Each route calls ``memoria.*`` and shapes the result into a typed response
model - it holds no rule the CLI or the MCP server does not, opens no
SQLite database and reads no evidence file itself
(``test_web_app.py``'s isolation test).

#26 makes this an adapter over the *write* path as well as the read side,
which is why ``memoria.write`` is here: a match-term write is the author's
first durable write (ADR-0003). The rule stays the same - the route resolves
no path, hashes no file and never touches one; ``memoria.subjects`` owns all
three and this shapes its answer.
"""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request

import memoria.drivers as drivers
import memoria.references as references
from memoria.extraction import status as extraction_status
from memoria.model import (
    ModelError,
    ModelFn,
    ModelSettings,
    ModelUnavailable,
    load_settings,
    readiness,
    require_model,
    save_settings,
)
from memoria.index import IndexBuildError, IndexSchemaError, SearchFilters
from memoria.ingestion import RawUnitError, RawUnitExists, RunInProgress, ingestion_status
from memoria.ingestion import add_raw_unit as add_raw_unit_core
from memoria.ingestion import run_normalize as run_normalize_core
from memoria.ingestion import run_rebuild as run_rebuild_core
from memoria.index import appearances_supported
from memoria.index import gather as gather_set
from memoria.index import is_built as index_is_built
from memoria.index import list_appearances
from memoria.index import search as search_index
from memoria.records import LaunchError, NormalizedRecord, Read, ReadError
from memoria.records import is_normalized
from memoria.records import list_sources as list_sources_core
from memoria.records import load as load_source
from memoria.records import read as read_ref
from memoria.records import read_raw_source as read_raw_source_core
from memoria.records import real_paragraphs
from memoria.records import reveal_original_source as reveal_original_source_core
from memoria.grill import GrillError
from memoria.manuscript import (
    ManuscriptError,
    add_draft,
    add_section,
    brief_from_prose,
    plan_section,
)
from memoria.repository import NoEvidenceRoot, Repository
from memoria.review import (
    ReviewError,
    SettlementError,
    apply_rewrite,
    review_section,
    settle_finding,
)
from memoria.section import compose_section, locate_section, outline as manuscript_outline
from memoria.style import (
    StyleError,
    WritingStyle,
    add_sample,
    confirm_observation,
    discard_observation,
    list_samples,
    pending_observations,
    serve_style,
    set_style,
    status as style_status,
)
from memoria.supplied_context import supplied_context as compose_supplied_context
from memoria.subjects import (
    Entry,
    OverlayAct,
    SubjectError,
    add_subject,
    is_seeded,
    load_all_entries,
    load_all_subjects,
    load_entry,
    parse_statements,
    serve_entry,
    set_match_terms,
)
from memoria.web.dependencies import get_repository, get_session_id
from memoria.web.schemas import (
    AuditRunOut,
    AuditRunRequest,
    ExtractionRunOut,
    GrillOut,
    GrillRequest,
    SectionCreate,
    SectionCreated,
    ExtractionStatusOut,
    ModelSettingsOut,
    ModelSettingsUpdate,
    RejectionOut,
    RunRequest,
    SpendOut,
    StyleRunOut,
    SettleRequest,
    SettlementOut,
    AppearanceOut,
    AppearancesResponse,
    AssembledEntryOut,
    CitationOut,
    DecisionOut,
    DisagreementMemberOut,
    EntryDetail,
    EntryListResponse,
    EntrySummary,
    FallbackOut,
    FindingOut,
    GatheredSetResponse,
    GatheredSourceOut,
    LocalityOut,
    ManuscriptOutline,
    MatchTermsResponse,
    MatchTermsUpdate,
    NotCurrentOut,
    ObservationResolution,
    RawUnitOut,
    RawUnitUpload,
    SampleUpload,
    StyleObservationOut,
    StyleOut,
    StyleSampleOut,
    StyleUpdate,
    OutlineChapterOut,
    OutlineSectionOut,
    OverlayActOut,
    Paragraph,
    QuestionOut,
    RawSourceResponse,
    ReadOverlayOut,
    RevealSourceResponse,
    ReviewOut,
    RewriteResponse,
    RewriteUpdate,
    ScopeEntryOut,
    SearchResponse,
    SearchResultOut,
    SectionParagraphOut,
    SectionView,
    ServedSinceOut,
    SessionSuppliedContextOut,
    SourceDetail,
    SourceListResponse,
    SourceSummary,
    StatementOut,
    SubjectCreate,
    SubjectCreated,
    SubjectListResponse,
    SubjectSummary,
    SuppliedContextOut,
    IngestionRunOut,
    IngestionStatusOut,
    UnitStatusOut,
)
from memoria.write import Rejected, WriteError, repository_actor

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
        is_built=is_normalized(repository),
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


@router.get("/ingestion")
def ingestion(repository: Repository = Depends(get_repository)) -> IngestionStatusOut:
    """Every raw unit in the ledger with its conversion, index and
    extraction state - derived from the ledger, the records and the index,
    never recorded (part 05 §5.4). ``memoria.ingestion`` computes it; this
    shapes it.
    """
    status = ingestion_status(repository)
    return IngestionStatusOut(
        units=(
            None
            if status.units is None
            else [
                UnitStatusOut(
                    id=unit.id,
                    path=unit.path,
                    deleted=unit.deleted,
                    converted=unit.converted,
                    failure_reason=unit.failure_reason,
                    record_paragraphs=unit.record_paragraphs,
                    indexed_paragraphs=unit.indexed_paragraphs,
                    extracted_paragraphs=unit.extracted_paragraphs,
                    email_message_index=unit.email_message_index,
                )
                for unit in status.units
            ]
        ),
        counts=dict(status.counts),
        unnumbered=None if status.unnumbered is None else list(status.unnumbered),
        is_normalized=status.is_normalized,
        is_indexed=status.is_indexed,
        generated_at=status.generated_at,
    )


@router.post("/ingestion/normalize")
def ingestion_normalize(
    request: Request, repository: Repository = Depends(get_repository)
) -> IngestionRunOut:
    """Run one normalization pass (ADR-0011): the same pass ``memoria
    normalize`` runs, on the author's own machine only - the same peer
    check ``reveal`` makes, for the same reason. Synchronous: the response
    is the pass's report. A 409 is another pass already running.
    """
    if not _is_local(request):
        raise HTTPException(status_code=403, detail="normalize is local-only")
    try:
        outcome = run_normalize_core(repository)
    except NoEvidenceRoot as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestionRunOut(
        kind=outcome.kind, summary=outcome.summary, elapsed_seconds=outcome.elapsed_seconds
    )


@router.post("/ingestion/rebuild")
def ingestion_rebuild(
    request: Request, repository: Repository = Depends(get_repository)
) -> IngestionRunOut:
    """Regenerate the index from the records on disk (ADR-0011), with no
    embedder - ``memoria rebuild`` remains the path that loads the model
    (ADR-0007). Local-only and synchronous, as ``/ingestion/normalize``.
    """
    if not _is_local(request):
        raise HTTPException(status_code=403, detail="rebuild is local-only")
    try:
        outcome = run_rebuild_core(repository)
    except RunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IndexBuildError, IndexSchemaError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return IngestionRunOut(
        kind=outcome.kind, summary=outcome.summary, elapsed_seconds=outcome.elapsed_seconds
    )


@router.post("/ingestion/units")
def ingestion_add_unit(
    upload: RawUnitUpload, repository: Repository = Depends(get_repository)
) -> RawUnitOut:
    """Place one raw unit's bytes under ``raw/`` (ADR-0013). Not local-only:
    the bytes travel, so this works hosted; only the normalize that numbers
    the unit is local. Mints nothing - the next normalize does (ADR-0006).
    **409** for a path already taken (nothing overwritten), **400** for a
    path that is absolute, climbs out of ``raw/`` or names a dotfile,
    **404** when no evidence corpus is configured."""
    try:
        added = add_raw_unit_core(repository, upload.path, bytes(upload.content))
    except NoEvidenceRoot as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RawUnitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RawUnitExists as exc:
        raise HTTPException(
            status_code=409,
            detail=f"{exc.path} already exists - nothing was written. Rename the file and try again.",
        ) from exc
    return RawUnitOut(path=added.path, size=added.size)


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
    actually cites - a ``SRC-`` record or paragraph, a ``SUB-x/y`` entry, or
    (#34) one ``SES-...#T`` transcript turn - rather than the wider set ``memoria.records.read`` resolves for the MCP
    tool surface (chapters, sections, changes, sessions, decisions, research
    memos, a bare ``SUB-`` subject, or a repository path). #145: that wider
    contract was never something the panel needed, and left standing it is
    the kind of thing that becomes load-bearing by accident - ``GET
    /api/read?ref=.git/config`` served the file.
    """
    if isinstance(reference, references.SourceReference):
        return True
    if isinstance(reference, references.SubjectReference):
        return reference.entry_slug is not None
    # #34: a decision or question cites `SES-...#T017`, and the Section
    # view's "see the exact turn" is this panel opening on that turn. A
    # *bare* session stays refused - the panel cites what was said in one
    # turn, never a whole transcript with its manifest.
    return isinstance(reference, references.SessionReference) and reference.turn is not None


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
            "SRC- records and paragraphs, SUB-x/y entries, and SES-...#T turns, only",
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
    un-normalized one - and since #157 an empty list that says which of the
    two it is, in ``is_built``.
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
        ],
        is_built=is_seeded(repository),
    )


@router.post("/subjects")
def create_subject(
    body: SubjectCreate, repository: Repository = Depends(get_repository)
) -> SubjectCreated:
    """The author adding a subject from the dialog - ``+ New subject``
    (ADR-0014). One file, ``subjects/<slug>/_subject.md``, one commit
    through the write path's creation door, committed as the author -
    ``repository_actor``, never a name in the payload (ADR-0002) - because
    the click is the act, as it is for ``create_section``.

    **409** for a subject already there (nothing written), **422** for a
    name that makes no id, **500** for a write that cannot be attempted
    (no git identity).
    """
    try:
        subject = add_subject(
            repository,
            body.name,
            match=body.match,
            hazards=body.hazards,
            audit_questions=body.audit_questions,
            auto_promote=body.auto_promote,
            actor=repository_actor(repository),
        )
    except SubjectError as exc:
        status = 409 if "already exists" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SubjectCreated(id=subject.id)


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


def _to_overlay_act(act: OverlayAct) -> OverlayActOut:
    """One pin or exclusion, without the actor's email (``OverlayActOut``)."""
    return OverlayActOut(
        anchor=act.anchor, action=act.action, actor_name=act.actor_name, at=act.at
    )


def _served_entry(repository: Repository, subject_id: str, entry_slug: str) -> tuple[Entry, str]:
    """``serve_entry``, with its 404s shaped - for the read that leads to an
    edit, and so needs a staleness token."""
    try:
        return serve_entry(repository, subject_id, entry_slug)
    except SubjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _loaded_entry(repository: Repository, subject_id: str, entry_slug: str) -> Entry:
    """``load_entry``, with its 404s shaped - for a read that leads to no
    edit, so no token is minted for nobody to hold.

    One ``except`` covers every 404 either read has, because the core raises
    for all three: an unknown subject, an unknown entry, and a
    ``subject_id`` that is not a subject ID at all.
    """
    try:
        return load_entry(repository, subject_id, entry_slug)
    except SubjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/subjects/{subject_id}/entries/{entry_slug}")
def read_entry(
    subject_id: str,
    entry_slug: str,
    repository: Repository = Depends(get_repository),
) -> EntryDetail:
    """One entry read whole - #64's third subject read, built in #157.

    `GET /api/read?ref=SUB-x/y` (#25) serves this same entry, but as the raw
    file verbatim, frontmatter included - the MCP tool surface's "the entry,
    verbatim" contract (`docs/tool-surface.md`), reached through a reference
    for the slide-over citation panel's backlink navigation. That is a
    different read from this one (#148): the `SUBJECTS` tree needs an entry
    shaped like its `list subjects`/`list a subject's entries` siblings -
    parsed fields, not a raw blob - the same way `read_source` parses a record
    into paragraphs rather than pointing callers at `raw_source`.

    Served through ``serve_entry`` rather than ``load_entry`` (#26): the
    author edits match terms from this surface, and ADR-0003's staleness
    check compares against *the file as it was read*, so the token has to be
    minted by the read that produced what is on screen rather than by the
    write that follows it.

    Resolves an entry whose file has been renamed: ``serve_entry`` goes
    through ``find_entry_path``, which falls back to matching the
    frontmatter ``id``, so #16's stable ``SUB-x/y`` IDs survive a rename on
    disk and this route inherits that without repeating it.

    ``extra`` is not served - it exists so a rewrite does not drop an
    unmodelled frontmatter key, not to be published (``EntryDetail``).

    The gathered set and appearances are not here either, and that is the
    §8.11 separation rather than an economy: this is a read of the entry
    *file*, and those two are index reads with their own build signal and
    their own failure. They have their own routes below.
    """
    entry, token = _served_entry(repository, subject_id, entry_slug)
    return EntryDetail(
        id=entry.id,
        match_terms=entry.match_terms,
        statements=[
            StatementOut(badge=statement.badge, text=statement.text)
            for statement in parse_statements(entry.body)
        ],
        overlay=[_to_overlay_act(act) for act in entry.overlay],
        token=token,
    )


@router.get("/subjects/{subject_id}/entries/{entry_slug}/gathered")
def read_gathered_set(
    subject_id: str,
    entry_slug: str,
    repository: Repository = Depends(get_repository),
) -> GatheredSetResponse:
    """An entry's gathered set, with the author's overlay legible on it.

    ``gather`` has already applied the overlay - it drops an excluded anchor
    and adds a pinned one - so membership needs nothing here. What it does
    not carry is the *act*: which anchors the author pinned, who did it and
    when. That is on the entry file (part 04 §42 keeps it there, so it
    survives the index being deleted), and joining the two is this route's
    whole job.

    The exclusions are served separately because they are absent from
    ``items`` by construction. A surface that got only the list would show a
    shorter set with no account of why, which is an author act rendered as
    nothing.
    """
    entry = _loaded_entry(repository, subject_id, entry_slug)
    acts = {act.anchor: act for act in entry.overlay}
    items = []
    for source in gather_set(repository, entry.id):
        act = acts.get(source.anchor)
        items.append(
            GatheredSourceOut(
                src_id=source.src_id,
                anchor=source.anchor,
                pinned=source.pinned,
                overlay_action=act.action if act is not None else None,
                actor_name=act.actor_name if act is not None else None,
                at=act.at if act is not None else None,
            )
        )
    return GatheredSetResponse(
        items=items,
        excluded=[
            _to_overlay_act(act) for act in entry.overlay if act.action == "exclude"
        ],
        is_built=index_is_built(repository),
    )


@router.get("/subjects/{subject_id}/entries/{entry_slug}/appearances")
def read_appearances(
    subject_id: str,
    entry_slug: str,
    repository: Repository = Depends(get_repository),
) -> AppearancesResponse:
    """An entry's appearances - the already-written prose it touches.

    ``engine_supported`` is what stops an empty list from meaning two
    things. For a Person it means the lexical pass found nothing; for a
    Theme or an Arc it means the pass never ran, and will not until the
    audit at M5 (part 06 §8.11). ``memoria.index.appearances_supported``
    decides, the same predicate ``compute_appearances`` skips on.

    The entry is served first so an unknown entry is a 404 here too, rather
    than an empty list for something that does not exist.
    """
    entry = _loaded_entry(repository, subject_id, entry_slug)
    return AppearancesResponse(
        items=[
            AppearanceOut(src_id=item.src_id, anchor=item.anchor, note=item.note)
            for item in list_appearances(repository, entry.id)
        ],
        is_built=index_is_built(repository),
        engine_supported=appearances_supported(entry.id),
    )


@router.put("/subjects/{subject_id}/entries/{entry_slug}/match-terms")
def update_match_terms(
    subject_id: str,
    entry_slug: str,
    update: MatchTermsUpdate,
    repository: Repository = Depends(get_repository),
) -> MatchTermsResponse:
    """Replace an entry's match terms - the first durable write over HTTP.

    Match terms are author-owned (part 06 §8.2), so this commits as the
    author: ``repository_actor`` supplies the identity from the repository's
    own git config, never from the request, because ADR-0002 forbids
    assuming the browser and the repository share a machine and a name in a
    payload is an unverified claim about who acted.

    The three outcomes, each a different status:

    - **409** for a stale token. The file changed since the client read it -
      in Obsidian, or in another tab - and nothing was written, merged or
      partially applied (ADR-0003 decision 1). The client re-reads for the
      current content and a fresh token; this response deliberately carries
      neither (decision 5), because #64 already builds that read.
    - **400** for a malformed match term, refused by ``set_match_terms``
      before the file is touched.
    - **500** for a write that cannot be attempted - no configured git
      identity, or a failing commit.

    On success the *new* token is returned, because the write has just
    invalidated the one the client presented and the editor is still open
    over the file.
    """
    try:
        actor = repository_actor(repository)
        result = set_match_terms(
            repository, subject_id, entry_slug, update.match_terms, update.token, actor
        )
    except SubjectError as exc:
        # An unknown subject or entry is a 404; a malformed match term is a
        # 400. Both arrive as `SubjectError`, and the distinction is which
        # of the two the caller can fix by sending something else.
        status = 404 if str(exc).startswith("no such ") else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(result, Rejected):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{result.path} changed since it was read - nothing was "
                "written. Re-read the entry and try again."
            ),
        )
    entry, token = _served_entry(repository, subject_id, entry_slug)
    return MatchTermsResponse(match_terms=entry.match_terms, token=token)


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

    ``is_built`` reports whether the index exists at all (#157), so a client
    can tell "never indexed" from "nothing matched" - the same empty list
    otherwise.
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
        ],
        is_built=index_is_built(repository),
    )


# --- the manuscript: outline, Section, Review (#43) ---------------------------
#
# Reads plus explicit acts, and no model driver (#43): every route below
# calls ``memoria.section`` or ``memoria.review`` and shapes the value. The
# one write, ``apply_rewrite``, is the author's own act through the single
# write path (ADR-0003), exactly the shape ``update_match_terms`` already
# has. Nothing here can run an audit or record one - ``test_audit.py``'s
# sweep refuses a call to the recording functions from this file.


@router.get("/manuscript")
def read_manuscript(repository: Repository = Depends(get_repository)) -> ManuscriptOutline:
    """The `MANUSCRIPT` tree: chapters and sections in outline order, each
    labelled by its brief's first line. Honest about an empty repository
    through ``is_built`` (#157's convention), the way the other trees are.
    """
    result = manuscript_outline(repository)
    return ManuscriptOutline(
        chapters=[
            OutlineChapterOut(
                id=chapter.id,
                number=chapter.number,
                excerpt=chapter.excerpt,
                sections=[
                    OutlineSectionOut(
                        id=section.id,
                        number=section.number,
                        excerpt=section.excerpt,
                        has_draft=section.has_draft,
                    )
                    for section in chapter.sections
                ],
            )
            for chapter in result.chapters
        ],
        is_built=result.is_built,
    )


@router.get("/sections/{section_id}")
def read_section(
    section_id: str, repository: Repository = Depends(get_repository)
) -> SectionView:
    """The Section surface, composed at this call (part 19 §19.5 / §19.11):
    the brief, the draft with each paragraph's not-current judgements, the
    entries in scope, and the decisions and questions from the sessions
    that touched it. Nothing here is stored section state - see
    ``memoria.section``."""
    try:
        view = compose_section(repository, section_id)
    except ManuscriptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SectionView(
        id=view.id,
        chapter_id=view.chapter_id,
        chapter_number=view.chapter_number,
        section_number=view.section_number,
        brief=view.brief,
        unconfirmed=view.unconfirmed,
        has_draft=view.has_draft,
        paragraphs=[
            SectionParagraphOut(
                index=paragraph.index,
                text=paragraph.text,
                not_current=[
                    NotCurrentOut(entry_id=item.entry_id, kind=item.kind, cause=item.cause)
                    for item in paragraph.not_current
                ],
            )
            for paragraph in view.paragraphs
        ],
        scope=[
            ScopeEntryOut(entry_id=entry.entry_id, matched_by=list(entry.matched_by))
            for entry in view.scope
        ],
        scope_empty=view.scope_empty,
        sessions=list(view.sessions),
        decisions=[
            DecisionOut(id=decision.id, text=decision.text, citation=decision.citation)
            for decision in view.decisions
        ],
        questions=[
            QuestionOut(text=question.text, citation=question.citation)
            for question in view.questions
        ],
    )


@router.get("/sections/{section_id}/review")
def read_review(
    section_id: str, repository: Repository = Depends(get_repository)
) -> ReviewOut:
    """The Review surface: the results of the audit the author ran on this
    section - a read over the verdicts a session recorded, and nothing
    else. Findings arrive as disagreement sets with the resolutions their
    shape admits; the resolution list is read off the set, never a stored
    label (part 06 §8.10)."""
    try:
        review = review_section(repository, section_id)
    except ManuscriptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReviewOut(
        section_id=review.section_id,
        chapter_number=review.chapter_number,
        section_number=review.section_number,
        findings=[
            FindingOut(
                paragraph_index=item.paragraph_index,
                paragraph_text=item.paragraph_text,
                entry_id=item.entry_id,
                subject_id=item.finding.subject_id,
                confidence=item.finding.confidence,
                statement=item.finding.statement,
                disagreement_set=[
                    DisagreementMemberOut(kind=member.kind, ref=member.ref)
                    for member in item.finding.disagreement_set
                ],
                resolutions=list(item.finding.available_resolutions),
                patch=item.finding.patch,
                entry_token=review.entry_staleness.get(item.entry_id),
            )
            for item in review.findings
        ],
        verdicts_current=review.verdicts_current,
        verdicts_not_current=review.verdicts_not_current,
        token=review.token,
        sessions=list(review.sessions),
    )


@router.post("/sections/{section_id}/settlements")
def settle_section_finding(
    section_id: str,
    request: SettleRequest,
    repository: Repository = Depends(get_repository),
) -> SettlementOut:
    """Settle one of this section's findings - the author's explicit act
    from Review (part 06 §8.7: click-authorized), and the surface's second
    write.

    The settlement lands on the entry the finding names, inside its
    audit-visible body, with a claim accreted beside it (#33); the section
    is only where the conflict surfaced, and nothing written points at a
    paragraph. The same three outcomes the rewrite has: **409** when the
    entry changed since Review served its token (nothing written; re-read
    the review for a fresh one), **400** for a settlement the set does not
    admit - a side it does not carry, a brief among its members, an empty
    reason - **404** for a section that does not exist. Commits as the
    author (``repository_actor``, ADR-0002), because the click is the
    authorization.
    """
    try:
        result = settle_finding(
            repository,
            section_id,
            entry_id=request.entry_id,
            disagreement_set=[(member.kind, member.ref) for member in request.disagreement_set],
            side=request.side,
            proposition=request.proposition,
            reason=request.reason,
            session_id=request.session_id,
            entry_token=request.entry_token,
            actor=repository_actor(repository),
        )
    except ManuscriptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ReviewError, SettlementError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(result, Rejected):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{result.path} changed since the review was read - nothing was "
                "written. Re-read the review and settle again."
            ),
        )
    return SettlementOut(
        entry_id=result.entry_id, settled_line=result.settled_line, claim_id=result.claim_id
    )


@router.get("/sections/{section_id}/supplied-context")
def read_supplied_context(
    section_id: str, repository: Repository = Depends(get_repository)
) -> SuppliedContextOut:
    """The supplied-context surface (#61, ADR-0001): for each session that
    assembled this section, what assembly resolved and every read served
    since - composed from the session ledgers at this call, so a surface
    that asks again while open sees what has been served so far. It claims
    what Memoria supplied, in countable domain units, and nothing else."""
    try:
        account = compose_supplied_context(repository, section_id)
    except ManuscriptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SuppliedContextOut(
        section_id=account.section_id,
        sessions=[
            SessionSuppliedContextOut(
                session_id=session.session_id,
                assembled_at=session.assembled_at,
                briefs=list(session.briefs),
                entries=[
                    AssembledEntryOut(
                        entry_id=entry.entry_id,
                        matched_by=list(entry.matched_by),
                        sources=list(entry.sources),
                    )
                    for entry in session.entries
                ],
                fallbacks=[
                    FallbackOut(
                        subject_id=fallback.subject_id,
                        candidate_id=fallback.candidate_id,
                        label=fallback.label,
                    )
                    for fallback in session.fallbacks
                ],
                unconfirmed=session.unconfirmed,
                empty=session.empty,
                served_since=[
                    ServedSinceOut(tool=item.tool, ref=item.ref, served=list(item.served))
                    for item in session.served_since
                ],
            )
            for session in account.sessions
        ],
    )


@router.put("/sections/{section_id}/paragraphs/{paragraph_index}")
def rewrite_paragraph(
    section_id: str,
    paragraph_index: int,
    update: RewriteUpdate,
    repository: Repository = Depends(get_repository),
) -> RewriteResponse:
    """Apply a proposed rewrite to one paragraph of a section's draft - the
    author's explicit act from Review, and the surface's one write.

    Through the single write path (ADR-0003), the same three outcomes
    ``update_match_terms`` has: **409** for a draft changed since Review
    read it (nothing written, nothing merged; the client re-reads for the
    current draft and a fresh token), **400** for a paragraph the draft
    does not have or an empty rewrite, **500** for a write that cannot be
    attempted. Commits as the author - ``repository_actor``, never a name
    in the payload (ADR-0002) - because the click is the authorization
    (part 10 §19.3) and the applied prose is now the author's, the same
    class of thing as an edit made in Obsidian. The only file this can
    reach is ``draft.md``; no route edits a brief.
    """
    try:
        actor = repository_actor(repository)
        result = apply_rewrite(
            repository, section_id, paragraph_index, update.token, update.text, actor
        )
    except ManuscriptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(result, Rejected):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{result.path} changed since it was read - nothing was "
                "written. Re-read the review and try again."
            ),
        )
    review = review_section(repository, section_id)
    return RewriteResponse(
        paragraph_index=paragraph_index,
        text=update.text.strip(),
        token=review.token or "",
    )


# --- the writing style (ADR-0009) -------------------------------------------


def _style_out(repository: Repository) -> StyleOut:
    style, token = serve_style(repository)
    state = style_status(repository)
    current = style or WritingStyle()
    return StyleOut(
        exists=style is not None,
        direction=current.direction,
        observations=list(current.observations),
        sample_sources=list(current.sample_sources),
        samples=[
            StyleSampleOut(path=s.path, title=s.title, original_file=s.original_file)
            for s in list_samples(repository)
        ],
        token=token,
        pending=[
            StyleObservationOut(
                id=o.id, aspect=o.aspect, observation=o.observation, example=o.example
            )
            for o in pending_observations(repository)
        ],
        confirmed_count=state.confirmed,
        discarded_count=state.discarded,
    )


def _stale(result: Rejected) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=(
            f"{result.path} changed since it was read - nothing was written. "
            "Re-read the writing style and try again."
        ),
    )


@router.get("/style")
def read_style(repository: Repository = Depends(get_repository)) -> StyleOut:
    """The writing style, its samples, and the observations awaiting the
    author - the Settings surface's one read. A repository with no style
    yet is an honest empty state with ``exists=False`` and no token."""
    try:
        return _style_out(repository)
    except StyleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/style")
def update_style(
    update: StyleUpdate, repository: Repository = Depends(get_repository)
) -> StyleOut:
    """Replace the writing style - an author act through the single write
    path, committed as the author (``repository_actor``, never a name in
    the payload; ADR-0002). The same outcomes as ``update_match_terms``:
    **409** for a style changed since it was read (or one that appeared
    where the client thought there was none), **400** for a sample source
    that names no record, **500** for a write that cannot be attempted."""
    try:
        actor = repository_actor(repository)
        result = set_style(
            repository,
            WritingStyle(
                direction=update.direction,
                observations=tuple(update.observations),
                sample_sources=tuple(update.sample_sources),
            ),
            update.token,
            actor,
        )
    except StyleError as exc:
        status = 500 if "must be attributed" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(result, Rejected):
        raise _stale(result)
    return _style_out(repository)


@router.post("/style/observations/{observation_id}")
def resolve_style_observation(
    observation_id: int,
    resolution: ObservationResolution,
    repository: Repository = Depends(get_repository),
) -> StyleOut:
    """The author acting on one proposed observation. ``confirm`` appends
    it - as proposed, or as ``text`` where they changed it - to the style
    through the write path first, and only a committed write marks the
    row confirmed; **409** leaves both untouched. ``discard`` marks the
    row and writes nothing durable. An observation that is not proposed,
    or does not exist, is a **404**."""
    try:
        if resolution.action == "discard":
            discard_observation(repository, observation_id)
        else:
            actor = repository_actor(repository)
            result = confirm_observation(
                repository, observation_id, resolution.text, resolution.token, actor
            )
            if isinstance(result, Rejected):
                raise _stale(result)
    except StyleError as exc:
        message = str(exc)
        if message.startswith("no such observation") or "is already" in message:
            status = 404
        elif "must be attributed" in message:
            status = 500
        else:
            status = 400
        raise HTTPException(status_code=status, detail=message) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _style_out(repository)


@router.post("/style/samples")
def upload_style_sample(
    upload: SampleUpload, repository: Repository = Depends(get_repository)
) -> StyleOut:
    """Add one uploaded document as a style sample, written under
    ``style/samples/`` and committed as the author. **409** for a name
    already taken (nothing overwritten), **400** for an unsupported type,
    a document with no text, or a converter this install lacks."""
    try:
        actor = repository_actor(repository)
        result = add_sample(repository, upload.filename, bytes(upload.content), actor)
    except StyleError as exc:
        status = 500 if "must be attributed" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(result, Rejected):
        raise HTTPException(
            status_code=409,
            detail=f"{result.path} already exists - nothing was written. Rename the file and try again.",
        )
    return _style_out(repository)


# --- direct runs (ADR-0010) ------------------------------------------------------
#
# The one class of route that reaches a generative model, and it does so
# through `memoria.model`'s seam at the point of use, never by holding a
# client: `require_model` -> one driver call -> shape the report. Off by
# default - every run route is a 409 naming Settings > Model until the
# author switches direct runs on. The settings file is machine-local
# (beside the index, gitignored), so writing it is not a durable write and
# does not go through `memoria.write`; the core owns the file, this shapes.


def _model_out(repository: Repository) -> ModelSettingsOut:
    state = readiness(repository)
    return ModelSettingsOut(
        enabled=state.enabled,
        provider=state.provider,
        model=state.model,
        effort=state.effort,
        api_key_set=state.api_key_set,
        api_key_source=state.api_key_source,
        ready=state.ready,
        reason=state.reason,
    )


def _model(repository: Repository) -> ModelFn:
    try:
        return require_model(repository)
    except ModelUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _spend(spend: drivers.Spend) -> SpendOut:
    # Calls and model only: part 14 §40 keeps the other figure off this
    # surface (see ``SpendOut``); the ledger holds it.
    return SpendOut(calls=spend.calls, model=spend.model)


def _rejections(rejected: tuple[drivers.Rejection, ...]) -> list[RejectionOut]:
    return [RejectionOut(anchor=item.anchor, reason=item.reason) for item in rejected]


def _provider_failure(exc: ModelError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/model")
def read_model_settings(repository: Repository = Depends(get_repository)) -> ModelSettingsOut:
    """Settings > Model's one read: the switch, the model id, whether a key
    is set and where from, and whether a direct run would succeed. Never
    the key."""
    return _model_out(repository)


@router.put("/model")
def update_model_settings(
    update: ModelSettingsUpdate, repository: Repository = Depends(get_repository)
) -> ModelSettingsOut:
    """The author changing the switch, the model, the effort, or the stored
    key. The provider is fixed to the one this slice ships; ``api_key`` absent
    leaves the stored key alone and empty clears it."""
    current = load_settings(repository)
    if update.api_key is None:
        api_key = current.api_key
    else:
        api_key = update.api_key.strip() or None
    save_settings(
        repository,
        ModelSettings(
            enabled=update.enabled,
            provider=current.provider,
            model=update.model.strip(),
            api_key=api_key,
            effort=update.effort,
        ),
    )
    return _model_out(repository)


@router.get("/extraction")
def read_extraction_status(
    repository: Repository = Depends(get_repository),
) -> ExtractionStatusOut:
    """Where the extraction stands - the numbers Settings shows beside the
    Run button, so the author sees what a run would read before it spends
    anything. A read; nothing here runs."""
    state = extraction_status(repository)
    return ExtractionStatusOut(
        paragraphs=state.paragraphs,
        extracted=state.extracted,
        pending=state.pending,
        candidates_raw=state.candidates_raw,
        candidates_above_threshold=state.candidates_above_threshold,
        unplaced_forms=state.unplaced_forms,
        proposed_match_terms=state.proposed_match_terms,
        clusters=sum(state.clusters_by_level.values()),
        summaries_done=state.summaries_done,
        summaries_pending=state.summaries_pending,
        derived=state.derived,
    )


@router.post("/extraction/run")
def run_extraction(
    request: RunRequest,
    repository: Repository = Depends(get_repository),
    session_id: str = Depends(get_session_id),
) -> ExtractionRunOut:
    """One bounded step of a direct extraction run: up to ``limit``
    paragraphs read and recorded, or - once every paragraph is read - the
    pass closed and up to ``limit`` summaries written. **409** while direct
    runs are off or not ready (the detail names Settings > Model), **502**
    when the provider fails mid-run (what was recorded stays)."""
    model = _model(repository)
    try:
        report = drivers.run_extraction(repository, model, session_id, limit=request.limit)
    except ModelError as exc:
        raise _provider_failure(exc) from exc
    return ExtractionRunOut(
        phase=report.phase,
        paragraphs_read=report.paragraphs_read,
        paragraphs_accepted=report.paragraphs_accepted,
        paragraphs_remaining=report.paragraphs_remaining,
        summaries_written=report.summaries_written,
        summaries_remaining=report.summaries_remaining,
        finished=report.finished,
        promotions=list(report.promotions),
        rejected=_rejections(report.rejected),
        spend=_spend(report.spend),
    )


@router.post("/sections/{section_id}/audit")
def run_audit(
    section_id: str,
    request: AuditRunRequest,
    repository: Repository = Depends(get_repository),
    session_id: str = Depends(get_session_id),
) -> AuditRunOut:
    """The audit's button on a section, or on one paragraph of it
    (CONTEXT.md: "a button on a section or a chapter, or on a highlighted
    passage") - run here, directly. Up to ``limit`` judgements answered
    and recorded per call; the client calls again while ``remaining`` is
    above zero. **404** for a section that is not there, **409** while
    direct runs are off, **502** when the provider fails."""
    try:
        chapter, section = locate_section(repository, section_id)
    except ManuscriptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    model = _model(repository)
    try:
        report = drivers.run_audit(
            repository,
            model,
            session_id,
            chapter_number=chapter.number,
            section_number=section.number,
            paragraph_index=request.paragraph_index,
            limit=request.limit,
        )
    except ModelError as exc:
        raise _provider_failure(exc) from exc
    return AuditRunOut(
        accepted=report.accepted,
        findings=report.findings,
        remaining=report.remaining,
        rejected=_rejections(report.rejected),
        spend=_spend(report.spend),
    )


@router.post("/style/analyse")
def run_style_analysis(
    repository: Repository = Depends(get_repository),
    session_id: str = Depends(get_session_id),
) -> StyleRunOut:
    """Settings > Writing style's "Analyse now": the analysis run here,
    directly, its proposed observations recorded for the author to confirm
    exactly as the skill's ``style_record`` records them. **400** with
    nothing to analyse, **409** while direct runs are off, **502** when the
    provider fails."""
    model = _model(repository)
    try:
        report = drivers.run_style(repository, model, session_id)
    except StyleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelError as exc:
        raise _provider_failure(exc) from exc
    return StyleRunOut(
        accepted=report.accepted,
        rejected=_rejections(report.rejected),
        spend=_spend(report.spend),
        style=_style_out(repository),
    )


# --- a new section (ADR-0012) --------------------------------------------------


@router.post("/chapters/{chapter_id}/sections")
def create_section(
    chapter_id: str,
    body: SectionCreate,
    repository: Repository = Depends(get_repository),
) -> SectionCreated:
    """The author writing a new section from the dialog - "Write now", or
    the draft a grilling ended in, edited and confirmed with a click.

    Appended to ``chapter_id`` (position is the directory number; the
    picker chooses a chapter and nothing finer, ADR-0012). Two files, two
    commits through the single write path (ADR-0003's second door,
    ``write.create``): the brief, then ``draft.md``. Commits as the author -
    ``repository_actor``, never a name in the payload (ADR-0002) - because
    the click is the act, the same as ``rewrite_paragraph``; a grilled
    draft the author read and wrote is theirs, the same class of thing as
    a rewrite they applied from Review. A brief the author did not write is
    the prose's opening, marked unconfirmed (``brief_from_prose``).

    **404** for a chapter no chapter carries, **409** for a file that
    appeared underneath the create, **500** for a write that cannot be
    attempted (no git identity), **422** for empty prose.
    """
    brief_text = body.brief.strip()
    try:
        actor = repository_actor(repository)
        planned = plan_section(repository, chapter_id)
        section = add_section(
            repository,
            planned,
            brief_text or brief_from_prose(body.draft),
            actor,
            unconfirmed=not brief_text,
        )
        add_draft(repository, section, body.draft.strip() + "\n", actor)
    except ManuscriptError as exc:
        # `plan_section` names a chapter that is not there; the two creates
        # name a file that appeared underneath them - the same class of
        # outcome as a stale token, so the same status.
        status = 404 if str(exc).startswith("no such chapter") else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except WriteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SectionCreated(
        id=section.brief.id,
        chapter_id=planned.chapter.brief.id,
        chapter_number=planned.chapter.number,
        section_number=section.number,
        unconfirmed=section.brief.unconfirmed,
    )


@router.post("/grill")
def grill_turn(
    request: GrillRequest,
    repository: Repository = Depends(get_repository),
    session_id: str = Depends(get_session_id),
) -> GrillOut:
    """One interviewer turn of the dialog's "Grill me", run here directly
    (ADR-0010, ADR-0012): the client's whole transcript in, the next
    question - or the brief and the draft, once the understanding is
    shared - out. Nothing is stored between turns; nothing here writes a
    file. The draft goes back to the author to edit and write through
    ``create_section``. **404** for an unknown chapter or source, **409**
    while direct runs are off (the detail names Settings > Model), **502**
    when the provider fails."""
    model = _model(repository)
    try:
        report = drivers.run_grill(
            repository,
            model,
            session_id,
            chapter_id=request.chapter_id,
            source_ref=request.source_ref,
            turns=tuple(drivers.GrillTurn(role=t.role, text=t.text) for t in request.turns),
        )
    except GrillError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelError as exc:
        raise _provider_failure(exc) from exc
    return GrillOut(
        done=report.done,
        question=report.question,
        recommended_answer=report.recommended_answer,
        brief=report.brief,
        draft=report.draft,
        rejected=_rejections(report.rejected),
        spend=_spend(report.spend),
    )
