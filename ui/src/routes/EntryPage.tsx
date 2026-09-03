import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  readAppearances,
  readEntry,
  readGatheredSet,
  updateMatchTerms,
  type AppearanceOut,
  type EntryDetail,
  type GatheredSetResponse,
  type GatheredSourceOut,
  type OverlayActOut,
  type StatementOut,
} from "../api/client";
import { Badge, type Tone } from "../components/Badge";
import { useCitationPanel } from "../lib/citationPanel";

// Ownership is read off the badge, not off a region of the page (part 06
// §8.2, CONTEXT.md's "Entry"): testimony is unbadged, and the absence *is*
// the attribution (§9.5). The three layer colours are load-bearing
// information design (§19.10) - blue is the author's, so `[author]` takes
// it and testimony, being the author's own hand, is named rather than
// tinted.
const BADGE_TONE: Record<string, Tone> = {
  author: "blue",
  source: "green",
  inferred: "amber",
  open: "neutral",
  // A settlement (#33) is the author's own act, so it takes the author's colour.
  settled: "blue",
  // §19.6's amber card: the Curator's note on a statement it may not
  // rewrite (part 08 §14.2, #32), served under this pseudo-badge.
  "memoria-note": "amber",
};

// The audit-visible body is testimony and every badged statement except
// `[open]` and a Memoria note - `memoria.subjects.is_audit_visible` on the
// server side, and this is the same line drawn on the same field.
function isAuditVisible(statement: StatementOut): boolean {
  return statement.badge !== "open" && statement.badge !== "memoria-note";
}

/**
 * The entry view (§19.6's Theme screen, generalized to any subject) and the
 * surface M3's gate is walked on: a citation here opens the slide-over on
 * the exact evidence paragraph without costing the reader their place, and
 * the panel's "Open original" serves the raw, unnormalized source.
 *
 * Most of what §19.6 draws is M4 data. Every region is built and none is
 * hidden: a region with nothing in it yet says which milestone fills it,
 * the way `MANUSCRIPT` does in the shell (#24). Nothing here invents a
 * statement or a badge to fill a space - a reviewer walking the gate has to
 * be able to see what is not built yet, and tell it from what merely has no
 * data.
 *
 * Three reads, not one. The entry is a read of its *file*; the gathered set
 * and appearances are index reads with their own build signal, and part 06
 * §8.11 keeps those two apart because one is evidence to write *from* and
 * the other is prose already written.
 */
export default function EntryPage() {
  const { subjectId, entrySlug } = useParams<{ subjectId: string; entrySlug: string }>();
  const enabled = Boolean(subjectId && entrySlug);

  const entry = useQuery({
    queryKey: ["entry", subjectId, entrySlug],
    queryFn: () => readEntry(subjectId as string, entrySlug as string),
    enabled,
  });
  const gathered = useQuery({
    queryKey: ["gathered", subjectId, entrySlug],
    queryFn: () => readGatheredSet(subjectId as string, entrySlug as string),
    enabled,
  });
  const appearances = useQuery({
    queryKey: ["appearances", subjectId, entrySlug],
    queryFn: () => readAppearances(subjectId as string, entrySlug as string),
    enabled,
  });

  if (entry.isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (entry.isError) {
    const message =
      entry.error instanceof ApiError ? entry.error.message : "This entry could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!entry.data) return null;

  const data = entry.data;
  const auditVisible = data.statements.filter(isAuditVisible);
  const outsideBody = data.statements.filter((statement) => !isAuditVisible(statement));

  return (
    <article className="max-w-[900px] p-8">
      <header className="mb-8">
        <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
          {(subjectId ?? "").replace(/^SUB-/, "")}
        </p>
        <h1 className="mt-1 text-2xl capitalize text-ink">{entrySlug}</h1>
        <p className="mt-1 font-mono text-xs text-muted">{data.id}</p>
      </header>

      <Region
        label="Audit-visible body"
        note="Testimony, settlements and the [author] / [source] / [inferred] statements — what assembly loads and what the audit compares prose against."
      >
        {auditVisible.length === 0 ? (
          <NotYetBuilt>
            No statements yet. The record extractor writes <code>[author]</code>,{" "}
            <code>[source]</code> and <code>[inferred]</code> statements at M4 (#31), and
            author testimony has no write path until then either.
          </NotYetBuilt>
        ) : (
          <ul className="space-y-4">
            {auditVisible.map((statement, index) => (
              <StatementRow key={index} statement={statement} />
            ))}
          </ul>
        )}
        {/* Settlements are *part of* the audit-visible body (part 06 §8.2),
            so their not-yet-built region is nested here rather than made a
            sibling of it - a top-level "Settlements" beside the body would
            draw a line the domain does not have. */}
        <h3 className="mt-6 font-mono text-[11px] uppercase tracking-wide text-muted">
          Settlements
        </h3>
        <div className="mt-2">
          <NotYetBuilt>
            Not built yet. Settlements — recorded author resolutions of surfaced conflicts,
            and part of this body — arrive at M4 (#33).
          </NotYetBuilt>
        </div>
      </Region>

      <Region
        label="Outside the audit-visible body"
        note="Assembly never loads these and the audit never evaluates against them."
      >
        {outsideBody.length === 0 ? (
          <p className="text-xs text-muted">No [open] lines on this entry.</p>
        ) : (
          <ul className="space-y-4">
            {outsideBody.map((statement, index) => (
              <StatementRow key={index} statement={statement} />
            ))}
          </ul>
        )}
      </Region>

      <Region label="Memoria notes">
        <NotYetBuilt>
          Not built yet. Memoria notes — what the Curator appends when evidence conflicts with
          a statement it may not rewrite — arrive at M4 (#32).
        </NotYetBuilt>
      </Region>

      <MatchTerms
        subjectId={subjectId as string}
        entrySlug={entrySlug as string}
        entry={data}
      />

      <Region
        label="Gathered set"
        note="The sources this subject matched to this entry — evidence to write from. Derived and rebuildable; it asserts nothing on its own."
      >
        {gathered.isError && <p className="text-xs text-muted">The gathered set could not be read.</p>}
        {gathered.data && <GatheredSet data={gathered.data} />}
      </Region>

      <Region
        label="Appearances"
        note="Manuscript passages this entry turns out to touch — prose already written, never material to write from, and never merged into the gathered set."
      >
        {appearances.isError && <p className="text-xs text-muted">Appearances could not be read.</p>}
        {appearances.data &&
          (!appearances.data.engine_supported ? (
            // Not an empty list: for a Theme or an Arc nothing has looked
            // yet, which is a different fact from nothing being found
            // (part 06 §8.11).
            <NotYetBuilt>
              No appearances yet — the model engine arrives with the audit at M5. This
              subject's match terms name entries and relations, and manuscript prose is never
              extracted, so there is nothing for a lexical pass to match against.
            </NotYetBuilt>
          ) : appearances.data.items.length === 0 ? (
            <p className="text-xs text-muted">
              {appearances.data.is_built
                ? "No appearances. The lexical pass found no manuscript passage touching this entry."
                : "No index yet — run memoria rebuild."}
            </p>
          ) : (
            <ul className="space-y-1">
              {appearances.data.items.map((item) => (
                <AppearanceRow key={item.anchor} item={item} />
              ))}
            </ul>
          ))}
      </Region>
    </article>
  );
}

function Region({
  label,
  note,
  children,
}: {
  label: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section className="mb-10">
      <h2 className="font-mono text-[11px] uppercase tracking-wide text-muted">{label}</h2>
      {note && <p className="mt-1 max-w-[640px] text-xs text-muted">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

// A region that has nothing in it *because it is not built*, distinct from
// one that is built and empty. Both render; only this one names a
// milestone. `MANUSCRIPT` in the shell (#24) is the same posture.
function NotYetBuilt({ children }: { children: ReactNode }) {
  return (
    <p className="max-w-[640px] rounded border border-dashed border-border px-3 py-2 text-xs text-muted">
      {children}
    </p>
  );
}

function StatementRow({ statement }: { statement: StatementOut }) {
  return (
    <li className="max-w-[640px]">
      <div className="mb-1">
        {statement.badge ? (
          <Badge tone={BADGE_TONE[statement.badge] ?? "neutral"}>{statement.badge}</Badge>
        ) : (
          // The absence of a badge is the attribution (part 06 §9.5), so it
          // is said rather than left blank - an unlabelled paragraph beside
          // labelled ones reads as an oversight, not as testimony.
          <Badge tone="blue">testimony · author</Badge>
        )}
      </div>
      <p className="text-body">{statement.text}</p>
    </li>
  );
}

function GatheredSet({ data }: { data: GatheredSetResponse }) {
  const { open: openCitation } = useCitationPanel();

  if (data.items.length === 0 && data.excluded.length === 0) {
    return (
      <p className="text-xs text-muted">
        {data.is_built
          ? // An entry with an empty gathered set is a valid state, not an
            // error (part 06 §8.2) - it may exist entirely on testimony.
            "Nothing gathered. This is a valid state: an entry may exist entirely on author testimony."
          : "No index yet — run memoria rebuild."}
      </p>
    );
  }

  return (
    <>
      <ul className="space-y-1">
        {data.items.map((item) => (
          <GatheredRow key={item.anchor} item={item} onOpen={openCitation} />
        ))}
      </ul>
      {data.excluded.length > 0 && (
        <div className="mt-4">
          <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
            Excluded from this set
          </p>
          <ul className="mt-2 space-y-1">
            {data.excluded.map((act) => (
              <li key={act.anchor} className="flex flex-wrap items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => openCitation(act.anchor)}
                  className="rounded-chip border border-amber bg-amber-tint px-2 py-0.5 font-mono text-[11px] text-amber hover:bg-hover"
                >
                  {act.anchor}
                </button>
                <OverlayAttribution act={act} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function GatheredRow({
  item,
  onOpen,
}: {
  item: GatheredSourceOut;
  onOpen: (ref: string) => void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-2 text-xs">
      {/* The citation chip the gate is walked through: it opens the
          slide-over over this page rather than navigating, which is what
          keeps the reader's place (#25, §19.9). */}
      <button
        type="button"
        onClick={() => onOpen(item.anchor)}
        className="rounded-chip border border-amber bg-amber-tint px-2 py-0.5 font-mono text-[11px] text-amber hover:bg-hover"
      >
        {item.anchor}
      </button>
      <span className="font-mono text-[11px] text-muted">{item.src_id}</span>
      {item.pinned && <Badge tone="blue">pinned</Badge>}
      {item.overlay_action && <OverlayAttribution act={item} />}
    </li>
  );
}

// Pins and exclusions are attributable author acts (part 06 §8.3), and this
// surface renders them - it never authors them. Pinning and excluding are
// #18's, from the source side.
function OverlayAttribution({
  act,
}: {
  act: Pick<OverlayActOut, "actor_name" | "at"> | Pick<GatheredSourceOut, "actor_name" | "at">;
}) {
  if (!act.actor_name && !act.at) return null;
  return (
    <span className="text-[11px] text-muted">
      by {act.actor_name ?? "an unnamed actor"}
      {act.at ? `, ${act.at.slice(0, 10)}` : ""}
    </span>
  );
}

function AppearanceRow({ item }: { item: AppearanceOut }) {
  const { open: openCitation } = useCitationPanel();
  return (
    <li className="flex flex-wrap items-center gap-2 text-xs">
      <button
        type="button"
        onClick={() => openCitation(item.anchor)}
        className="rounded-chip border border-border px-2 py-0.5 font-mono text-[11px] text-secondary hover:bg-hover"
      >
        {item.anchor}
      </button>
      <span className="font-mono text-[11px] text-muted">{item.src_id}</span>
      <span className="text-[11px] text-muted">{item.note}</span>
    </li>
  );
}

/**
 * Match terms, and the only write this surface makes.
 *
 * They are author-owned (part 06 §8.2) and the system's only alias store,
 * and this is the first durable write in the system. It goes through the
 * single write path and its staleness check (ADR-0003): the token the entry
 * was served with is held here and presented back, and a file changed
 * underneath - in Obsidian, or in another tab - is rejected whole. Nothing
 * is merged and nothing is retried silently; the author's edits stay in the
 * editor and they are told to re-read.
 */
function MatchTerms({
  subjectId,
  entrySlug,
  entry,
}: {
  subjectId: string;
  entrySlug: string;
  entry: EntryDetail;
}) {
  const queryClient = useQueryClient();
  const [terms, setTerms] = useState<string[]>(entry.match_terms);
  const [draft, setDraft] = useState("");
  const [token, setToken] = useState(entry.token);

  // A fresh read - a different entry, or this one re-read after a rejection
  // - replaces both. Without this the editor would keep the previous
  // entry's terms and, worse, its token.
  useEffect(() => {
    setTerms(entry.match_terms);
    setToken(entry.token);
    setDraft("");
  }, [entry]);

  const save = useMutation({
    mutationFn: () => updateMatchTerms(subjectId, entrySlug, token, terms),
    onSuccess: (result) => {
      // The write invalidated the token this editor holds - by its own
      // write - so the server's fresh one replaces it and the editor stays
      // usable without a reload.
      setToken(result.token);
      setTerms(result.match_terms);
      // And the cached entry too, or navigating away and back would serve
      // the pre-write token from cache and the next save would be rejected
      // as stale against a file only this editor had changed.
      queryClient.setQueryData<EntryDetail>(["entry", subjectId, entrySlug], (cached) =>
        cached ? { ...cached, match_terms: result.match_terms, token: result.token } : cached,
      );
      // The gathered set is derived from these terms, so it is now stale.
      queryClient.invalidateQueries({ queryKey: ["gathered", subjectId, entrySlug] });
    },
  });

  const isStale = save.error instanceof ApiError && save.error.status === 409;

  return (
    <Region
      label="Match terms"
      note="How this entry is referenced, beyond the subject default. The author's, and the system's only alias store."
    >
      <ul className="mb-3 flex flex-wrap gap-2">
        {terms.length === 0 && <li className="text-xs text-muted">No match terms yet.</li>}
        {terms.map((term, index) => (
          <li
            key={`${term}-${index}`}
            className="flex items-center gap-2 rounded-chip border border-border bg-panel px-2 py-0.5 font-mono text-[11px] text-body"
          >
            {term}
            <button
              type="button"
              onClick={() => setTerms(terms.filter((_, at) => at !== index))}
              aria-label={`Remove ${term}`}
              className="text-muted hover:text-ink"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-label="New match term"
          placeholder="Bob, Robert, SUB-people/bob"
          className="rounded border border-border bg-card px-2 py-1 text-sm text-body"
        />
        <button
          type="button"
          onClick={() => {
            if (!draft.trim()) return;
            setTerms([...terms, draft.trim()]);
            setDraft("");
          }}
          className="rounded border border-border px-3 py-1 text-sm text-body hover:bg-panel"
        >
          Add
        </button>
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
      {save.isSuccess && !save.isPending && (
        <p className="mt-2 text-xs text-muted">Saved.</p>
      )}
      {isStale && (
        <p className="mt-2 max-w-[640px] rounded border border-amber bg-amber-tint-soft px-3 py-2 text-xs text-secondary">
          This entry changed on disk since it was opened — nothing was written. Your edits are
          still here.{" "}
          <button
            type="button"
            onClick={() =>
              queryClient.invalidateQueries({ queryKey: ["entry", subjectId, entrySlug] })
            }
            className="underline"
          >
            Reload the entry
          </button>{" "}
          to see the current version and try again.
        </p>
      )}
      {save.isError && !isStale && (
        <p className="mt-2 text-xs text-muted">
          {save.error instanceof ApiError ? save.error.message : "Match terms could not be saved."}
        </p>
      )}
    </Region>
  );
}
