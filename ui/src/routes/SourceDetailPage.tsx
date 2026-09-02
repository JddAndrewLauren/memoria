import { useEffect, useRef } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  readSource,
  readRef,
  checkLocality,
  revealSource,
  ApiError,
  type EditorialRecordOut,
} from "../api/client";
import { Badge, type Tone } from "../components/Badge";
import { Backlinks } from "../components/CitationPanel";
import { useCitationPanel } from "../lib/citationPanel";

// Five values, all of which must render distinguishably
// (docs/normalized-record-schema.md's `date_confidence`) - not just as
// different text in an identical badge. `chapter-only` and `unresolved`
// are different claims about the world ("the chapter is all we have" vs.
// "we tried and failed") and so get different tones, not just different
// words in the same neutral badge.
const DATE_CONFIDENCE_TONE: Record<string, Tone> = {
  exact: "green",
  inferred: "amber",
  published: "blue",
  "chapter-only": "neutral",
  unresolved: "red",
};

/**
 * The source viewer (§19.4): a normalized source's text, temporal metadata,
 * editorial apparatus and backlinks, with an "Open original" action. Reached
 * plainly (browsing `SOURCES`) it shows the whole record undecorated; reached
 * via a citation - the URL fragment names the cited paragraph's stable
 * anchor - that paragraph is highlighted and scrolled to, and the right
 * rail's `CITED BY` list shows its backlinks (#20's read decoration).
 *
 * A secondary "Reveal in editor" action (#65) sits beside "Open original",
 * present only when `/api/locality` reports this browser and the server
 * share a machine - absent otherwise, never disabled or erroring.
 */
export default function SourceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const citedAnchor = location.hash ? location.hash.slice(1) : null;
  const { open: openCitation } = useCitationPanel();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["source", id],
    queryFn: () => readSource(id as string),
    enabled: Boolean(id),
  });

  // The cited paragraph's backlinks - the same generic read the slide-over
  // uses, keyed to this one anchor rather than every paragraph, so an
  // ordinary full-record read stays cheap.
  const { data: citation, isError: isCitationError } = useQuery({
    queryKey: ["read", citedAnchor],
    queryFn: () => readRef(citedAnchor as string),
    enabled: Boolean(citedAnchor),
  });

  // "Reveal in editor" (#65): a local convenience, absent - not disabled,
  // not erroring - unless the browser and the API server are on the same
  // machine. `is_local` defaults to falsy while this loads or fails, so
  // the button never flashes in before the check settles.
  const { data: locality } = useQuery({
    queryKey: ["locality"],
    queryFn: checkLocality,
  });
  const reveal = useMutation({ mutationFn: () => revealSource(id as string) });

  const citedRef = useRef<HTMLParagraphElement | null>(null);
  useEffect(() => {
    citedRef.current?.scrollIntoView?.({ block: "center" });
  }, [citedAnchor, data]);

  if (isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (isError) {
    const message = error instanceof ApiError ? error.message : "This source could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!data) return null;

  // "Some records have no date at all" - render the absence as a fact
  // rather than an invented date (docs/normalized-record-schema.md).
  const hasNoDate = !data.recorded_date && !data.event_date;
  const apparatusByAnchor = groupApparatusByAnchor(data.apparatus);

  return (
    <div className="flex">
      <article className="flex-1 p-8">
        <header className="mb-2 flex flex-wrap items-center gap-2">
          <h1 className="font-mono text-sm text-ink">{data.id}</h1>
          <Badge tone={data.contemporaneous ? "green" : "amber"}>
            {data.contemporaneous ? "Contemporaneous" : "Retrospective"}
          </Badge>
          <Badge tone="neutral">{data.source_type}</Badge>
          {hasNoDate ? (
            <Badge tone="neutral">no date resolved</Badge>
          ) : (
            <>
              <Badge tone="neutral">recorded {data.recorded_date || "—"}</Badge>
              <Badge tone={DATE_CONFIDENCE_TONE[data.date_confidence] ?? "neutral"}>
                event {data.event_date || "—"} · {data.date_confidence}
              </Badge>
            </>
          )}
        </header>
        <p className="mb-6 max-w-[640px] text-xs text-muted">{data.original_locator}</p>
        <div className={citedAnchor ? "prose has-cited" : "prose"}>
          {data.paragraphs.map((paragraph) => {
            const isCited = paragraph.anchor === citedAnchor;
            return (
              <div key={paragraph.anchor}>
                <p
                  ref={isCited ? citedRef : undefined}
                  id={paragraph.anchor}
                  className={isCited ? "cited" : undefined}
                >
                  <span className="anchor" aria-hidden="true">
                    {paragraph.anchor.split("-p").pop()}
                  </span>
                  {paragraph.text}
                </p>
                {/* Apparatus attaches beside the paragraph it annotates,
                    never inside its text (§6/#25). */}
                {(apparatusByAnchor.get(paragraph.anchor) ?? []).map((item, index) => (
                  <ApparatusNote key={index} item={item} />
                ))}
              </div>
            );
          })}
        </div>
      </article>
      <aside className="w-[230px] shrink-0 border-l border-border p-4">
        <Link
          to={`/sources/${data.id}/raw`}
          target="_blank"
          rel="noreferrer"
          className="mb-6 block rounded bg-ink px-3 py-2 text-center text-sm text-card hover:bg-body"
        >
          Open original ↗
        </Link>
        {locality?.is_local && (
          <button
            type="button"
            onClick={() => reveal.mutate()}
            className="mb-6 block w-full rounded border border-border px-3 py-2 text-center text-sm text-body hover:bg-panel"
          >
            Reveal in editor
          </button>
        )}
        {reveal.isError && (
          <p className="mb-6 text-xs text-muted">Could not reveal the original file.</p>
        )}
        {citedAnchor && isCitationError && (
          <p className="mt-6 text-xs text-muted">This reference could not be read.</p>
        )}
        {citedAnchor && citation?.overlay && (
          <Backlinks overlay={citation.overlay} onOpen={openCitation} />
        )}
      </aside>
    </div>
  );
}

function groupApparatusByAnchor(
  apparatus: EditorialRecordOut[],
): Map<string, EditorialRecordOut[]> {
  const byAnchor = new Map<string, EditorialRecordOut[]>();
  for (const item of apparatus) {
    const items = byAnchor.get(item.linked_anchor) ?? [];
    items.push(item);
    byAnchor.set(item.linked_anchor, items);
  }
  return byAnchor;
}

function ApparatusNote({ item }: { item: EditorialRecordOut }) {
  return (
    <aside className="mb-4 ml-[2.75em] max-w-[560px] rounded border-l-[3px] border-amber bg-amber-tint-soft px-3 py-2 text-sm text-secondary">
      <div className="mb-1 flex items-center gap-2">
        <Badge tone="amber">{item.editorial_type}</Badge>
        {item.retrospective && <Badge tone="neutral">retrospective</Badge>}
      </div>
      <p>{item.text}</p>
    </aside>
  );
}
