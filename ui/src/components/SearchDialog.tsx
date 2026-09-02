import { useEffect, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { listSubjects, listEntries, search } from "../api/client";
import { splitSearchResultsByLayer } from "../lib/searchLayers";
import { searchEntries } from "../lib/entrySearch";
import { splitSnippet } from "../lib/snippet";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { useCitationPanel } from "../lib/citationPanel";

interface SearchDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Cross-layer search (part 19 §19.8, #24's acceptance criteria): SOURCES
 * (evidence by default, editorial voice included only on request and
 * always in its own, visibly distinct group) and SUBJECTS (entries,
 * matched by id or match term). MANUSCRIPT carries no results - it has
 * nothing in it yet.
 */
export function SearchDialog({ open, onClose }: SearchDialogProps) {
  const [query, setQuery] = useState("");
  const [includeEditorial, setIncludeEditorial] = useState(false);
  const debouncedQuery = useDebouncedValue(query, 200);
  const { open: openCitation } = useCitationPanel();

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    if (open) document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const trimmed = debouncedQuery.trim();

  const { data: searchData, isError: searchIsError } = useQuery({
    queryKey: ["search", trimmed],
    queryFn: () => search(trimmed),
    enabled: open && trimmed.length > 0,
  });
  const { evidence, editorial } = splitSearchResultsByLayer(searchData?.results ?? []);
  // #157: no hits over an index that was never built is a different fact
  // from no hits over one that was, and the empty list is the same either
  // way. Guarded on the response having landed, so an in-flight query does
  // not flash "not built" before the answer arrives.
  const indexUnbuilt = searchData && !searchData.is_built ? INDEX_UNBUILT : undefined;

  const { data: subjectsData, isError: subjectsIsError } = useQuery({
    queryKey: ["subjects"],
    queryFn: listSubjects,
    enabled: open,
  });
  const subjects = subjectsData?.items ?? [];
  // The subjects group reads the *subjects* facet, not the index: entry hits
  // are computed here from listSubjects/listEntries and never touch
  // /api/search, so an unbuilt index says nothing about them (#157).
  const subjectsUnseeded = subjectsData && !subjectsData.is_built ? SUBJECTS_UNSEEDED : undefined;
  const entryQueries = useQueries({
    queries: subjects.map((subject) => ({
      queryKey: ["entries", subject.id],
      queryFn: () => listEntries(subject.id),
      enabled: open,
    })),
  });
  const entriesIsError = subjectsIsError || entryQueries.some((query) => query.isError);
  const entryHits =
    trimmed.length === 0
      ? []
      : subjects.flatMap((subject, index) =>
          searchEntries(subject.id, entryQueries[index]?.data?.items ?? [], trimmed),
        );

  if (!open) return null;

  return (
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/40 pt-24"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        onClick={(event) => event.stopPropagation()}
        className="w-[620px] max-w-[90vw] rounded-card border border-border bg-card shadow-lg"
      >
        <div className="border-b border-border p-3">
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search sources and subjects..."
            className="w-full rounded px-2 py-2 text-sm text-ink outline-none placeholder:text-faint"
          />
        </div>
        {trimmed.length === 0 ? (
          <p className="p-4 text-xs text-muted">Start typing to search.</p>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto p-3">
            <ResultGroup
              label="Sources"
              tone="sources"
              count={evidence.length}
              empty="No matching evidence."
              unbuilt={indexUnbuilt}
              isError={searchIsError}
              error="Search could not be completed."
            >
              {evidence.map((hit) => (
                <SourceHitRow
                  key={`${hit.src_id}-${hit.anchor}`}
                  hit={hit}
                  onSelect={() => {
                    // A citation chip's click, per §19.9: opens the
                    // slide-over rather than navigating away, so checking a
                    // hit never costs the reader their place.
                    openCitation(hit.anchor);
                    onClose();
                  }}
                />
              ))}
            </ResultGroup>

            <label className="mb-2 flex items-center gap-2 px-1 text-[11px] text-muted">
              <input
                type="checkbox"
                checked={includeEditorial}
                onChange={(event) => setIncludeEditorial(event.target.checked)}
              />
              Include editorial voice ({editorial.length})
            </label>
            {includeEditorial && (
              <ResultGroup
                label="Editorial"
                tone="amber"
                count={editorial.length}
                empty="No matching editorial commentary."
                unbuilt={indexUnbuilt}
                isError={searchIsError}
                error="Search could not be completed."
              >
                {editorial.map((hit) => (
                  <SourceHitRow
                    key={`${hit.src_id}-${hit.anchor}`}
                    hit={hit}
                    onSelect={() => {
                      openCitation(hit.anchor);
                      onClose();
                    }}
                  />
                ))}
              </ResultGroup>
            )}

            <ResultGroup
              label="Subjects"
              tone="subjects"
              count={entryHits.length}
              empty="No matching entries."
              unbuilt={subjectsUnseeded}
              isError={entriesIsError}
              error="Subjects could not be searched."
            >
              {entryHits.map(({ subjectId, entry, matchedOn }) => (
                <div key={entry.id} className="rounded px-2 py-1.5 text-sm">
                  <span className="font-mono text-xs text-subjects">
                    {subjectId.replace(/^SUB-/, "")}
                  </span>
                  <span className="ml-2 text-ink">{entry.id.split("/")[1] ?? entry.id}</span>
                  <span className="ml-2 text-xs text-muted">matched &quot;{matchedOn}&quot;</span>
                </div>
              ))}
            </ResultGroup>
          </div>
        )}
      </div>
    </div>
  );
}

// The two things a group says when it has nothing to show and the reason is
// not "nothing matched" - module-level so the sources and editorial groups
// cannot drift apart, since one index backs both layers.
const INDEX_UNBUILT = "The index is not built. Run `memoria rebuild`.";
const SUBJECTS_UNSEEDED = "No subjects yet. Run `memoria seed-subjects`.";

function ResultGroup({
  label,
  tone,
  count,
  empty,
  unbuilt,
  isError,
  error,
  children,
}: {
  label: string;
  tone: "sources" | "subjects" | "amber";
  count: number;
  empty: string;
  /** Shown instead of `empty` when the facet behind this group was never
   * built (#157) - undefined when it was, so the normal copy is untouched. */
  unbuilt?: string;
  isError: boolean;
  error: string;
  children: React.ReactNode;
}) {
  const border = { sources: "border-sources", subjects: "border-subjects", amber: "border-amber" }[tone];
  return (
    <div className={`mb-3 rounded border-l-4 ${border} bg-panel`}>
      <div className="flex items-center justify-between px-2 py-1 font-mono text-[11px] uppercase tracking-wide text-secondary">
        <span>{label}</span>
        <span>{count}</span>
      </div>
      {isError ? (
        <p className="px-2 pb-2 text-xs text-muted">{error}</p>
      ) : unbuilt ? (
        <p className="px-2 pb-2 text-xs text-muted">{unbuilt}</p>
      ) : count === 0 ? (
        <p className="px-2 pb-2 text-xs text-muted">{empty}</p>
      ) : (
        <div className="pb-1">{children}</div>
      )}
    </div>
  );
}

function SourceHitRow({
  hit,
  onSelect,
}: {
  hit: { src_id: string; anchor: string; source_type: string; snippet?: string | null };
  onSelect: () => void;
}) {
  const paragraphNumber = hit.anchor.split("-p").pop();
  return (
    <button
      type="button"
      onClick={onSelect}
      className="block w-full px-2 py-1.5 text-left text-sm hover:bg-hover"
    >
      <span className="font-mono text-xs text-ink">
        {hit.src_id} P{paragraphNumber}
      </span>
      {hit.snippet && (
        <span className="ml-2 text-xs text-secondary">
          {splitSnippet(hit.snippet).map((part, index) =>
            part.matched ? (
              <mark key={index} className="bg-amber-tint text-ink">
                {part.text}
              </mark>
            ) : (
              <span key={index}>{part.text}</span>
            ),
          )}
        </span>
      )}
    </button>
  );
}
