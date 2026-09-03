import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ApiError,
  readSuppliedContext,
  type AssembledEntryOut,
  type FallbackOut,
  type ServedSinceOut,
  type SessionSuppliedContextOut,
} from "../api/client";
import { Badge } from "../components/Badge";

// How often the surface asks again while it is open. Live while open,
// absent while closed (ADR-0001): the query is mounted only by this page,
// so nothing asks once the author has left it.
export const REFRESH_INTERVAL_MS = 5_000;

// The tool names `memoria.ledger` writes, worded for the surface. Anything
// the ledger names that is not listed renders as sent.
const TOOL_LABEL: Record<string, string> = {
  read: "read",
  search_text: "text search",
  search_semantic: "semantic search",
  search_global: "global search",
  extraction_brief: "extraction brief",
  extraction_next_paragraphs: "extraction batch",
  extraction_next_summary: "extraction summary task",
};

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/**
 * The supplied-context surface (#61, ADR-0001, part 11 §33.1): for each
 * session that assembled this section, the working context assembly
 * produced and, apart from it, every read Memoria served since.
 *
 * Three things are load-bearing here rather than cosmetic. It reports what
 * Memoria *supplied* - the ledger records what was served and cannot record
 * what the client compacted away, so nothing on this page speaks for the
 * model. It is opened, not watched: it re-reads while mounted and does
 * nothing once closed, and its opener on the Section view carries no count.
 * And it states countable domain units - briefs, entries, fallbacks,
 * sources served - never a token, byte, percentage or capacity figure; the
 * response has no such field to render, and a test holds the page to it.
 */
export default function SuppliedContextPage() {
  const { sectionId } = useParams<{ sectionId: string }>();

  const account = useQuery({
    queryKey: ["supplied-context", sectionId],
    queryFn: () => readSuppliedContext(sectionId as string),
    enabled: Boolean(sectionId),
    refetchInterval: REFRESH_INTERVAL_MS,
  });

  if (account.isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (account.isError) {
    const message =
      account.error instanceof ApiError
        ? account.error.message
        : "The supplied context could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!account.data) return null;

  const data = account.data;

  return (
    <article className="max-w-[900px] p-8">
      <header className="mb-6">
        <p className="font-mono text-[11px] uppercase tracking-wide text-muted">Supplied context</p>
        <h1 className="mt-1 text-lg text-ink">
          What Memoria supplied for{" "}
          <Link to={`/sections/${data.section_id}`} className="font-mono text-sm underline">
            {data.section_id}
          </Link>
        </h1>
        <p className="mt-1 max-w-[640px] text-xs text-muted">
          For each session that assembled this section: the working context assembly produced,
          and every read served since. An account of what Memoria served, never of what the
          client kept.
        </p>
      </header>

      {data.sessions.length === 0 ? (
        <p className="max-w-[640px] rounded border border-dashed border-border px-3 py-2 text-xs text-muted">
          No session has assembled this section. There is no supplied context to report.
        </p>
      ) : (
        <ul className="space-y-6">
          {data.sessions.map((session) => (
            <SessionAccount key={session.session_id} session={session} />
          ))}
        </ul>
      )}
    </article>
  );
}

function SessionAccount({ session }: { session: SessionSuppliedContextOut }) {
  const sourcesServed = session.served_since.reduce((total, item) => total + item.served.length, 0);
  return (
    <li className="rounded-card border border-border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-ink">{session.session_id}</span>
        {session.unconfirmed && <Badge tone="amber">unconfirmed brief</Badge>}
        <span className="ml-auto font-mono text-[11px] text-muted">
          assembled {session.assembled_at}
        </span>
      </div>

      <p className="mb-4 font-mono text-[11px] text-muted">
        {plural(session.briefs.length, "brief")} · {plural(session.entries.length, "entry", "entries")} ·{" "}
        {plural(session.fallbacks.length, "fallback")} · {plural(sourcesServed, "source")} served since
      </p>

      <section aria-label="Working context" className="mb-4">
        <Heading>Working context — what assembly produced</Heading>

        <Row label="Briefs loaded">
          <ul className="flex flex-wrap gap-2">
            {session.briefs.map((brief) => (
              <li key={brief} className="font-mono text-[11px] text-secondary">
                {brief}
              </li>
            ))}
          </ul>
        </Row>

        <Row label="Entries resolved from the declared scope">
          {session.empty ? (
            <p className="text-xs text-muted">The declared scope named no entry.</p>
          ) : session.entries.length === 0 ? (
            <p className="text-xs text-muted">Nothing the scope named resolved to an entry.</p>
          ) : (
            <ul className="space-y-1">
              {session.entries.map((entry) => (
                <EntryRow key={entry.entry_id} entry={entry} />
              ))}
            </ul>
          )}
        </Row>

        <Row label="Fallbacks">
          {session.fallbacks.length === 0 ? (
            <p className="text-xs text-muted">None: nothing the scope named was left without an entry.</p>
          ) : (
            <ul className="space-y-1">
              {session.fallbacks.map((fallback) => (
                <FallbackRow key={fallback.candidate_id} fallback={fallback} />
              ))}
            </ul>
          )}
        </Row>
      </section>

      <section aria-label="Served since assembly">
        <Heading>Served since — reads Memoria served after assembly, not part of the working context</Heading>
        {session.served_since.length === 0 ? (
          <p className="text-xs text-muted">Nothing has been served to this session since assembly.</p>
        ) : (
          <ul className="space-y-1">
            {session.served_since.map((item, index) => (
              <ServedRow key={index} item={item} />
            ))}
          </ul>
        )}
      </section>
    </li>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-2 font-mono text-[11px] uppercase tracking-wide text-muted">{children}</h2>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-3">
      <p className="text-xs text-secondary">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

// An entry is what assembly loaded; its gathered set is what assembly
// reported - identifiers, never the paragraphs they name (#38).
function EntryRow({ entry }: { entry: AssembledEntryOut }) {
  const [subjectId, slug] = entry.entry_id.split("/");
  return (
    <li className="text-sm text-body">
      <Link
        to={`/subjects/${subjectId}/entries/${slug}`}
        className="rounded-chip border border-border bg-panel px-2 py-0.5 font-mono text-[11px] text-subjects hover:bg-hover"
      >
        {entry.entry_id}
      </Link>
      <span className="ml-2 font-mono text-[11px] text-muted">
        named by {entry.matched_by.join(", ")} · gathered set of {plural(entry.sources.length, "source")},
        reported as identifiers, not loaded
      </span>
    </li>
  );
}

// Part 06 §8.4: assembly never dead-ends, and says so. The candidate is
// named by its identity only - nothing of it was loaded.
function FallbackRow({ fallback }: { fallback: FallbackOut }) {
  return (
    <li className="text-sm text-body">
      <span className="font-medium">“{fallback.label}”</span> named no entry. Assembly fell back to the
      unpromoted candidate{" "}
      <span className="font-mono text-[11px] text-secondary">{fallback.candidate_id}</span> under{" "}
      <span className="font-mono text-[11px] text-secondary">{fallback.subject_id}</span> — its identity
      only; nothing of it was loaded.
    </li>
  );
}

function ServedRow({ item }: { item: ServedSinceOut }) {
  return (
    <li className="text-xs text-body">
      <span className="font-mono text-[11px] text-secondary">{TOOL_LABEL[item.tool] ?? item.tool}</span>
      {item.ref && <span className="ml-2 font-mono text-[11px] text-muted">asked for {item.ref}</span>}
      <span className="ml-2">served</span>{" "}
      {item.served.length === 0 ? (
        <span className="text-muted">nothing</span>
      ) : (
        <span className="font-mono text-[11px] text-secondary">{item.served.join(", ")}</span>
      )}
    </li>
  );
}
