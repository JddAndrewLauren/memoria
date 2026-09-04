import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  MODEL_KEY,
  readModelSettings,
  runAudit,
  type AuditRunOut,
  type ModelSettingsOut,
  type SpendOut,
} from "../api/client";

/**
 * Whether a direct run (ADR-0010) can happen: the author switched it on
 * under Settings > Model and a key and the SDK are there. Every surface
 * that offers a Run button asks this first, through one cached read, and
 * shows its existing "run one from a session" text otherwise. Nothing
 * here can reach a model - the button POSTs to the backend, which holds
 * the seam; the client holds no model dependency at all.
 */
export function useModelReadiness(): { ready: boolean; settings: ModelSettingsOut | undefined } {
  // Readiness changes only when the author edits Settings > Model, and
  // that panel writes the fresh answer into this same cache on save - so
  // one read serves every surface for a while rather than each mount
  // asking again.
  const query = useQuery({
    queryKey: MODEL_KEY,
    queryFn: readModelSettings,
    retry: false,
    staleTime: 60_000,
  });
  return { ready: Boolean(query.data?.ready), settings: query.data };
}

// Calls and the model only - never a token figure, which part 14 §40 keeps
// off every author-facing surface; the ledger holds those.
export function describeSpend(spend: SpendOut): string {
  if (spend.calls === 0) return "no metered calls";
  return `${spend.calls} metered ${spend.calls === 1 ? "call" : "calls"} on ${spend.model}`;
}

export interface Step {
  done: boolean;
  summary: string;
}

/**
 * A Run button that loops one bounded step until the run says it is done
 * or the author stops it - the same resumable shape the skills keep, so a
 * stop between steps loses nothing. Shows the latest step's summary
 * inline, and the failure when a step fails.
 */
export function RunButton({
  label,
  runningLabel,
  step,
  onFinished,
  disabled = false,
}: {
  label: string;
  runningLabel: string;
  step: () => Promise<Step>;
  onFinished?: () => void | Promise<unknown>;
  disabled?: boolean;
}) {
  const [running, setRunning] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stopRequested = useRef(false);

  async function start() {
    stopRequested.current = false;
    setRunning(true);
    setError(null);
    try {
      let result: Step;
      do {
        result = await step();
        setSummary(result.summary);
      } while (!result.done && !stopRequested.current);
      await onFinished?.();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "The run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={disabled || running}
        onClick={start}
        className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
      >
        {running ? runningLabel : label}
      </button>
      {running && (
        <button
          type="button"
          onClick={() => {
            stopRequested.current = true;
          }}
          className="rounded border border-border px-3 py-1 text-sm text-body hover:bg-panel"
        >
          Stop after this step
        </button>
      )}
      {summary && (
        <span role="status" className="text-xs text-secondary">
          {summary}
        </span>
      )}
      {error && <span className="text-xs text-muted">{error}</span>}
    </div>
  );
}

function describeAudit(result: AuditRunOut): string {
  const parts = [
    `${result.accepted} ${result.accepted === 1 ? "judgement" : "judgements"} recorded`,
    `${result.findings} ${result.findings === 1 ? "finding" : "findings"}`,
    result.remaining > 0 ? `${result.remaining} still awaiting audit` : "every judgement current",
  ];
  if (result.rejected.length > 0) parts.push(`${result.rejected.length} rejected`);
  parts.push(describeSpend(result.spend));
  return parts.join(" · ");
}

/**
 * The audit's button on a section (CONTEXT.md: "a button on a section or
 * a chapter, or on a highlighted passage"), rendered only when a direct
 * run is ready. Loops until the section has nothing not-current, then
 * refreshes the Section and Review reads.
 */
export function RunAuditButton({ sectionId }: { sectionId: string }) {
  const queryClient = useQueryClient();
  const { ready } = useModelReadiness();
  if (!ready) return null;
  return (
    <RunButton
      label="Run audit"
      runningLabel="Auditing…"
      step={async () => {
        const result = await runAudit(sectionId, { limit: 20 });
        return { done: result.remaining === 0, summary: describeAudit(result) };
      }}
      onFinished={() =>
        Promise.all([
          queryClient.invalidateQueries({ queryKey: ["review", sectionId] }),
          queryClient.invalidateQueries({ queryKey: ["section", sectionId] }),
        ])
      }
    />
  );
}
