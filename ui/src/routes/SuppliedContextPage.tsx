import { Link, useParams } from "react-router-dom";

/**
 * The supplied-context surface's home (#61, ADR-0001), reached from the
 * Section view's opener. The surface itself - what assembly resolved for a
 * session, and every read served since, in countable domain units - is
 * #61's to build behind this route; until it lands, this page says so
 * rather than standing in for it with anything that looks like a report.
 * Nothing here counts, measures or claims what a model holds.
 */
export default function SuppliedContextPage() {
  const { sectionId } = useParams<{ sectionId: string }>();
  return (
    <article className="max-w-[640px] p-8">
      <p className="font-mono text-[11px] uppercase tracking-wide text-muted">Supplied context</p>
      <h1 className="mt-1 text-lg text-ink">
        For{" "}
        <Link to={`/sections/${sectionId}`} className="font-mono text-sm underline">
          {sectionId}
        </Link>
      </h1>
      <p className="mt-4 rounded border border-dashed border-border px-3 py-2 text-xs text-muted">
        Not built yet. The supplied-context surface — what Memoria supplied to a session on this
        section, and what it has served since — arrives with #61. It is opened, not watched, and
        it will report briefs, entries, fallbacks and sources served, never a token figure.
      </p>
    </article>
  );
}
