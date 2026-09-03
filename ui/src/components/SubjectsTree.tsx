import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listSubjects, listEntries, readEntry, type EntrySummary } from "../api/client";
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
        // Branched on is_built (#157): naming the command is only honest
        // when `memoria seed-subjects` has not run. The nested "No entries
        // yet." below carries no such branch on purpose - a subject that
        // exists with no entries is genuinely empty, and EntryListResponse
        // ships no flag.
        <p className="px-2 py-2 text-xs text-muted">
          {!data.is_built ? (
            <>
              No subjects yet. Run <code className="font-mono">memoria seed-subjects</code>.
            </>
          ) : (
            <>
              No subjects yet. <code className="font-mono">subjects/</code> holds no subject
              prompts.
            </>
          )}
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
  const { data, isError } = useQuery({
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
          {isError && <li className="py-1 text-xs text-muted">Entries could not be loaded.</li>}
          {!isError && data?.items.length === 0 && (
            <li className="py-1 text-xs text-muted">No entries yet.</li>
          )}
          {!isError &&
            data?.items.map((entry) => (
              <EntryRow key={entry.id} subjectId={id} entry={entry} />
            ))}
        </ul>
      )}
    </div>
  );
}

function EntryRow({ subjectId, entry }: { subjectId: string; entry: EntrySummary }) {
  const [expanded, setExpanded] = useState(false);
  const label = entry.id.split("/")[1] ?? entry.id;
  const { data, isError } = useQuery({
    queryKey: ["entry", subjectId, label],
    queryFn: () => readEntry(subjectId, label),
    enabled: expanded,
  });

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
        <div className="px-1 pb-1 text-[11px] text-muted">
          <p>
            {entry.match_terms.length > 0
              ? `Match terms: ${entry.match_terms.join(", ")}`
              : "No match terms yet."}
          </p>
          {isError && <p>The entry could not be read.</p>}
          {data?.statements.length === 0 && <p>No statements yet.</p>}
          {data?.statements.map((statement, index) => (
            <p key={index}>
              {statement.badge && (
                <span className="font-mono uppercase">[{statement.badge}] </span>
              )}
              {statement.text}
            </p>
          ))}
        </div>
      )}
    </li>
  );
}
