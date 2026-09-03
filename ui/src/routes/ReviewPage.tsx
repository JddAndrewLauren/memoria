import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  applyRewrite,
  readReview,
  settleFinding,
  type DisagreementMemberOut,
  type FindingOut,
  type ReviewOut,
  type SettlementOut,
} from "../api/client";
import { Badge, type Tone } from "../components/Badge";
import { useCitationPanel } from "../lib/citationPanel";
import { wordDiff } from "../lib/wordDiff";

// Part 10 §21's confidence tiers - the one ordering findings have, and the
// only label a finding card carries besides the subject that raised it.
// Not a verdict and not a severity: part 19 §19.3's CONTRADICTED / "4 high
// · factual conflicts" are example content, and nothing here is named after
// them.
const CONFIDENCE_TONE: Record<string, Tone> = {
  high: "red",
  moderate: "amber",
  low: "neutral",
};

/**
 * Review (part 19 §19.3, as amended by §19.11): **the results view of an
 * audit the author asked for, not an inbox.** This page reads what the audit
 * a session ran on this section recorded, once, when opened - there is no
 * refetch interval, no subscription, nothing that fills it while the author
 * is away. A section nobody has audited says so, distinct from an audit that
 * found nothing.
 *
 * A finding is a disagreement set plus prose (part 06 §8.10), and its card
 * offers exactly what the set admits: view evidence, preview diff, apply,
 * settle. Nothing on this surface edits a brief - the "passage + brief"
 * shape's resolution is a conversation about the brief, rendered as text.
 * Apply is the author's authorization (part 10 §19.3) and goes through the
 * write path with the draft's staleness token (ADR-0003). Settle is the
 * same kind of act (part 06 §8.7: click-authorized) and lands on the entry
 * the finding names, with the entry's own token; its provenance is the
 * session it happened in, chosen from the sessions that touched the section.
 */
export default function ReviewPage() {
  const { sectionId } = useParams<{ sectionId: string }>();
  // What this visit settled, kept here rather than on the finding's card:
  // a settlement silences its finding, so the card is gone on the next
  // read of the review, and the record of the act has to outlive it.
  const [settled, setSettled] = useState<SettlementOut[]>([]);

  const review = useQuery({
    queryKey: ["review", sectionId],
    queryFn: () => readReview(sectionId as string),
    enabled: Boolean(sectionId),
  });

  if (review.isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (review.isError) {
    const message =
      review.error instanceof ApiError ? review.error.message : "This review could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!review.data) return null;

  const data = review.data;
  const audited = data.verdicts_current > 0;

  return (
    <article className="max-w-[900px] p-8">
      <header className="mb-6">
        <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
          Review · Section {data.chapter_number}.{data.section_number}
        </p>
        <h1 className="mt-1 text-lg text-ink">
          Results of the audit you ran on{" "}
          <Link to={`/sections/${data.section_id}`} className="font-mono text-sm underline">
            {data.section_id}
          </Link>
        </h1>
        <p className="mt-1 text-xs text-muted">Nothing changes without your say-so.</p>
      </header>

      <SummaryBar data={data} audited={audited} />

      {settled.length > 0 && (
        <ul className="mt-3 space-y-1" aria-label="Settled this visit">
          {settled.map((item) => (
            <li key={item.claim_id} className="text-xs text-muted">
              Settled on {item.entry_id} as {item.claim_id}: {item.settled_line}
            </li>
          ))}
        </ul>
      )}

      {!audited ? (
        <p className="mt-6 max-w-[640px] rounded border border-dashed border-border px-3 py-2 text-xs text-muted">
          No audit has been run on this section. Run one from a session — the audit is asked for,
          never scheduled — and this view shows what it found.
        </p>
      ) : data.findings.length === 0 ? (
        <p className="mt-6 max-w-[640px] text-xs text-muted">
          The audit found nothing to disagree with in the paragraphs it judged.
        </p>
      ) : (
        <ul className="mt-6 space-y-4">
          {data.findings.map((finding, index) => (
            <FindingCard
              key={`${finding.paragraph_index}-${finding.entry_id}-${index}`}
              sectionId={data.section_id}
              finding={finding}
              token={data.token}
              sessions={data.sessions}
              onSettled={(item) => setSettled((items) => [...items, item])}
            />
          ))}
        </ul>
      )}
    </article>
  );
}

// Counts from the recorded findings themselves, by confidence - never a
// severity list and never a fixed set of labels.
function SummaryBar({ data, audited }: { data: ReviewOut; audited: boolean }) {
  const byConfidence = new Map<string, number>();
  for (const finding of data.findings) {
    byConfidence.set(finding.confidence, (byConfidence.get(finding.confidence) ?? 0) + 1);
  }
  return (
    <div className="flex flex-wrap items-center gap-3 rounded border border-border bg-panel px-3 py-2 text-xs text-body">
      <span className="font-medium">
        {data.findings.length} {data.findings.length === 1 ? "finding" : "findings"}
      </span>
      {[...byConfidence.entries()].map(([confidence, count]) => (
        <span key={confidence} className="flex items-center gap-1">
          <Badge tone={CONFIDENCE_TONE[confidence] ?? "neutral"}>{confidence}</Badge>
          <span className="font-mono text-[11px] text-muted">{count}</span>
        </span>
      ))}
      <span className="ml-auto font-mono text-[11px] text-muted">
        {audited
          ? `${data.verdicts_current} judgements current · ${data.verdicts_not_current} not current`
          : "no judgements current"}
      </span>
    </div>
  );
}

// The settlement form (part 06 §8.7): the side chosen, the proposition, the
// reason, and the session the act happened in. It posts the finding's own
// disagreement set back with the entry's token; a 409 is the entry moved
// underneath, told apart from a failure by that number (ADR-0003).
function SettleForm({
  sectionId,
  finding,
  sides,
  sessions,
  onSettled,
  onClose,
}: {
  sectionId: string;
  finding: FindingOut;
  sides: string[];
  sessions: string[];
  onSettled: (item: SettlementOut) => void;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [side, setSide] = useState(sides[0]);
  const [proposition, setProposition] = useState("");
  const [reason, setReason] = useState("");
  const [sessionId, setSessionId] = useState(sessions[0] ?? "");
  const [subjectId, entrySlug] = finding.entry_id.split("/");

  const settle = useMutation({
    mutationFn: () =>
      settleFinding(sectionId, {
        entry_id: finding.entry_id,
        disagreement_set: finding.disagreement_set,
        side,
        proposition,
        reason,
        session_id: sessionId,
        entry_token: finding.entry_token as string,
      }),
    onSuccess: (item) => {
      // The settlement moved the entry, so every judgement against it is
      // stale and the finding is silenced: the review and the section are
      // re-read, and the entry page shows the settled line. The page keeps
      // the record, since this card leaves with the re-read.
      onSettled(item);
      onClose();
      queryClient.invalidateQueries({ queryKey: ["review", sectionId] });
      queryClient.invalidateQueries({ queryKey: ["section", sectionId] });
      queryClient.invalidateQueries({ queryKey: ["entry", subjectId, entrySlug] });
    },
  });
  const isStale = settle.error instanceof ApiError && settle.error.status === 409;
  const ready = Boolean(side && proposition.trim() && reason.trim() && sessionId.trim());

  return (
    <form
      aria-label="Settle this finding"
      className="mt-3 max-w-[640px] space-y-2 rounded border border-border bg-panel p-3 text-xs text-body"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) settle.mutate();
      }}
    >
      <fieldset className="flex flex-wrap gap-3">
        <legend className="font-mono text-[11px] uppercase tracking-wide text-muted">
          Settle toward
        </legend>
        {sides.map((candidate) => (
          <label key={candidate} className="flex items-center gap-1">
            <input
              type="radio"
              name={`side-${finding.paragraph_index}-${finding.entry_id}`}
              value={candidate}
              checked={side === candidate}
              onChange={() => setSide(candidate)}
            />
            the {candidate}
          </label>
        ))}
      </fieldset>
      <label className="block">
        <span className="font-mono text-[11px] uppercase tracking-wide text-muted">Proposition</span>
        <input
          type="text"
          value={proposition}
          onChange={(event) => setProposition(event.target.value)}
          className="mt-1 w-full rounded border border-border bg-card px-2 py-1"
        />
      </label>
      <label className="block">
        <span className="font-mono text-[11px] uppercase tracking-wide text-muted">Reason</span>
        <input
          type="text"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="mt-1 w-full rounded border border-border bg-card px-2 py-1"
        />
      </label>
      <label className="block">
        <span className="font-mono text-[11px] uppercase tracking-wide text-muted">Session</span>
        {sessions.length > 0 ? (
          <select
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            className="mt-1 w-full rounded border border-border bg-card px-2 py-1 font-mono"
          >
            {sessions.map((candidate) => (
              <option key={candidate} value={candidate}>
                {candidate}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={sessionId}
            placeholder="SES-…: the session this settlement happens in"
            onChange={(event) => setSessionId(event.target.value)}
            className="mt-1 w-full rounded border border-border bg-card px-2 py-1 font-mono"
          />
        )}
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!ready || settle.isPending}
          className="rounded bg-ink px-3 py-1 text-xs text-card hover:bg-body disabled:opacity-50"
        >
          {settle.isPending ? "Settling…" : "Record settlement"}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-border px-3 py-1 text-xs text-body hover:bg-panel"
        >
          Cancel
        </button>
      </div>
      {isStale && (
        <p className="rounded border border-amber bg-amber-tint-soft px-3 py-2 text-xs text-secondary">
          The entry changed since this review was read — nothing was written.{" "}
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["review", sectionId] })}
            className="underline"
          >
            Reload the review
          </button>{" "}
          for a fresh token.
        </p>
      )}
      {settle.isError && !isStale && (
        <p className="text-xs text-muted">
          {settle.error instanceof ApiError ? settle.error.message : "The settlement was not recorded."}
        </p>
      )}
    </form>
  );
}

function memberLabel(member: DisagreementMemberOut): string {
  return member.kind === "passage" ? `¶${member.ref.split("#").pop()}` : member.ref;
}

// The sides a finding can be settled toward, read off the resolutions the
// set admits (part 06 §8.10's table) - never off the members directly, so
// a set whose resolutions are a rewrite or an exclusion offers no side.
const SETTLE_RESOLUTION = /^settle toward the (entry|source|passage)$/;

function settleSides(finding: FindingOut): string[] {
  return finding.resolutions
    .map((resolution) => SETTLE_RESOLUTION.exec(resolution)?.[1])
    .filter((side): side is string => Boolean(side));
}

function FindingCard({
  sectionId,
  finding,
  token,
  sessions,
  onSettled,
}: {
  sectionId: string;
  finding: FindingOut;
  token: string | null | undefined;
  sessions: string[];
  onSettled: (item: SettlementOut) => void;
}) {
  const { open: openCitation } = useCitationPanel();
  const queryClient = useQueryClient();
  const [showDiff, setShowDiff] = useState(false);
  const [settling, setSettling] = useState(false);
  const [draftToken, setDraftToken] = useState(token ?? "");
  useEffect(() => setDraftToken(token ?? ""), [token]);

  const sources = finding.disagreement_set.filter((member) => member.kind === "source");
  const canApply = Boolean(finding.patch) && Boolean(draftToken);

  const apply = useMutation({
    mutationFn: () =>
      applyRewrite(sectionId, finding.paragraph_index, draftToken, finding.patch as string),
    onSuccess: () => {
      // The write moved the draft, so every judgement on the rewritten
      // paragraph is now stale and the review is re-read - what the author
      // sees next is what the audit still stands behind, not this card.
      queryClient.invalidateQueries({ queryKey: ["review", sectionId] });
      queryClient.invalidateQueries({ queryKey: ["section", sectionId] });
    },
  });
  const isStale = apply.error instanceof ApiError && apply.error.status === 409;
  const sides = settleSides(finding);
  const canSettle = sides.length > 0 && Boolean(finding.entry_token);

  return (
    <li className="rounded-card border border-border border-l-4 border-l-manuscript bg-card p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-muted">¶{finding.paragraph_index}</span>
        <Badge tone={CONFIDENCE_TONE[finding.confidence] ?? "neutral"}>
          {finding.confidence} confidence
        </Badge>
        <span className="font-mono text-[11px] text-muted">raised by {finding.subject_id}</span>
      </div>

      <p className="mb-3 max-w-[640px] text-sm text-body">{finding.statement}</p>

      <div className="mb-3">
        <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
          Disagreement set
        </p>
        <ul className="mt-1 flex flex-wrap gap-2">
          {finding.disagreement_set.map((member) => (
            <li key={`${member.kind}:${member.ref}`}>
              <MemberChip member={member} />
            </li>
          ))}
        </ul>
      </div>

      <div className="mb-3">
        <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
          Admissible resolutions
        </p>
        <ul className="mt-1 list-disc pl-5 text-xs text-secondary">
          {finding.resolutions.map((resolution) => (
            <li key={resolution}>{resolution}</li>
          ))}
        </ul>
      </div>

      {showDiff && finding.patch && (
        <DiffPreview before={finding.paragraph_text} after={finding.patch} />
      )}

      <div className="flex flex-wrap items-center gap-2">
        {sources.length > 0 && (
          <button
            type="button"
            onClick={() => openCitation(sources[0].ref)}
            className="rounded border border-border px-3 py-1 text-xs text-body hover:bg-panel"
          >
            View evidence
          </button>
        )}
        <button
          type="button"
          onClick={() => setShowDiff((value) => !value)}
          disabled={!finding.patch}
          title={finding.patch ? undefined : "The audit proposed no rewrite for this finding."}
          className="rounded border border-border px-3 py-1 text-xs text-body hover:bg-panel disabled:opacity-50"
        >
          {showDiff ? "Hide diff" : "Preview diff"}
        </button>
        <button
          type="button"
          onClick={() => apply.mutate()}
          disabled={!canApply || apply.isPending}
          title={finding.patch ? undefined : "The audit proposed no rewrite for this finding."}
          className="rounded bg-ink px-3 py-1 text-xs text-card hover:bg-body disabled:opacity-50"
        >
          {apply.isPending ? "Applying…" : "Apply"}
        </button>
        <button
          type="button"
          onClick={() => setSettling((value) => !value)}
          disabled={!canSettle}
          title={
            canSettle
              ? undefined
              : "This set admits no settlement: its resolutions are a rewrite, an exclusion or a conversation."
          }
          className="rounded border border-border px-3 py-1 text-xs text-body hover:bg-panel disabled:opacity-50"
        >
          Settle
        </button>
      </div>

      {settling && (
        <SettleForm
          sectionId={sectionId}
          finding={finding}
          sides={sides}
          sessions={sessions}
          onSettled={onSettled}
          onClose={() => setSettling(false)}
        />
      )}

      {apply.isSuccess && <p className="mt-2 text-xs text-muted">Applied.</p>}
      {isStale && (
        <p className="mt-2 max-w-[640px] rounded border border-amber bg-amber-tint-soft px-3 py-2 text-xs text-secondary">
          The draft changed since this review was read — nothing was written.{" "}
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["review", sectionId] })}
            className="underline"
          >
            Reload the review
          </button>{" "}
          to see the current draft and its findings.
        </p>
      )}
      {apply.isError && !isStale && (
        <p className="mt-2 text-xs text-muted">
          {apply.error instanceof ApiError ? apply.error.message : "The rewrite could not be applied."}
        </p>
      )}
    </li>
  );
}

// A member is rendered by its own reference form (part 06 §8.10): a source
// anchor opens the slide-over on the evidence; an entry links to its view;
// a passage, a decision or a brief is named as text - a brief chip that
// opened an editor would be the one path this surface must not have.
function MemberChip({ member }: { member: DisagreementMemberOut }) {
  const { open: openCitation } = useCitationPanel();
  const base = "rounded-chip border px-2 py-0.5 font-mono text-[11px]";
  if (member.kind === "source") {
    return (
      <button
        type="button"
        onClick={() => openCitation(member.ref)}
        className={`${base} border-amber bg-amber-tint text-amber hover:bg-hover`}
      >
        source · {member.ref}
      </button>
    );
  }
  if (member.kind === "entry") {
    const [subjectId, slug] = member.ref.split("/");
    return (
      <Link
        to={`/subjects/${subjectId}/entries/${slug}`}
        className={`${base} border-border bg-panel text-subjects hover:bg-hover`}
      >
        entry · {member.ref}
      </Link>
    );
  }
  return (
    <span className={`${base} border-border bg-panel text-secondary`}>
      {member.kind} · {memberLabel(member)}
    </span>
  );
}

function DiffPreview({ before, after }: { before: string; after: string }) {
  return (
    <div className="mb-3 max-w-[640px] rounded border border-border bg-page p-3 font-serif text-sm leading-relaxed text-body">
      {wordDiff(before, after).map((op, index) =>
        op.kind === "same" ? (
          <span key={index}>{op.text}</span>
        ) : op.kind === "removed" ? (
          <del key={index} className="bg-amber-tint text-manuscript">
            {op.text}
          </del>
        ) : (
          <ins key={index} className="bg-sources-tint text-sources no-underline">
            {op.text}
          </ins>
        ),
      )}
    </div>
  );
}
