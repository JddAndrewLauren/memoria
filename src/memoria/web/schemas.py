"""Typed response models for the JSON API.

Declared explicitly, per #64's acceptance criteria, so the OpenAPI schema is
complete rather than inferred - the source ``ui/`` generates its TypeScript
client types from. Field names mirror ``docs/normalized-record-schema.md``
verbatim; nothing here invents a field the schema does not have.
"""

from __future__ import annotations

from pydantic import BaseModel


class SourceSummary(BaseModel):
    """One record's frontmatter, and nothing else - the list view's row.

    "List sources... Returns frontmatter only, never bodies" (#64): the
    paragraphs a record carries are not on this model, only on
    ``SourceDetail``.
    """

    id: str
    source_type: str
    recorded_date: str
    event_date: str
    date_confidence: str
    contemporaneous: bool
    original_file: str
    original_locator: str


class Paragraph(BaseModel):
    """One paragraph, carrying the stable anchor ``read(ref)`` accepts.

    ``anchor`` comes from ``NormalizedRecord.anchor_id()`` - never
    re-derived as a string (#64's "where the fields come from").
    """

    anchor: str
    text: str


class EditorialRecordOut(BaseModel):
    """One piece of editorial apparatus, linked to the paragraph it
    annotates (#25's "what the data actually is").

    ``editorial_type`` is one of ``footnote``, ``bracketed-span``,
    ``interpolation`` or ``introduction``; a consumer renders whatever value
    is actually present rather than assuming that list is closed, the same
    posture ``SourceSummary.source_type`` already takes. ``retrospective``
    marks apparatus added after the fact, distinct from the evidence it
    annotates. ``linked_record_id``/``linked_anchor`` name the paragraph it
    attaches to - never inline in that paragraph's own text (§6).
    """

    editorial_type: str
    retrospective: bool
    linked_record_id: str
    linked_anchor: str
    text: str


class SourceDetail(SourceSummary):
    """A source read in full: frontmatter, verbatim paragraphs, apparatus.

    ``apparatus`` is the linked editorial apparatus - footnotes, bracketed
    asides, interpolations, editors' introductions - as a **separate
    collection**, never interleaved into ``paragraphs`` (§6). It is always
    empty today: nothing produces editorial records or links them to the
    record they annotate yet (``memoria.index``'s note on ``source_type``),
    so this field exists to be filled once that linkage does, not to be
    faked in the meantime.
    """

    paragraphs: list[Paragraph]
    apparatus: list[EditorialRecordOut] = []


class SourceListResponse(BaseModel):
    """A page of ``list sources`` - paginated, per the acceptance criterion.

    ``is_built`` is whether ``memoria normalize`` has produced anything here
    (``memoria.records.is_normalized``). It is what makes an empty ``items``
    readable: empty and ``false`` is an un-normalized checkout and the client
    should name the command to run; empty and ``true`` is a corpus that
    genuinely holds no sources. ADR-0004's "the empty corpus becomes a
    value" - this is the part of the value that says which state it is in
    (#157). The same field name appears on ``SubjectListResponse`` and
    ``SearchResponse``, each reporting its own build step.
    """

    items: list[SourceSummary]
    total: int
    limit: int
    offset: int
    is_built: bool


class RawSourceResponse(BaseModel):
    """The un-normalized file at ``original_file``, served as text.

    ``original_locator`` is printed and never parsed - a pointer a person
    follows, not an offset (docs/normalized-record-schema.md).
    """

    text: str
    original_locator: str


class LocalityOut(BaseModel):
    """Whether this connection's client is on the same machine as the
    server.

    "Reveal in editor" (#65)'s one locality fact - general on purpose, per
    ``docs/adr/0002-ui-is-a-react-client.md``'s "no other surface may
    acquire a client-locality condition" of its own: any future
    locality-gated action reads this same field rather than deriving one.
    """

    is_local: bool


class RevealSourceResponse(BaseModel):
    """Confirms "Reveal in editor" (#65) launched.

    Carries no other state - the editor or file manager runs on the host,
    outside this response.
    """

    opened: bool


class ReadOverlayOut(BaseModel):
    """The curated overlay a decorated paragraph read carries (#20):
    mirrors ``memoria.index.ReadOverlay`` field for field. ``citing_settlements``
    is always empty in this build - settlements have no durable storage yet
    (#20's own docstring) - and stays on the shape rather than being dropped,
    the same forward-compatibility call ``ReadOverlay`` itself makes.
    """

    entry_links: list[str]
    exclusions: list[str]
    citing_settlements: list[str]


class CitationOut(BaseModel):
    """One resolved reference - the slide-over citation panel's read (§19.9).

    The single generic read the panel uses in both directions: a ``SRC-``
    paragraph anchor serves the cited text, its record and its backlinks
    (``overlay``); a ``SUB-x/y`` entry reference serves the entry's own text,
    with ``record``/``paragraph``/``overlay`` all ``None`` - a backlink is
    clickable into the same panel, and the panel does not need a second shape
    to render it (#25's "traverse in both directions"). Wraps
    ``memoria.records.read``, the same composed core the MCP tool surface
    calls, but narrower: only those two reference kinds resolve, and a bare
    ``SUB-`` subject or a repository path is a 404 (#145) - so this is the
    one generic reference read the viewer has, never a second one duplicating
    ``/sources/{id}`` or a browse over the repository.

    ``anchor`` is the cited paragraph's own stable anchor, from
    ``NormalizedRecord.anchor_id()`` - served, not reconstructed client-side,
    the same "no reconstruction by the caller" discipline
    ``docs/tool-surface.md`` already holds for a search hit's anchor.
    ``None`` whenever ``paragraph`` is, the same pairing.

    ``EntryDetail`` is **not** a second copy of this for entries, and the two
    are not collapsible (#157). Reading ``SUB-x/y`` here serves the entry's
    raw text for the panel and nothing else - no ``match_terms``, no badges,
    no curated overlay. The entry read serves the entry's own shape. Both
    exist because they answer different questions, and #25's one generic
    reference read stays exactly as it is.
    """

    ref: str
    citation: str
    text: str
    record: SourceSummary | None = None
    paragraph: int | None = None
    anchor: str | None = None
    overlay: ReadOverlayOut | None = None


class SubjectSummary(BaseModel):
    """One subject - the `SUBJECTS` tree's top level (#24).

    ``entry_count`` is computed from the entries actually on disk, never
    hardcoded (#24's acceptance criteria) - the same discipline
    ``SourceListResponse.total`` keeps for sources.
    """

    id: str
    entry_count: int


class SubjectListResponse(BaseModel):
    """The `SUBJECTS` tree's top level.

    ``is_built`` is whether ``memoria seed-subjects`` has run
    (``memoria.subjects.is_seeded``) - the same field, and the same
    distinction, as ``SourceListResponse.is_built``, reporting a different
    build step (#157). It reports the ``subjects/`` directory's existence
    rather than its contents, so a directory holding no subject prompts
    reads as built-and-empty; ``is_seeded`` records why.
    """

    items: list[SubjectSummary]
    is_built: bool


class EntrySummary(BaseModel):
    """One entry under a subject - CONTEXT.md's vocabulary, not "item" or
    "record" (#24's acceptance criteria)."""

    id: str
    match_terms: list[str]


class EntryListResponse(BaseModel):
    """One subject's entries, for the `SUBJECTS` tree's second level.

    Carries no ``is_built``, and the omission is a decision rather than an
    oversight (#157): a subject that exists with no entries is genuinely
    empty. There is no third state to report, so there is no flag.
    """

    items: list[EntrySummary]


class StatementOut(BaseModel):
    """One paragraph of an entry body, with its badge if it has one -
    mirrors ``memoria.subjects.Statement`` field for field.

    ``badge`` is ``None`` for author testimony, and that is not a missing
    value: **the absence of a badge is the attribution** (part 06 §9.5),
    which is why it is a nullable field on the shape rather than an omitted
    key. A response that dropped it would not be serving the entry.
    Non-null values are ``author``, ``source``, ``inferred`` and ``open``; a
    client renders whatever value is present rather than assuming that list
    is closed, the same posture ``SourceSummary.source_type`` takes.
    """

    badge: str | None = None
    text: str


class OverlayActOut(BaseModel):
    """One pin or exclusion recorded on an entry (#157's entry read).

    **Not ``ReadOverlayOut``**, which sits a few models above under a
    confusingly similar name and is a different concept: that one mirrors
    ``memoria.index.ReadOverlay`` and carries the
    ``entry_links``/``exclusions``/``citing_settlements`` a *paragraph* read
    is decorated with (#20). This one is an attributable author act stored
    on the entry file itself - part 04 §42's "never regenerated", which
    survives the index being deleted outright.

    ``actor_name`` is served and ``actor_email`` is not. The address was
    withheld with the name when this model was written (#157) on the
    grounds that nothing in the client attributed a pin to a person; the
    entry view is that consumer, and part 06 §8.3 requires the overlay to be
    *attributable* on the surface that renders it - a gathered-set row
    marked "excluded" without saying by whom is an unexplained absence. The
    address stays withheld: ADR-0002 forbids assuming the browser and the
    repository share a machine, and an email crossing that boundary is a
    liability that no rendering needs.
    """

    anchor: str
    action: str
    actor_name: str
    at: str


class EntryDetail(EntrySummary):
    """One entry read whole - #64's third subject read, built here (#148,
    #157).

    Distinct from ``GET /api/read?ref=SUB-x/y`` (#25's ``CitationOut``),
    which serves the entry's raw file verbatim, frontmatter included - the
    MCP tool surface's "the entry, verbatim" contract
    (``docs/tool-surface.md``), reached through a reference for the
    slide-over citation panel's backlink navigation. This is the `SUBJECTS`
    tree's own read, shaped like its ``SubjectSummary``/``EntrySummary``
    siblings rather than conflated with that one.

    ``statements`` is the body split by ``memoria.subjects.parse_statements``:
    Memoria's badged statements and the author's unbadged testimony are
    shared territory in the same body (part 06 §8.2), and splitting them is
    what keeps them distinguishable rather than merely visually different.

    Neither ``extra`` nor the raw ``body`` is here. ``extra`` exists so a
    rewrite does not drop an unmodelled frontmatter key (``Entry.extra``),
    not to be published; the parsed statements are the served form of the
    body, and a client that wants the markdown is asking for the file rather
    than for the entry.

    ``token`` is ``memoria.write.serve``'s content hash of the entry file as
    it was served (ADR-0003 decision 1), opaque to the client and presented
    back on a match-term write. This is where the staleness token first
    crosses HTTP: entry files are editable in Obsidian too, so a write has
    to be checked against the file the client actually read rather than
    against whatever is on disk when it arrives.
    """

    statements: list[StatementOut]
    overlay: list[OverlayActOut] = []
    token: str


class GatheredSourceOut(BaseModel):
    """One paragraph in an entry's gathered set (part 06 §8.3), with the
    author's overlay act over it if there is one.

    ``anchor`` is the whole address a reader needs - it is what
    ``/api/read`` resolves - because the gathered set has no stable ID of
    its own: it is derived, asserts nothing, and nothing outside it ever
    names one (``memoria.index.GatheredSource``).

    ``pinned`` is ``gather``'s own flag - membership. ``overlay_action`` and
    the two fields after it are the *act* behind it, read off the entry
    file: ``"pin"``, ``"exclude"``, or ``None`` where the pass alone
    accounts for the row. Both are served because they answer different
    questions and an excluded anchor is not in ``items`` at all - see
    ``GatheredSetResponse``.
    """

    src_id: str
    anchor: str
    pinned: bool
    overlay_action: str | None = None
    actor_name: str | None = None
    at: str | None = None


class GatheredSetResponse(BaseModel):
    """An entry's gathered set, and the exclusions kept out of it.

    ``items`` is ``memoria.index.gather``'s result, which has already
    applied the overlay: a pinned anchor is in it whatever the pass found,
    and an excluded one is gone. ``excluded`` carries those removed acts
    separately, because an exclusion the surface cannot render is an author
    act with nothing to show for it - the reader sees a shorter list and no
    reason for it.

    ``is_built`` is ``memoria.index.is_built``, the same field and the same
    meaning as on ``SearchResponse``: an empty gathered set with it false
    means the corpus was never indexed, which is a different fact from an
    entry nothing matched. An entry with an empty gathered set is a valid
    state either way (part 06 §8.2), never an error.
    """

    items: list[GatheredSourceOut]
    excluded: list[OverlayActOut] = []
    is_built: bool


class AppearanceOut(BaseModel):
    """One manuscript passage an entry turns out to touch (part 06 §8.11).

    ``note`` names the match term that found it. No pin or exclude field
    here, unlike ``GatheredSourceOut``, and that is the design rather than
    an omission: an author act against one passage would be a durable
    pointer into mutable prose, which part 04 §4.1 forbids.
    """

    src_id: str
    anchor: str
    note: str


class AppearancesResponse(BaseModel):
    """An entry's appearances, and whether an engine could produce any.

    Kept in its own response rather than folded onto ``EntryDetail``
    alongside the gathered set, because part 06 §8.11's separation is the
    point: a gathered set is evidence to write *from*, appearances are prose
    already written, and merging them would put manuscript text into what a
    writing agent reads as material.

    ``engine_supported`` is ``memoria.index.appearances_supported``. False
    for Themes and Arcs, whose engine waits for the audit at M5 - without
    it, an empty list says "nothing appears" when the truth is "nothing has
    looked yet".

    ``is_built`` reports ``memoria rebuild``, as elsewhere.
    """

    items: list[AppearanceOut]
    is_built: bool
    engine_supported: bool


class MatchTermsUpdate(BaseModel):
    """A match-term write: the terms to store, and the token the entry was
    served with (ADR-0003).

    The token is the whole staleness check from the client's side - it
    presents back what ``EntryDetail`` gave it, unread and unmodified, and a
    file changed underneath since then is rejected rather than merged.
    """

    token: str
    match_terms: list[str]


class MatchTermsResponse(BaseModel):
    """What an accepted match-term write stored, and a fresh token.

    The new token is served so the editor stays usable without a reload:
    the file it holds a token for has just changed - by its own write - so
    the one it presented is now stale by construction.
    """

    match_terms: list[str]
    token: str


class SearchResultOut(BaseModel):
    """One search hit: the ``SRC-`` ID, the paragraph anchor, and a snippet.

    ``memoria.index.SearchResult`` carries no paragraph text and this route
    serves none either, for the same reason ``search_text`` (#12) does not -
    see ``docs/tool-surface.md``'s "search_text(query, filters)" section,
    "What it returns", which is where that constraint is recorded.

    ``snippet`` is not that text. It is the match locator #95 settled on: a
    truncated fragment of the index's copy, matched terms wrapped in
    ``index.SNIPPET_MATCH_START``/``_END``, for drawing a hit row (part 19
    §19.8). A client splits on those marks; it never renders the snippet as
    markup, and it never feeds it to ``read``. Evidence arrives when the
    reader clicks the hit and the slide-over reads ``anchor`` (§19.9).

    Every field of ``index.SearchResult`` has a counterpart here, and
    ``test_web_app.py`` fails if one stops having one - the generated-types
    check cannot see a field the core has and this model dropped, because
    the schema stays self-consistent, just impoverished.
    """

    src_id: str
    anchor: str
    source_type: str
    snippet: str | None = None


class SearchResponse(BaseModel):
    """A page of hits.

    ``is_built`` is whether ``memoria rebuild`` has produced an index
    (``memoria.index.is_built``) - the same field as on
    ``SourceListResponse`` and ``SubjectListResponse``, reporting the third
    build step (#157). No results with ``is_built`` false means the corpus
    was never indexed, which is a different fact from nothing matching, and
    the two are the same empty list without it.
    """

    results: list[SearchResultOut]
    is_built: bool


# --- the manuscript: outline, Section, Review (#43) ---------------------------


class OutlineSectionOut(BaseModel):
    """One section row of the `MANUSCRIPT` tree. ``excerpt`` is the first
    line of the brief, shortened - a brief has no title field (part 04
    §2.1), so the tree shows its prose rather than inventing a name.
    ``has_draft`` tells a planned section (brief written, draft empty -
    CONTEXT.md's "Outline") from one with prose."""

    id: str
    number: int
    excerpt: str
    has_draft: bool


class OutlineChapterOut(BaseModel):
    id: str
    number: int
    excerpt: str
    sections: list[OutlineSectionOut]


class ManuscriptOutline(BaseModel):
    """The `MANUSCRIPT` tree: the ordered tree of chapters and sections,
    which *is* the outline - there is no outline file (part 04 §2.1).
    ``is_built`` is whether ``chapters/`` exists at all, the same
    "which empty is this" flag the other three trees carry (#157)."""

    chapters: list[OutlineChapterOut]
    is_built: bool


class NotCurrentOut(BaseModel):
    """One not-current judgement against a paragraph: the entry it was
    checked against, the judgement kind (``engagement`` or
    ``audit_verdict``), and the cause - one of ``memoria.audit``'s
    ``STALENESS_CAUSES``, rendered as it is rather than mapped."""

    entry_id: str
    kind: str
    cause: str


class SectionParagraphOut(BaseModel):
    """One draft paragraph, positionally numbered for this read only (part
    04 §4.1: no durable identity), with every not-current judgement the
    staleness map holds against it - what the surface tints, and why."""

    index: int
    text: str
    not_current: list[NotCurrentOut]


class ScopeEntryOut(BaseModel):
    """One entry the brief's declared scope resolved to, and which of its
    match terms (or its own name) the brief text contains - the "how" half
    of ``memoria.scope.ScopeResolution``'s report."""

    entry_id: str
    matched_by: list[str]


class DecisionOut(BaseModel):
    id: str
    text: str
    citation: str


class QuestionOut(BaseModel):
    text: str
    citation: str


class SectionView(BaseModel):
    """The Section surface (part 19 §19.5 as amended by §19.11): the brief
    (``PURPOSE`` - the one card that reads a file), the draft with its
    not-current tint, the entries in scope, and the decisions and open
    questions composed from the sessions that touched this section.

    No ``checkpoint``, no ``next``, no ``impacts`` field, and never will be:
    those are withdrawn state (part 12 §39), not empty state.
    ``sessions`` names the session records the decisions and questions
    were composed from, so the composition is legible on the surface.
    """

    id: str
    chapter_id: str
    chapter_number: int
    section_number: int
    brief: str
    unconfirmed: bool
    has_draft: bool
    paragraphs: list[SectionParagraphOut]
    scope: list[ScopeEntryOut]
    scope_empty: bool
    sessions: list[str]
    decisions: list[DecisionOut]
    questions: list[QuestionOut]


class DisagreementMemberOut(BaseModel):
    """One member of a finding's disagreement set - ``kind`` is one of
    ``passage``, ``entry``, ``source``, ``decision``, ``brief``; ``ref`` is
    that kind's own reference form (``memoria.audit.DisagreementMember``)."""

    kind: str
    ref: str


class FindingOut(BaseModel):
    """One finding, as the audit recorded it (part 06 §8.10): a disagreement
    set, prose stating how they disagree, a confidence, the subject that
    raised it, and an optional proposed rewrite. ``resolutions`` is read off
    the set's shape by ``Finding.available_resolutions`` - never stored,
    never a category. ``paragraph_index``/``paragraph_text`` locate it for
    this read only."""

    paragraph_index: int
    paragraph_text: str
    entry_id: str
    subject_id: str
    confidence: str
    statement: str
    disagreement_set: list[DisagreementMemberOut]
    resolutions: list[str]
    patch: str | None = None


class ReviewOut(BaseModel):
    """The Review surface: the results of an audit the author ran on one
    section, and nothing else (part 19 §19.11's amendment of §19.3).

    ``findings`` is ordered by confidence. ``verdicts_current`` and
    ``verdicts_not_current`` count the section's (paragraph, entry) audit
    verdicts on each side of the staleness map: zero current is a section
    no audit has been run over, which the surface tells apart from an audit
    that found nothing. ``token`` is the draft's staleness token for
    ``PUT .../paragraphs/{index}`` to present back; ``None`` when the
    section has no draft.
    """

    section_id: str
    chapter_number: int
    section_number: int
    findings: list[FindingOut]
    verdicts_current: int
    verdicts_not_current: int
    token: str | None = None


class RewriteUpdate(BaseModel):
    """The author applying a proposed rewrite to one paragraph - the
    interface act part 10 §19.3 names as authorization (``Apply``). ``token``
    is what ``ReviewOut`` served, presented back unread (ADR-0003)."""

    token: str
    text: str


class RewriteResponse(BaseModel):
    """What an accepted rewrite wrote, and a fresh token for the draft the
    write has just changed."""

    paragraph_index: int
    text: str
    token: str


class AssembledEntryOut(BaseModel):
    """One entry the declared scope resolved to: which phrase named it, and
    its gathered set's anchors - the sources behind it, as identifiers only
    (assembly reports a gathered set, it does not load one; #38)."""

    entry_id: str
    matched_by: list[str]
    sources: list[str]


class FallbackOut(BaseModel):
    """A phrase the scope named that resolved to no entry, and the
    unpromoted candidate assembly fell back to - named, never silent
    (part 06 §8.4)."""

    subject_id: str
    candidate_id: str
    label: str


class ServedSinceOut(BaseModel):
    """One read the tool surface served after assembly: the tool, the
    reference it was asked for (a ``read``), and the references it served."""

    tool: str
    ref: str | None = None
    served: list[str]


class SessionSuppliedContextOut(BaseModel):
    """The supplied context for one session on one section (#61,
    ADR-0001): the working context assembly produced - ``briefs``,
    ``entries``, ``fallbacks`` - and, apart from it, ``served_since``.

    An account of what Memoria *supplied*, in countable domain units:
    briefs, entries, fallbacks and the references served. No field here
    is, or will be, a size or capacity figure of any kind - the ledger's
    measurement belongs to the context manifest (#29), a development
    instrument, and no code path runs from it to this model (ADR-0001).
    """

    session_id: str
    assembled_at: str
    briefs: list[str]
    entries: list[AssembledEntryOut]
    fallbacks: list[FallbackOut]
    unconfirmed: bool
    empty: bool
    served_since: list[ServedSinceOut]


class SuppliedContextOut(BaseModel):
    """The supplied-context surface for one section: one account per
    session that assembled it, latest assembly first."""

    section_id: str
    sessions: list[SessionSuppliedContextOut]
