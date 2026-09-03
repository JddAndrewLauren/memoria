import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { readRef, type CitationOut } from "../api/client";
import { Badge } from "./Badge";
import { CitationPanelContext, useCitationPanel, type CitationPanelApi } from "../lib/citationPanel";

/**
 * Owns the slide-over's state - a small stack of references, last pushed is
 * current - and provides `useCitationPanel()` to every descendant: the
 * search dialog's source hits, the source viewer's backlinks rail, and the
 * panel's own backlinks all open into the same panel this way.
 */
export function CitationPanelProvider({ children }: { children: ReactNode }) {
  const [refs, setRefs] = useState<string[]>([]);

  const api: CitationPanelApi = {
    open: (ref) => setRefs((stack) => [...stack, ref]),
    close: () => setRefs([]),
  };

  return (
    <CitationPanelContext.Provider value={api}>
      {children}
      <CitationPanel
        refs={refs}
        onBack={() => setRefs((stack) => stack.slice(0, -1))}
        onClose={api.close}
      />
    </CitationPanelContext.Provider>
  );
}

interface CitationPanelProps {
  refs: string[];
  onBack: () => void;
  onClose: () => void;
}

/**
 * The slide-over source panel (§19.9) - the flagship interaction. Clicking
 * any citation opens this beside whatever page is already open; closing it
 * returns to the identical position, because nothing underneath ever
 * navigated. The full source viewer (`/sources/:id`) stays reachable from
 * inside it, via "Open full source".
 */
function CitationPanel({ refs, onBack, onClose }: CitationPanelProps) {
  const current = refs[refs.length - 1];
  const open = refs.length > 0;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    if (open) document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["read", current],
    queryFn: () => readRef(current as string),
    enabled: Boolean(current),
  });

  if (!open) return null;

  return (
    <div
      role="presentation"
      onClick={onClose}
      // The scrim starts past the sidebar (§19.9: "over a scrim that
      // starts at x=232, so the sidebar stays lit").
      style={{ left: 232 }}
      className="fixed inset-y-0 right-0 z-40 bg-ink/30"
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Citation"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-[440px] max-w-[90vw] flex-col border-l border-border bg-card shadow-lg"
      >
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            {refs.length > 1 && (
              <button
                type="button"
                onClick={onBack}
                aria-label="Back"
                className="shrink-0 rounded px-1 text-secondary hover:bg-hover hover:text-ink"
              >
                {"←"}
              </button>
            )}
            <span className="truncate font-mono text-xs text-ink">
              {data?.citation ?? current}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded px-1 text-secondary hover:bg-hover hover:text-ink"
          >
            {"×"}
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading && <p className="text-sm text-muted">Loading…</p>}
          {isError && <p className="text-sm text-muted">This reference could not be read.</p>}
          {data && <CitationBody data={data} onNavigateAway={onClose} />}
        </div>
      </aside>
    </div>
  );
}

function CitationBody({
  data,
  onNavigateAway,
}: {
  data: CitationOut;
  onNavigateAway: () => void;
}) {
  const { open } = useCitationPanel();
  const record = data.record;
  const paragraph = typeof data.paragraph === "number" ? data.paragraph : null;
  const isCitedParagraph = record !== null && paragraph !== null;

  return (
    <div>
      {record && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-ink">{record.id}</span>
          <Badge tone={record.contemporaneous ? "green" : "amber"}>
            {record.contemporaneous ? "Contemporaneous" : "Retrospective"}
          </Badge>
          <Badge tone="neutral">recorded {record.recorded_date || "—"}</Badge>
          <Badge tone="neutral">{record.source_type}</Badge>
        </div>
      )}

      <p
        className={
          isCitedParagraph
            ? "rounded border-l-[3px] border-amber bg-amber-tint-soft px-3 py-2 font-serif text-[15px] leading-relaxed text-ink"
            : "whitespace-pre-wrap font-serif text-[15px] leading-relaxed text-ink"
        }
      >
        {data.text}
      </p>

      {record && (
        <div className="mt-4 flex gap-2">
          <Link
            to={
              paragraph !== null && data.anchor
                ? `/sources/${record.id}#${data.anchor}`
                : `/sources/${record.id}`
            }
            onClick={onNavigateAway}
            className="flex-1 rounded border border-border-strong px-3 py-2 text-center text-sm text-ink hover:bg-hover"
          >
            Open full source
          </Link>
          <Link
            to={`/sources/${record.id}/raw`}
            target="_blank"
            rel="noreferrer"
            className="flex-1 rounded bg-ink px-3 py-2 text-center text-sm text-card hover:bg-body"
          >
            Open original ↗
          </Link>
        </div>
      )}

      {data.overlay && <Backlinks overlay={data.overlay} onOpen={open} />}
    </div>
  );
}

/**
 * The `CITED BY` rail (§19.4/§19.9): `overlay.entry_links`/`exclusions`, the
 * only backlinks #20's read decoration actually supplies - never stubbed
 * (#25's acceptance criteria). Shared between the panel and the full source
 * viewer's own right rail, so a backlink opens the same way from either.
 */
export function Backlinks({
  overlay,
  onOpen,
}: {
  overlay: NonNullable<CitationOut["overlay"]>;
  onOpen: (ref: string) => void;
}) {
  const nothingLinks = overlay.entry_links.length === 0 && overlay.exclusions.length === 0;

  return (
    <div className="mt-6">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-muted">
        Cited by
      </div>
      {nothingLinks ? (
        <p className="text-xs text-muted">Nothing links this paragraph yet.</p>
      ) : (
        <ul className="space-y-1">
          {overlay.entry_links.map((entryId) => (
            <li key={entryId}>
              <button
                type="button"
                onClick={() => onOpen(entryId)}
                className="font-mono text-xs text-subjects hover:underline"
              >
                {entryId.replace(/^SUB-/, "")}
              </button>
            </li>
          ))}
          {overlay.exclusions.map((entryId) => (
            <li key={entryId}>
              <button
                type="button"
                onClick={() => onOpen(entryId)}
                className="font-mono text-xs text-muted hover:underline"
              >
                {entryId.replace(/^SUB-/, "")} · excluded
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
