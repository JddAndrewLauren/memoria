import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listSubjects, listEntries, type EntrySummary } from "../api/client";
import { TreeSection } from "./TreeSection";

export function SubjectsTree() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["subjects"],
    queryFn: listSubjects,
  });

  return (
    <TreeSection label="Subjects">
      {isLoading && <p className="px-2 py-2 text-xs text-muted">Loading…</p>}
      {isError && <p className="px-2 py-2 text-xs text-muted">Subjects could not be loaded.</p>}
      {data && data.items.length === 0 && (
        <p className="px-2 py-2 text-xs text-muted">
          No subjects yet. Run <code className="font-mono">memoria seed-subjects</code>.
        </p>
      )}
      {data &&
        data.items.map((subject) => (
          <SubjectRow key={subject.id} id={subject.id} entryCount={subject.entry_count} />
        ))}
    </TreeSection>
  );
}

function SubjectRow({ id, entryCount }: { id: string; entryCount: number }) {
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["entries", id],
    queryFn: () => listEntries(id),
    enabled: open,
  });
  const label = id.replace(/^SUB-/, "");

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-sm capitalize text-body hover:bg-hover"
      >
        <span>{label}</span>
        <span className="font-mono text-[11px] text-muted">{entryCount}</span>
      </button>
      {open && (
        <ul className="ml-3 border-l border-border-faint pl-2">
          {data?.items.length === 0 && <li className="py-1 text-xs text-muted">No entries yet.</li>}
          {data?.items.map((entry) => <EntryRow key={entry.id} entry={entry} />)}
        </ul>
      )}
    </div>
  );
}

function EntryRow({ entry }: { entry: EntrySummary }) {
  const [expanded, setExpanded] = useState(false);
  const label = entry.id.split("/")[1] ?? entry.id;

  return (
    <li>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="block w-full truncate rounded px-1 py-1 text-left text-xs text-secondary hover:bg-hover hover:text-ink"
      >
        {label}
      </button>
      {expanded && (
        <p className="px-1 pb-1 text-[11px] text-muted">
          {entry.match_terms.length > 0
            ? `Match terms: ${entry.match_terms.join(", ")}`
            : "No match terms yet."}
        </p>
      )}
    </li>
  );
}
