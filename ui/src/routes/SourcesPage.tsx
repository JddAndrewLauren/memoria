import { useState } from "react";
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
import { RawFileTree } from "../components/RawFileTree";
import { STATE_ORDER, drawState, extractedLabel } from "../lib/ingestion";
import { useOpenAddRawUnits } from "../lib/addRawUnitsContext";

/**
 * The Sources page, reached from the SOURCES header in the sidebar: the
 * archive and its ingestion status on one surface. Two views of the same
 * status - *Files*, every file under `raw/` in its folders whether or not
 * the ledger has numbered it (ADR-0013), and *Units*, every ledger row with
 * whether it was converted into a normalized record, whether the index
 * holds it, and how much of it the extraction has read - derived on the
 * server from the ledger, the records and the index, never recorded (part
 * 05 §5.4: "the record is the state"). This is the one place a raw unit
 * that *failed* to convert, has no converter, or is not yet numbered is
 * visible at all: none becomes a record, so the SOURCES tree cannot list it.
 *
 * Two actions, "Normalize" and "Rebuild index" (ADR-0011), present only when
 * `/api/locality` says this browser and the server share a machine - absent
 * otherwise, never disabled. Each is one synchronous pass; a 409 is the
 * other one still running. The extraction is not launchable here: it needs
 * a model, and nothing that needs a model runs unasked (ADR-0005).
 */
export default function SourcesPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ingestion"],
    queryFn: readIngestionStatus,
  });
  const openAddRawUnits = useOpenAddRawUnits();
  const [view, setView] = useState<"files" | "units">("files");

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
        <h1 className="font-serif text-xl text-ink">Sources</h1>
        <span className="font-mono text-[11px] text-muted">as of {data.generated_at}</span>
        {data.unnumbered && (
          <span className="font-mono text-[11px] text-muted">
            {fileCount(data)} {fileCount(data) === 1 ? "file" : "files"}
            {data.unnumbered.length > 0 && ` · ${data.unnumbered.length} not numbered yet`}
          </span>
        )}
        {/* ADR-0013: not locality-gated - the bytes travel - so it sits in
            the header rather than among the two local-only runs below. */}
        <button
          type="button"
          onClick={() => openAddRawUnits()}
          className="ml-auto rounded border border-border bg-panel px-3 py-1 text-xs font-medium text-ink hover:bg-hover"
        >
          Add sources…
        </button>
      </header>
      <Actions status={data} />
      {data.unnumbered && data.unnumbered.length > 0 && (
        // Files under raw/ the ledger has not seen: the one archive fact no
        // row above can show, and where "already in the archive" from the
        // Add dialog points.
        <p role="note" className="mt-4 max-w-[640px] rounded border border-amber/40 bg-panel px-3 py-2 text-xs text-body">
          {data.unnumbered.length} {data.unnumbered.length === 1 ? "file" : "files"} in{" "}
          <code className="font-mono">raw/</code> {data.unnumbered.length === 1 ? "is" : "are"} not
          numbered yet. Normalize — above, or <code className="font-mono">memoria normalize</code> —
          numbers and converts them.
        </p>
      )}
      {data.units === null ? (
        <p className="mt-6 max-w-[640px] text-xs text-muted">
          Not checked — no evidence corpus is configured. Set{" "}
          <code className="font-mono">MEMORIA_EVIDENCE_ROOT</code> to the archive and the ledger
          under it is what this page reads.
        </p>
      ) : (
        <>
          {data.units.length > 0 && <SummaryBar status={data} />}
          <div role="tablist" className="mt-4 flex gap-1 border-b border-border text-xs">
            <ViewTab current={view} value="files" onPick={setView}>
              Files
            </ViewTab>
            <ViewTab current={view} value="units" onPick={setView}>
              Units
            </ViewTab>
          </div>
          {view === "files" ? (
            <RawFileTree status={data} />
          ) : data.units.length === 0 ? (
            <p className="mt-6 max-w-[640px] text-xs text-muted">
              The ledger is empty. Run <code className="font-mono">memoria normalize</code> against
              the evidence root — or Normalize above — to number the raw units and convert them.
            </p>
          ) : (
            <UnitsTable status={data} units={data.units} />
          )}
        </>
      )}
    </article>
  );
}

// Files under raw/: the ledger's live paths (one file however many
// messages it holds) plus the ones it has not numbered.
function fileCount(status: IngestionStatusOut): number {
  const paths = new Set(status.units?.filter((u) => !u.deleted).map((u) => u.path));
  return paths.size + (status.unnumbered?.length ?? 0);
}

function ViewTab({
  current,
  value,
  onPick,
  children,
}: {
  current: "files" | "units";
  value: "files" | "units";
  onPick: (view: "files" | "units") => void;
  children: string;
}) {
  const selected = current === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={() => onPick(value)}
      className={`-mb-px border-b-2 px-3 py-1.5 ${
        selected ? "border-ink font-medium text-ink" : "border-transparent text-secondary hover:text-ink"
      }`}
    >
      {children}
    </button>
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

// The two passes (ADR-0011). Both buttons disable while either runs: they
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
