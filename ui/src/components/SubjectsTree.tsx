import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { listSubjects, listEntries, type EntrySummary } from "../api/client";
import { TreeSection } from "./TreeSection";
import { useNewItems } from "../lib/newItemsContext";

export function SubjectsTree() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["subjects"],
    queryFn: listSubjects,
  });

  const { openNewSubject } = useNewItems();

  return (
    <TreeSection label="Subjects">
      {/* ADR-0014: declaring a subject from the app. */}
      <button
        type="button"
        onClick={openNewSubject}
        className="mb-1 block w-full rounded px-2 py-1 text-left text-xs text-secondary hover:bg-hover hover:text-ink"
      >
        + New subject…
      </button>
      {isLoading && <p className="px-2 py-2 text-xs text-muted">Loading…</p>}
      {isError && (
        <p className="px-2 py-2 text-xs text-muted">
          Subjects could not be loaded.
        </p>
      )}
      {data && data.items.length === 0 && (
        // Branched on is_built (#157): naming the command is only honest
        // when `memoria seed-subjects` has not run. The nested "No entries
        // yet." below carries no such branch on purpose - a subject that
        // exists with no entries is genuinely empty, and EntryListResponse
        // ships no flag.
        <p className="px-2 py-2 text-xs text-muted">
          {!data.is_built ? (
            <>
              No subjects yet. Add one above, or run{" "}
              <code className="font-mono">memoria seed-subjects</code> for the
              five built-ins.
            </>
          ) : (
            <>
              No subjects yet. <code className="font-mono">subjects/</code>{" "}
              holds no subject prompts.
            </>
          )}
        </p>
      )}
      {data &&
        data.items.map((subject) => (
          <SubjectRow
            key={subject.id}
            id={subject.id}
            entryCount={subject.entry_count}
          />
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
          {isError && (
            <li className="py-1 text-xs text-muted">
              Entries could not be loaded.
            </li>
          )}
          {!isError && data?.items.length === 0 && (
            <li className="py-1 text-xs text-muted">No entries yet.</li>
          )}
          {!isError &&
            data?.items.map((entry) => (
              <EntryRow key={entry.id} entry={entry} />
            ))}
        </ul>
      )}
    </div>
  );
}

// A link into the entry view (#26), the way `SourcesTree` links into the
// source viewer. It was an expander showing match terms inline until the
// entry view existed to show them properly; leaving both would give the
// author two places to read the same field and only one place to edit it.
function EntryRow({ entry }: { entry: EntrySummary }) {
  const [subjectId, slug] = entry.id.split("/");

  return (
    <li>
      <NavLink
        to={`/subjects/${subjectId}/entries/${slug}`}
        className={({ isActive }) =>
          `block w-full truncate rounded px-1 py-1 text-left text-xs ${
            isActive
              ? "bg-hover text-ink"
              : "text-secondary hover:bg-hover hover:text-ink"
          }`
        }
      >
        {slug ?? entry.id}
      </NavLink>
    </li>
  );
}
