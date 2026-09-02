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
    """A page of ``list sources`` - paginated, per the acceptance criterion."""

    items: list[SourceSummary]
    total: int
    limit: int
    offset: int


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
    ``memoria.records.read`` exactly - the same core function the MCP tool
    surface calls - so this is the one generic reference read the viewer has,
    never a second one duplicating ``/sources/{id}``.
    """

    ref: str
    citation: str
    text: str
    record: SourceSummary | None = None
    paragraph: int | None = None
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
    items: list[SubjectSummary]


class EntrySummary(BaseModel):
    """One entry under a subject - CONTEXT.md's vocabulary, not "item" or
    "record" (#24's acceptance criteria)."""

    id: str
    match_terms: list[str]


class EntryListResponse(BaseModel):
    items: list[EntrySummary]


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
    results: list[SearchResultOut]
