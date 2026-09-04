// The ingestion status's pure half: how each conversion state is drawn,
// and the per-unit lookup the SOURCES tree and the source viewer join on.
// Kept out of the components so the mapping is testable without a render
// (the same split `sourceGroups.ts` makes for the tree's grouping).
import type { IngestionStatusOut, UnitStatusOut } from "../api/client";
import type { Tone } from "../components/Badge";

export type StateDrawing = { glyph: string; tone: Tone; label: string };

// One row per state `memoria.ingestion.ConvertedState` names. The labels
// are the author-facing words: "out of date" rather than "stale", "not yet
// converted" rather than "pending" - CONTEXT.md reserves those for the
// manuscript's not-current judgements, and this is a different fact.
const DRAWINGS: Record<string, StateDrawing> = {
  current: { glyph: "●", tone: "green", label: "converted" },
  out_of_date: { glyph: "◐", tone: "amber", label: "out of date" },
  not_yet_converted: { glyph: "○", tone: "neutral", label: "not yet converted" },
  failed: { glyph: "✕", tone: "red", label: "failed" },
  unconvertible: { glyph: "–", tone: "neutral", label: "no converter" },
  container: { glyph: "▤", tone: "neutral", label: "email export" },
  stub: { glyph: "◌", tone: "amber", label: "no paragraphs" },
  deleted: { glyph: "⊘", tone: "neutral", label: "deleted" },
};

// A state this client has no drawing for renders as itself rather than
// vanishing - the server's list is not assumed closed here, the posture
// `SourceSummary.source_type` already takes.
export function drawState(state: string): StateDrawing {
  return DRAWINGS[state] ?? { glyph: "?", tone: "neutral", label: state.replace(/_/g, " ") };
}

// The order the summary chips and the counts line follow: the states an
// author acts on first, the bookkeeping ones last.
export const STATE_ORDER = [
  "current",
  "out_of_date",
  "not_yet_converted",
  "failed",
  "unconvertible",
  "stub",
  "container",
  "deleted",
] as const;

export function indexByUnitId(status: IngestionStatusOut | undefined): Map<string, UnitStatusOut> {
  const byId = new Map<string, UnitStatusOut>();
  for (const unit of status?.units ?? []) byId.set(unit.id, unit);
  return byId;
}

// "12 of 40" for a unit with a record; the honest absence otherwise.
export function extractedLabel(unit: UnitStatusOut): string | null {
  if (unit.record_paragraphs === null || unit.extracted_paragraphs === null) return null;
  return `${unit.extracted_paragraphs} of ${unit.record_paragraphs}`;
}
