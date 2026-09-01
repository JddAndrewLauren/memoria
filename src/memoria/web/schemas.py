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
    apparatus: list[SourceSummary] = []


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
