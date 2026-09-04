import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { listAllSources, readIngestionStatus, type SourceSummary } from "../api/client";
import { drawState, indexByUnitId } from "../lib/ingestion";
import { groupSourcesByType } from "../lib/sourceGroups";
import { TreeSection } from "./TreeSection";
import { useOpenAddRawUnits } from "../lib/addRawUnitsContext";

// The glyph's colour by state tone - the same tokens `Badge` uses, without
// the chip around them, since a tree row has no room for one.
const GLYPH_TONE: Record<string, string> = {
  green: "text-sources",
  amber: "text-amber",
  red: "text-manuscript",
  blue: "text-subjects",
  neutral: "text-muted",
};

export function SourcesTree() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sources"],
    queryFn: listAllSources,
  });
  const groups = data ? groupSourcesByType(data.items) : [];
  // The ingestion status, joined by id: each row carries the glyph for its
  // raw unit's conversion state. Only units with a record are rows here -
  // a failed or unconvertible unit has none - which is what the link at
  // the foot is for.
  const { data: ingestion } = useQuery({
    queryKey: ["ingestion"],
    queryFn: readIngestionStatus,
  });
  const states = indexByUnitId(ingestion);
  const openAddRawUnits = useOpenAddRawUnits();

  return (
    <TreeSection label="Sources" to="/sources">
      {/* ADR-0013: adding raw units from the app - files, a folder, or a
          drop anywhere in the window. */}
      <button
        type="button"
        onClick={() => openAddRawUnits()}
        className="mb-1 block w-full rounded px-2 py-1 text-left text-xs text-secondary hover:bg-hover hover:text-ink"
      >
        + Add sources…
      </button>
      {isLoading && <p className="px-2 py-2 text-xs text-muted">Loading…</p>}
      {isError && <p className="px-2 py-2 text-xs text-muted">Sources could not be loaded.</p>}
      {data && groups.length === 0 && (
        // The honest empty state (#24): gated on the grouped result, not
        // data.items, so a corpus that is all editorial (which
        // groupSourcesByType drops) still gets this message rather than a
        // bare header with nothing under it - see ADR-0004 "the empty
        // corpus becomes a value".
        //
        // Branched on is_built (#157), which is the rest of that value: the
        // "run this" copy is the truth for a checkout where `memoria
        // normalize` never ran, and a lie for one where it ran and found
        // nothing. With the gate on groups rather than items there are three
        // cases, not two - the third is a corpus that holds only editorial.
        <p className="px-2 py-2 text-xs text-muted">
          {!data.is_built ? (
            <>
              No sources yet. Add some above, or run{" "}
              <code className="font-mono">memoria normalize</code> against an evidence root,
              then <code className="font-mono">memoria rebuild</code>.
            </>
          ) : data.items.length === 0 ? (
            <>
              No sources yet. <code className="font-mono">memoria normalize</code> has run and
              produced no records.
            </>
          ) : (
            <>No evidence sources — every record in this corpus is editorial.</>
          )}
        </p>
      )}
      {groups.map((group) => (
        <SourceGroup
          key={group.sourceType}
          sourceType={group.sourceType}
          sources={group.sources}
          states={states}
        />
      ))}
      {/* What the tree cannot show - a file the ledger has not numbered, a
          unit that failed - flagged here, on the Sources page's link. */}
      {ingestion?.units && (ingestion.unnumbered?.length || ingestion.counts.failed > 0) ? (
        <NavLink
          to="/sources"
          className="mt-1 block rounded px-2 py-1 font-mono text-[11px] text-amber hover:bg-hover"
        >
          {[
            ingestion.unnumbered?.length ? `${ingestion.unnumbered.length} not numbered` : null,
            ingestion.counts.failed > 0 ? `${ingestion.counts.failed} failed` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </NavLink>
      ) : null}
    </TreeSection>
  );
}

function SourceGroup({
  sourceType,
  sources,
  states,
}: {
  sourceType: string;
  sources: SourceSummary[];
  states: ReturnType<typeof indexByUnitId>;
}) {
  return (
    <TreeSection label={`${sourceType} · ${sources.length}`} defaultOpen={false}>
      <ul>
        {sources.map((source) => {
          const unit = states.get(source.id);
          const drawing = unit ? drawState(unit.converted) : null;
          return (
            <li key={source.id}>
              <NavLink
                to={`/sources/${source.id}`}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 truncate rounded px-2 py-1 font-mono text-xs ${
                    isActive ? "bg-hover text-ink" : "text-secondary hover:bg-hover hover:text-ink"
                  }`
                }
              >
                {drawing && (
                  <span
                    role="img"
                    aria-label={drawing.label}
                    title={drawing.label}
                    className={`w-3 text-center text-[10px] ${GLYPH_TONE[drawing.tone]}`}
                  >
                    {drawing.glyph}
                  </span>
                )}
                {source.id}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </TreeSection>
  );
}
