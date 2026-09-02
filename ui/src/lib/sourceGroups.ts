import type { SourceSummary } from "../api/client";

// Editorial records (footnotes, bracketed spans, interpolations, editors'
// introductions) carry this source_type. They are retrospective records
// *about* the evidence (§6 of CONTEXT.md), not evidence themselves, so they
// must never be browsable in SOURCES (#24's acceptance criteria) - they
// surface as apparatus on the record they annotate (#25) and as a distinct
// layer in search (see `searchLayers.ts`).
export const EDITORIAL_SOURCE_TYPE = "editorial";

export interface SourceGroup {
  sourceType: string;
  sources: SourceSummary[];
}

/**
 * Groups sources by the `source_type` values the records actually carry -
 * never a fixed list (#24's acceptance criteria). A group's count is the
 * length of its own bucket, computed here from what `listAllSources`
 * served, never hardcoded and never guessed at when the corpus is empty.
 */
export function groupSourcesByType(sources: SourceSummary[]): SourceGroup[] {
  const groups = new Map<string, SourceSummary[]>();
  for (const source of sources) {
    if (source.source_type === EDITORIAL_SOURCE_TYPE) continue;
    const bucket = groups.get(source.source_type);
    if (bucket) {
      bucket.push(source);
    } else {
      groups.set(source.source_type, [source]);
    }
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([sourceType, groupSources]) => ({ sourceType, sources: groupSources }));
}
