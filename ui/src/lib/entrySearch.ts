import type { EntrySummary } from "../api/client";

export interface EntryHit {
  subjectId: string;
  entry: EntrySummary;
  matchedOn: string;
}

/**
 * A case-insensitive substring search over one subject's entries - the
 * `SUBJECTS` half of cross-layer search (#24's acceptance criteria). This
 * is presentation-layer filtering over data already served by the API
 * ("every read goes through the API" - #24), not a re-implementation of
 * the subject system's own matching: that stays in `memoria.subjects` and
 * `memoria.index.gather`, each subject's own hazards and all.
 */
export function searchEntries(subjectId: string, entries: EntrySummary[], query: string): EntryHit[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const hits: EntryHit[] = [];
  for (const entry of entries) {
    const label = entry.id.split("/")[1] ?? entry.id;
    if (label.toLowerCase().includes(needle)) {
      hits.push({ subjectId, entry, matchedOn: label });
      continue;
    }
    const matchedTerm = entry.match_terms.find((term) => term.toLowerCase().includes(needle));
    if (matchedTerm) {
      hits.push({ subjectId, entry, matchedOn: matchedTerm });
    }
  }
  return hits;
}
