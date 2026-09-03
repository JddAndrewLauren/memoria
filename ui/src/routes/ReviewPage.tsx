import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  applyRewrite,
  readReview,
  type DisagreementMemberOut,
  type FindingOut,
  type ReviewOut,
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
 * write path with the draft's staleness token (ADR-0003).
 */
export default function ReviewPage() {
  const { sectionId } = useParams<{ sectionId: string }>();

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

function memberLabel(member: DisagreementMemberOut): string {
  return member.kind === "passage" ? `¶${member.ref.split("#").pop()}` : member.ref;
}

function FindingCard({
  sectionId,
  finding,
  token,
}: {
  sectionId: string;
  finding: FindingOut;
  token: string | null | undefined;
}) {
  const { open: openCitation } = useCitationPanel();
  const queryClient = useQueryClient();
  const [showDiff, setShowDiff] = useState(false);
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
        {/* Settle is offered and honest about its state: a settlement is
            recorded on the entry, inside the audit-visible body, and that
            write arrives with #33. Present rather than hidden, the way
            the entry view's settlements region is. */}
        <button
          type="button"
          disabled
          title="Not built yet. Settlements — recorded on the entry, inside the audit-visible body — arrive with #33."
          className="rounded border border-dashed border-border px-3 py-1 text-xs text-muted disabled:opacity-70"
        >
          Settle
        </button>
      </div>

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
