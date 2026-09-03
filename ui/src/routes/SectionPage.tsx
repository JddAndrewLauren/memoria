import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ApiError,
  readSection,
  type DecisionOut,
  type NotCurrentOut,
  type QuestionOut,
  type ScopeEntryOut,
  type SectionParagraphOut,
} from "../api/client";
import { Badge } from "../components/Badge";

// The five staleness causes `memoria.audit.STALENESS_CAUSES` names (part 06
// §8.12), worded for the margin. Anything the server sends that is not one
// of these renders as sent - the list is the server's, not this file's.
const CAUSE_LABEL: Record<string, string> = {
  never_audited: "never audited",
  paragraph_edited: "edited since",
  entry_changed: "entry changed since",
  subject_changed: "subject changed since",
  gathered_set_changed: "gathered set changed since",
};

/**
 * The Section view (part 19 §19.5, as amended by §19.11): the draft with
 * its not-current tint, and a right rail of cards composed live. Of the six
 * cards the design drew, `PURPOSE` reads a file - the brief - and the other
 * five compose from the staleness map, the scope resolver and the session
 * records. `CHECKPOINT` and `Unresolved impacts` are superseded and have no
 * card: they were never stored state, and nothing here stands in for them.
 *
 * Reads plus explicit acts, no model driver. The two acts on this surface
 * are navigations: to Review, which shows the results of an audit the author
 * ran from a session, and to the supplied-context surface (#61), whose
 * opener carries no count by design - a count is a budget to optimise
 * against (ADR-0001, Invariant 1).
 */
export default function SectionPage() {
  const { sectionId } = useParams<{ sectionId: string }>();

  const section = useQuery({
    queryKey: ["section", sectionId],
    queryFn: () => readSection(sectionId as string),
    enabled: Boolean(sectionId),
  });

  if (section.isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (section.isError) {
    const message =
      section.error instanceof ApiError
        ? section.error.message
        : "This section could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!section.data) return null;

  const data = section.data;
  const notCurrentParagraphs = data.paragraphs.filter((p) => p.not_current.length > 0).length;

  return (
    <div className="flex">
      <article className="flex-1 p-8">
        <header className="mb-6">
          <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
            Section {data.chapter_number}.{data.section_number}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-sm text-ink">{data.id}</h1>
            {data.unconfirmed && <Badge tone="amber">unconfirmed brief</Badge>}
          </div>
          <nav className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <Link
              to={`/sections/${data.id}/review`}
              className="rounded bg-ink px-3 py-1.5 text-card hover:bg-body"
            >
              Review audit results
            </Link>
            {/* The opener onto the supplied-context surface (#61). No
                count and no badge, ever: "opened, not watched". */}
            <Link
              to={`/sections/${data.id}/supplied-context`}
              className="rounded border border-border px-3 py-1.5 text-body hover:bg-panel"
            >
              Supplied context
            </Link>
          </nav>
        </header>

        {/* The summary line part 06 §8.12 puts above the prose: the tint is
            identical on every not-current paragraph, and the distinction
            between causes is carried beside each one. */}
        {data.has_draft && data.paragraphs.length > 0 && (
          <p className="mb-4 max-w-[640px] font-mono text-[11px] text-muted">
            {notCurrentParagraphs === 0
              ? "Every paragraph is current."
              : `${notCurrentParagraphs} of ${data.paragraphs.length} paragraphs not current · audit this section from a session to bring them current`}
          </p>
        )}

        {!data.has_draft ? (
          <p className="max-w-[640px] rounded border border-dashed border-border px-3 py-2 text-xs text-muted">
            A planned section: the brief is written and there is no draft yet.
          </p>
        ) : data.paragraphs.length === 0 ? (
          <p className="max-w-[640px] text-xs text-muted">The draft is empty.</p>
        ) : (
          <div className="prose">
            {data.paragraphs.map((paragraph) => (
              <DraftParagraph key={paragraph.index} paragraph={paragraph} />
            ))}
          </div>
        )}
      </article>

      <aside className="w-[290px] shrink-0 border-l border-border p-4">
        <Card label="Purpose">
          {data.brief ? (
            <p className="whitespace-pre-wrap text-sm text-body">{data.brief}</p>
          ) : (
            <p className="text-xs text-muted">The brief is empty.</p>
          )}
        </Card>

        <Card label="Decisions">
          {data.decisions.length === 0 ? (
            <p className="text-xs text-muted">
              No decisions from the sessions that touched this section.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.decisions.map((decision) => (
                <DecisionRow key={decision.id} decision={decision} />
              ))}
            </ul>
          )}
        </Card>

        <Card label="Open questions">
          {data.questions.length === 0 ? (
            <p className="text-xs text-muted">
              No open questions from the sessions that touched this section.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.questions.map((question, index) => (
                <QuestionRow key={index} question={question} />
              ))}
            </ul>
          )}
        </Card>

        <Card label="In scope">
          {data.scope_empty ? (
            <p className="text-xs text-muted">
              The brief names no entry. Assembly and the audit have nothing to resolve here.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {data.scope.map((entry) => (
                <ScopeChip key={entry.entry_id} entry={entry} />
              ))}
            </ul>
          )}
        </Card>

        <Card label="Sessions">
          {data.sessions.length === 0 ? (
            <p className="text-xs text-muted">No session has touched this section.</p>
          ) : (
            <ul className="space-y-1">
              {data.sessions.map((session) => (
                <li key={session} className="font-mono text-[11px] text-secondary">
                  {session}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </aside>
    </div>
  );
}

function DraftParagraph({ paragraph }: { paragraph: SectionParagraphOut }) {
  const notCurrent = paragraph.not_current.length > 0;
  return (
    <div>
      <p className={notCurrent ? "not-current" : undefined}>
        <span className="anchor" aria-hidden="true">
          ¶{paragraph.index}
        </span>
        {paragraph.text}
      </p>
      {notCurrent && <NotCurrentRow items={paragraph.not_current} />}
    </div>
  );
}

// The cause beside the tint: one line per distinct (cause, entry), so an
// author reads "not current · edited since · SUB-people/bob" and not a
// bare colour.
function NotCurrentRow({ items }: { items: NotCurrentOut[] }) {
  const seen = new Map<string, NotCurrentOut>();
  for (const item of items) seen.set(`${item.cause}|${item.entry_id}`, item);
  return (
    <ul className="mb-4 ml-[2.75em] flex max-w-[560px] flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-amber">
      {[...seen.values()].map((item) => (
        <li key={`${item.cause}|${item.entry_id}`}>
          not current · {CAUSE_LABEL[item.cause] ?? item.cause} · {item.entry_id}
        </li>
      ))}
    </ul>
  );
}

function Card({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="font-mono text-[11px] uppercase tracking-wide text-muted">{label}</h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function DecisionRow({ decision }: { decision: DecisionOut }) {
  return (
    <li className="text-sm text-body">
      <p>{decision.text}</p>
      <p className="mt-1 font-mono text-[11px] text-muted">
        {decision.id} · {decision.citation}
      </p>
    </li>
  );
}

function QuestionRow({ question }: { question: QuestionOut }) {
  return (
    <li className="text-sm text-body">
      <p>{question.text}</p>
      <p className="mt-1 font-mono text-[11px] text-muted">{question.citation}</p>
    </li>
  );
}

function ScopeChip({ entry }: { entry: ScopeEntryOut }) {
  const [subjectId, slug] = entry.entry_id.split("/");
  return (
    <li>
      <Link
        to={`/subjects/${subjectId}/entries/${slug}`}
        title={`named by: ${entry.matched_by.join(", ")}`}
        className="rounded-chip border border-border bg-panel px-2 py-0.5 font-mono text-[11px] text-subjects hover:bg-hover"
      >
        {entry.entry_id}
      </Link>
    </li>
  );
}
