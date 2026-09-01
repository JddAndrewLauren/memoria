# Handoff — finish search hydration end to end

Written 2026-09-01, at the close of the #12/#76/#16/#13/#64 batch.

## Goal

`search_text` and `GET /api/search` return *identifiers* today, not evidence
text. Close that, and make sure the web layer cannot silently drop the text
once it exists.

## Why this is a handoff, not a ticket

The hydration shape is undecided and the decision is architectural: whether a
`SearchResult` carries its paragraph text, or whether callers stay obliged to
`read(ref)` each hit. That choice determines the record schema's reach into the
index, so it wants a person, not a brief.

## Member items

1. **Hydration itself** — owned by the open issues #74 / #81. `SearchResult`
   currently carries no text at all (`docs/tool-surface.md`, "What it returns");
   #64's brief assumed otherwise and was corrected by its own 2026-09-01
   amendment. See https://github.com/JddAndrewLauren/memoria/issues/64#issuecomment-5500730927.

2. **The web layer will drop the new field silently.**
   `src/memoria/web/schemas.py`'s `SearchResultOut` enumerates its fields, so
   when hydration adds text the route keeps serving the old shape. The generated
   types staleness check (`tests/test_web_types.py`) will *not* catch it: the
   schema stays self-consistent, just impoverished. Whoever adds the field must
   touch `SearchResultOut` in the same change, and it is worth a test that fails
   when a core `SearchResult` field has no `SearchResultOut` counterpart.

3. **Finish the `Repository` alignment.** `memoria.index.search` now takes the
   frozen `Repository` (ADR-0004), but `build_index` in the same module still
   takes a bare `db_path`. Align it while #74/#81 are already in that file.

## Context to load

- `src/memoria/index.py` — `search`, `SearchFilters`, `filter_predicate`,
  `build_index`, and the plain anchor-keyed `paragraphs` table (#12).
- `src/memoria/web/{routes,schemas}.py` — the pass-through route.
- `docs/tool-surface.md` — `search_text` section, "What it returns".
- `docs/normalized-record-schema.md:50` — `source_type` is open-ended, which is
  why the filters are inclusive exact-match with no negation. "Everything except
  editorial" is no longer expressible in one call; that constraint is inherited
  by anything built on these filters.
- ADR-0004 (frozen `Repository` values), ADR-0007 (embeddings by choice).

## The named missing decision

**Does a search hit carry its text, or a promise of it?** Hydrating in `search`
means the index reaches into record contents on every query; keeping results
thin means every caller pays a `read(ref)` round trip per hit, and the MCP
server's rendering already does exactly that. Decide this before writing code —
both #74/#81 and the web adapter follow from it.
