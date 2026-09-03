import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { listAllSources, type SourceSummary } from "../api/client";
import { groupSourcesByType } from "../lib/sourceGroups";
import { TreeSection } from "./TreeSection";

export function SourcesTree() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sources"],
    queryFn: listAllSources,
  });
  const groups = data ? groupSourcesByType(data.items) : [];

  return (
    <TreeSection label="Sources">
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
              No sources yet. Run <code className="font-mono">memoria normalize</code> against
              an evidence root, then <code className="font-mono">memoria rebuild</code>.
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
        <SourceGroup key={group.sourceType} sourceType={group.sourceType} sources={group.sources} />
      ))}
    </TreeSection>
  );
}

function SourceGroup({ sourceType, sources }: { sourceType: string; sources: SourceSummary[] }) {
  return (
    <TreeSection label={`${sourceType} · ${sources.length}`} defaultOpen={false}>
      <ul>
        {sources.map((source) => (
          <li key={source.id}>
            <NavLink
              to={`/sources/${source.id}`}
              className={({ isActive }) =>
                `block truncate rounded px-2 py-1 font-mono text-xs ${
                  isActive ? "bg-hover text-ink" : "text-secondary hover:bg-hover hover:text-ink"
                }`
              }
            >
              {source.id}
            </NavLink>
          </li>
        ))}
      </ul>
    </TreeSection>
  );
}
