import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import {
  readManuscript,
  type OutlineChapterOut,
  type OutlineSectionOut,
} from "../api/client";
import { TreeSection } from "./TreeSection";
import { useNewItems } from "../lib/newItemsContext";

/**
 * MANUSCRIPT: the ordered tree of chapters and sections with their briefs,
 * which *is* the outline - there is no outline file (part 04 §2.1). Each
 * row is labelled by its brief's first line, since a brief has no title
 * field. A section links into the Section view (#43). Honest about an
 * empty repository: a missing `chapters/` is "no manuscript yet", a
 * different fact from a book with no chapters (#157's `is_built`).
 */
export function ManuscriptTree() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["manuscript"],
    queryFn: readManuscript,
  });

  const { openNewSection } = useNewItems();

  return (
    <TreeSection label="Manuscript">
      {/* ADR-0014: the same dialog the floating button opens (ADR-0012). */}
      <button
        type="button"
        onClick={openNewSection}
        className="mb-1 block w-full rounded px-2 py-1 text-left text-xs text-secondary hover:bg-hover hover:text-ink"
      >
        + New section…
      </button>
      {isLoading && <p className="px-2 py-2 text-xs text-muted">Loading…</p>}
      {isError && (
        <p className="px-2 py-2 text-xs text-muted">
          The manuscript could not be loaded.
        </p>
      )}
      {data && data.chapters.length === 0 && (
        <p className="px-2 py-2 text-xs text-muted">
          {data.is_built ? (
            <>
              No chapters yet. <code className="font-mono">chapters/</code>{" "}
              holds none.
            </>
          ) : (
            <>
              No manuscript yet — there is no{" "}
              <code className="font-mono">chapters/</code> directory in this
              repository.
            </>
          )}
        </p>
      )}
      {data &&
        data.chapters.map((chapter) => (
          <ChapterRow key={chapter.id} chapter={chapter} />
        ))}
    </TreeSection>
  );
}

function ChapterRow({ chapter }: { chapter: OutlineChapterOut }) {
  const [open, setOpen] = useState(true);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm text-body hover:bg-hover"
      >
        <span className="font-mono text-[11px] text-muted">
          {chapter.number}
        </span>
        <span className="truncate">{chapter.excerpt || chapter.id}</span>
      </button>
      {open && (
        <ul className="ml-3 border-l border-border-faint pl-2">
          {chapter.sections.length === 0 && (
            <li className="py-1 text-xs text-muted">No sections yet.</li>
          )}
          {chapter.sections.map((section) => (
            <SectionRow
              key={section.id}
              chapterNumber={chapter.number}
              section={section}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function SectionRow({
  chapterNumber,
  section,
}: {
  chapterNumber: number;
  section: OutlineSectionOut;
}) {
  return (
    <li>
      <NavLink
        to={`/sections/${section.id}`}
        title={section.id}
        className={({ isActive }) =>
          `flex w-full items-center gap-2 rounded px-1 py-1 text-left text-xs ${
            isActive
              ? "bg-hover text-ink"
              : "text-secondary hover:bg-hover hover:text-ink"
          }`
        }
      >
        <span className="font-mono text-[11px] text-muted">
          {chapterNumber}.{section.number}
        </span>
        <span className="truncate">{section.excerpt || section.id}</span>
        {/* A planned section: brief written, draft empty (CONTEXT.md's
            "Outline") - said, not hidden. */}
        {!section.has_draft && (
          <span className="text-[10px] text-faint">planned</span>
        )}
      </NavLink>
    </li>
  );
}
