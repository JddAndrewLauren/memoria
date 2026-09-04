import { useState } from "react";
import { Link } from "react-router-dom";
import type { IngestionStatusOut, UnitStatusOut } from "../api/client";
import { drawState } from "../lib/ingestion";
import { buildRawTree, pruneRawTree, type RawFile, type RawFolder } from "../lib/rawTree";

const GLYPH_TONE: Record<string, string> = {
  green: "text-sources",
  amber: "text-amber",
  red: "text-manuscript",
  blue: "text-subjects",
  neutral: "text-muted",
};

/**
 * The archive as the author put it there: every file under `raw/`, in its
 * folders, whether or not the ledger has numbered it - the one view where a
 * file that is neither a record nor a ledger row (added, fetched, or copied
 * in, with no normalize since) is visible by name. Derived from the
 * ingestion status (ADR-0013's `unnumbered` beside the units).
 */
export function RawFileTree({ status }: { status: IngestionStatusOut }) {
  const [filter, setFilter] = useState("");
  const tree = buildRawTree(status);
  const shown = pruneRawTree(tree, filter);

  if (tree.files === 0) {
    return (
      <p className="mt-6 max-w-[640px] text-xs text-muted">
        Nothing under <code className="font-mono">raw/</code> yet. Add sources above, or drop files
        or folders anywhere in the window.
      </p>
    );
  }
  return (
    <div className="mt-4">
      <input
        type="search"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        placeholder="Filter by path"
        aria-label="Filter by path"
        className="mb-3 w-[320px] max-w-full rounded border border-border bg-card px-2 py-1 text-xs text-ink placeholder:text-muted"
      />
      {shown === null ? (
        <p className="text-xs text-muted">No file matches.</p>
      ) : (
        <ul className="font-mono text-[12px]">
          {shown.children.map((child) =>
            child.kind === "folder" ? (
              <Folder
                key={child.path}
                folder={child}
                depth={0}
                open={depth0Open(shown)}
                forceOpen={Boolean(filter.trim())}
              />
            ) : (
              <File key={child.path} file={child} depth={0} />
            ),
          )}
        </ul>
      )}
    </div>
  );
}

// Top-level folders start open when there are few of them.
function depth0Open(root: RawFolder): boolean {
  return root.children.filter((c) => c.kind === "folder").length <= 3;
}

// A folder remembers its fold, except while a filter is on: the matches
// are the point then, so every folder on the way to one stands open.
function Folder({
  folder,
  depth,
  open: initiallyOpen,
  forceOpen,
}: {
  folder: RawFolder;
  depth: number;
  open: boolean;
  forceOpen: boolean;
}) {
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = forceOpen || (toggled ?? initiallyOpen);
  const setOpen = (update: (value: boolean) => boolean) => setToggled(update(open));
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded px-2 py-0.5 text-left text-body hover:bg-hover"
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        <span className="w-3 text-muted" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="text-ink">{folder.name}/</span>
        <span className="text-[11px] text-muted">
          {folder.files}
          {folder.waiting > 0 && <span className="text-amber"> · {folder.waiting} not numbered</span>}
        </span>
      </button>
      {open && (
        <ul>
          {folder.children.map((child) =>
            child.kind === "folder" ? (
              <Folder key={child.path} folder={child} depth={depth + 1} open={false} forceOpen={forceOpen} />
            ) : (
              <File key={child.path} file={child} depth={depth + 1} />
            ),
          )}
        </ul>
      )}
    </li>
  );
}

function File({ file, depth }: { file: RawFile; depth: number }) {
  const records = file.units.filter((u) => u.record_paragraphs !== null);
  const lead = file.units.find((u) => u.converted !== "container") ?? file.units[0];
  const drawing = lead ? drawState(lead.converted) : null;
  return (
    <li
      className="flex items-center gap-2 rounded px-2 py-0.5 text-body hover:bg-hover"
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      <span className="w-3" aria-hidden="true" />
      {drawing ? (
        <span className={`w-3 ${GLYPH_TONE[drawing.tone]}`} title={drawing.label} aria-label={drawing.label}>
          {drawing.glyph}
        </span>
      ) : (
        <span className="w-3 text-amber" title="not numbered yet" aria-label="not numbered yet">
          ○
        </span>
      )}
      <span className="min-w-0 truncate" title={file.path}>
        {file.name}
      </span>
      <span className="ml-auto shrink-0 text-[11px] text-muted">
        {file.units.length === 0 ? (
          "not numbered yet"
        ) : records.length === 0 ? (
          `${lead.id} · ${drawing?.label}`
        ) : (
          <UnitLinks units={records} />
        )}
      </span>
    </li>
  );
}

// A record's id links to its source page; an email export with many
// messages shows the first few and the count.
function UnitLinks({ units }: { units: UnitStatusOut[] }) {
  const shown = units.slice(0, 3);
  return (
    <>
      {shown.map((unit, index) => (
        <span key={unit.id}>
          {index > 0 && " · "}
          <Link to={`/sources/${unit.id}`} className="text-ink underline decoration-border hover:decoration-ink">
            {unit.id}
          </Link>
        </span>
      ))}
      {units.length > shown.length && ` · ${units.length} messages`}
    </>
  );
}
