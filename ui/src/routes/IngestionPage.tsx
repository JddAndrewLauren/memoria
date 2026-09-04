import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  checkLocality,
  readIngestionStatus,
  runNormalize,
  runRebuild,
  type IngestionRunOut,
  type IngestionStatusOut,
  type UnitStatusOut,
} from "../api/client";
import { Badge } from "../components/Badge";
import { STATE_ORDER, drawState, extractedLabel } from "../lib/ingestion";

/**
 * The ingestion status: every raw unit in the ledger, with whether it was
 * converted into a normalized record, whether the index holds it, and how
 * much of it the extraction has read - derived on the server from the
 * ledger, the records and the index, never recorded (part 05 §5.4: "the
 * record is the state"). This is the one place a raw unit that *failed* to
 * convert, or has no converter, is visible at all: it never becomes a
 * record, so the SOURCES tree cannot list it.
 *
 * Two actions, "Normalize" and "Rebuild index" (ADR-0009), present only when
 * `/api/locality` says this browser and the server share a machine - absent
 * otherwise, never disabled. Each is one synchronous pass; a 409 is the
 * other one still running. The extraction is not launchable here: it needs
 * a model, and nothing that needs a model runs unasked (ADR-0005).
 */
export default function IngestionPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ingestion"],
    queryFn: readIngestionStatus,
  });

  if (isLoading) return <p className="p-8 text-sm text-muted">Loading...</p>;
  if (isError) {
    const message =
      error instanceof ApiError ? error.message : "The ingestion status could not be read.";
    return <p className="p-8 text-sm text-muted">{message}</p>;
  }
  if (!data) return null;

  return (
    <article className="p-8">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="font-serif text-xl text-ink">Ingestion</h1>
        <span className="font-mono text-[11px] text-muted">as of {data.generated_at}</span>
      </header>
      <Actions status={data} />
      {data.units === null ? (
        <p className="mt-6 max-w-[640px] text-xs text-muted">
          Not checked — no evidence corpus is configured. Set{" "}
          <code className="font-mono">MEMORIA_EVIDENCE_ROOT</code> to the archive and the ledger
          under it is what this page reads.
        </p>
      ) : data.units.length === 0 ? (
        <p className="mt-6 max-w-[640px] text-xs text-muted">
          The ledger is empty. Run <code className="font-mono">memoria normalize</code> against
          the evidence root — or Normalize above — to number the raw units and convert them.
        </p>
      ) : (
        <>
          <SummaryBar status={data} />
          <UnitsTable status={data} units={data.units} />
        </>
      )}
    </article>
  );
}

function SummaryBar({ status }: { status: IngestionStatusOut }) {
  const total = status.units?.length ?? 0;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 rounded border border-border bg-panel px-3 py-2 text-xs text-body">
      <span className="font-medium">
        {total} raw {total === 1 ? "unit" : "units"}
      </span>
      {STATE_ORDER.filter((state) => (status.counts[state] ?? 0) > 0).map((state) => {
        const drawing = drawState(state);
        return (
          <span key={state} className="flex items-center gap-1">
            <Badge tone={drawing.tone}>{drawing.label}</Badge>
            <span className="font-mono text-[11px] text-muted">{status.counts[state]}</span>
          </span>
        );
      })}
      <span className="ml-auto font-mono text-[11px] text-muted">
        {status.is_indexed
          ? `${status.counts.indexed ?? 0} indexed · ${status.counts.extracted_complete ?? 0} fully read by the extraction`
          : "index not built · run memoria rebuild, or Rebuild index above"}
      </span>
    </div>
  );
}

function UnitsTable({ status, units }: { status: IngestionStatusOut; units: UnitStatusOut[] }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="font-mono text-[11px] uppercase tracking-wide text-secondary">
          <tr>
            <th className="px-2 py-1">Unit</th>
            <th className="px-2 py-1">Raw unit</th>
            <th className="px-2 py-1">Converted</th>
            <th className="px-2 py-1 text-right">Indexed</th>
            <th className="px-2 py-1 text-right">Extracted</th>
          </tr>
        </thead>
        <tbody>
          {units.map((unit) => (
            <UnitRow key={unit.id} unit={unit} indexBuilt={status.is_indexed} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UnitRow({ unit, indexBuilt }: { unit: UnitStatusOut; indexBuilt: boolean }) {
  const drawing = drawState(unit.converted);
  const hasRecord = unit.record_paragraphs !== null;
  const extracted = extractedLabel(unit);
  return (
    <tr className="border-t border-border align-top">
      <td className="px-2 py-1 font-mono">
        {hasRecord ? (
          <Link to={`/sources/${unit.id}`} className="text-ink hover:underline">
            {unit.id}
          </Link>
        ) : (
          <span className="text-secondary">{unit.id}</span>
        )}
      </td>
      <td className="px-2 py-1 text-body">
        <span className="break-all">{unit.path}</span>
        {unit.email_message_index !== null && (
          <span className="ml-1 font-mono text-[11px] text-muted">
            message {unit.email_message_index}
          </span>
        )}
      </td>
      <td className="px-2 py-1">
        <Badge tone={drawing.tone}>{drawing.label}</Badge>
        {unit.failure_reason && (
          <p className="mt-1 max-w-[420px] break-words font-mono text-[11px] text-muted">
            {unit.failure_reason}
          </p>
        )}
      </td>
      <td className="px-2 py-1 text-right font-mono text-[11px]">
        {!hasRecord ? "—" : !indexBuilt ? "not built" : (unit.indexed_paragraphs ?? "—")}
      </td>
      <td className="px-2 py-1 text-right font-mono text-[11px]">{extracted ?? "—"}</td>
    </tr>
  );
}

// The two passes (ADR-0009). Both buttons disable while either runs: they
// share one lock on the server, and a click that would only earn a 409 is
// not an act worth offering.
function Actions({ status }: { status: IngestionStatusOut }) {
  const queryClient = useQueryClient();
  const { data: locality } = useQuery({ queryKey: ["locality"], queryFn: checkLocality });
  const settle = () => {
    // A pass changes what every source-reading surface shows.
    void queryClient.invalidateQueries({ queryKey: ["ingestion"] });
    void queryClient.invalidateQueries({ queryKey: ["sources"] });
    void queryClient.invalidateQueries({ queryKey: ["subjects"] });
  };
  const normalize = useMutation({ mutationFn: runNormalize, onSettled: settle });
  const rebuild = useMutation({ mutationFn: runRebuild, onSettled: settle });

  if (!locality?.is_local) return null;

  const running = normalize.isPending || rebuild.isPending;
  const canNormalize = status.units !== null;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded border border-border px-3 py-2 text-xs">
      <button
        type="button"
        onClick={() => normalize.mutate()}
        disabled={running || !canNormalize}
        className="rounded border border-border bg-panel px-3 py-1 font-medium text-ink hover:bg-hover disabled:opacity-50"
      >
        {normalize.isPending ? "Normalizing…" : "Normalize"}
      </button>
      <button
        type="button"
        onClick={() => rebuild.mutate()}
        disabled={running}
        className="rounded border border-border bg-panel px-3 py-1 font-medium text-ink hover:bg-hover disabled:opacity-50"
      >
        {rebuild.isPending ? "Rebuilding…" : "Rebuild index"}
      </button>
      <span className="text-muted">
        Normalize converts what changed in the archive; Rebuild index regenerates the index from
        the records, without semantic-search vectors — run{" "}
        <code className="font-mono">memoria rebuild</code> for those.
      </span>
      <RunOutcome label="Normalize" mutation={normalize} />
      <RunOutcome label="Rebuild index" mutation={rebuild} />
    </div>
  );
}

function RunOutcome({
  label,
  mutation,
}: {
  label: string;
  mutation: { data?: IngestionRunOut; error: unknown; isError: boolean };
}) {
  if (mutation.isError) {
    const { error } = mutation;
    const message =
      error instanceof ApiError && error.status === 409
        ? "A run is already in progress — try again when it finishes."
        : error instanceof ApiError
          ? error.message
          : `${label} failed.`;
    return (
      <p role="alert" className="basis-full text-manuscript">
        {label}: {message}
      </p>
    );
  }
  if (!mutation.data) return null;
  const summary = Object.entries(mutation.data.summary)
    .map(([key, value]) => `${value} ${key.replace(/_/g, " ")}`)
    .join(" · ");
  return (
    <p role="status" className="basis-full font-mono text-[11px] text-muted">
      {label}: {summary} · {mutation.data.elapsed_seconds.toFixed(1)}s
    </p>
  );
}
