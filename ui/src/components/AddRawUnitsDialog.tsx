import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  checkLocality,
  readIngestionStatus,
  runNormalize,
  uploadRawUnit,
  type IngestionRunOut,
} from "../api/client";
import {
  MAX_RAW_UNIT_BYTES,
  encodeFile,
  filesFromFileList,
  formatBytes,
  type PickedFile,
} from "../lib/rawUnits";
import { Dialog } from "./Dialog";

type RowState =
  | { kind: "queued" }
  | { kind: "too_large" }
  // Already under raw/ before this batch - numbered by the ledger, or
  // waiting for a normalize. Told up front, from the ingestion status,
  // rather than learnt one 409 at a time.
  | { kind: "present"; numbered: boolean }
  | { kind: "uploading" }
  | { kind: "added" }
  | { kind: "failed"; message: string };
type Phase = "picking" | "uploading" | "normalizing" | "done";

interface AddRawUnitsDialogProps {
  open: boolean;
  onClose: () => void;
  /** What the author has picked or dropped so far; App owns the list so a
   *  drop while the dialog is open lands in it too. */
  files: PickedFile[];
  onAddFiles: (files: PickedFile[]) => void;
}

/**
 * Adding raw units from the app (ADR-0013): pick files, pick a folder, or
 * drop either anywhere in the window; one request per file, sequential, so
 * every row reports for itself - a 409 is "already in the archive", and a
 * file over the server's cap is never sent. When the browser and the server
 * share a machine the normalize that numbers the units runs straight after
 * (ADR-0011); hosted, the author is told it is still needed.
 *
 * A file already under `raw/` is marked so before anything is sent, from
 * the ingestion status - and if the archive holds files no normalize has
 * numbered yet, the footer says how many and offers the normalize, since
 * "already in the archive" for a file no other surface shows is otherwise
 * a dead end.
 */
export function AddRawUnitsDialog({ open, onClose, files, onAddFiles }: AddRawUnitsDialogProps) {
  const queryClient = useQueryClient();
  const { data: locality } = useQuery({ queryKey: ["locality"], queryFn: checkLocality });
  const { data: ingestion } = useQuery({ queryKey: ["ingestion"], queryFn: readIngestionStatus });
  const numbered = new Set(ingestion?.units?.filter((u) => !u.deleted).map((u) => u.path) ?? []);
  const unnumbered = new Set(ingestion?.unnumbered ?? []);
  const [phase, setPhase] = useState<Phase>("picking");
  const [states, setStates] = useState<Record<string, RowState>>({});
  const [normalized, setNormalized] = useState<IngestionRunOut | null>(null);
  const [normalizeError, setNormalizeError] = useState<string | null>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement | null>(null);

  const stateOf = (row: PickedFile): RowState => {
    const known = states[row.path];
    if (known) return known;
    if (row.file.size > MAX_RAW_UNIT_BYTES) return { kind: "too_large" };
    const ledgerPath = `raw/${row.path}`;
    if (numbered.has(ledgerPath)) return { kind: "present", numbered: true };
    if (unnumbered.has(ledgerPath)) return { kind: "present", numbered: false };
    return { kind: "queued" };
  };
  const queued = files.filter((row) => stateOf(row).kind === "queued");
  const busy = phase === "uploading" || phase === "normalizing";

  const setRow = (path: string, state: RowState) =>
    setStates((current) => ({ ...current, [path]: state }));

  async function add() {
    setPhase("uploading");
    setNormalized(null);
    setNormalizeError(null);
    let added = 0;
    for (const row of queued) {
      setRow(row.path, { kind: "uploading" });
      try {
        await uploadRawUnit({ path: row.path, content: await encodeFile(row.file) });
        setRow(row.path, { kind: "added" });
        added += 1;
      } catch (error) {
        const message =
          error instanceof ApiError && error.status === 409
            ? "already in the archive"
            : error instanceof ApiError
              ? error.message
              : "could not be uploaded";
        setRow(row.path, { kind: "failed", message });
      }
    }
    // Asked here rather than read off a query that may not have answered
    // yet: a click that beats it must not skip the normalize.
    const local = await queryClient
      .fetchQuery({ queryKey: ["locality"], queryFn: checkLocality })
      .catch(() => null);
    if (added > 0 && local?.is_local) await normalizeNow();
    settle();
  }

  async function normalizeNow() {
    setPhase("normalizing");
    try {
      setNormalized(await runNormalize());
    } catch (error) {
      setNormalizeError(
        error instanceof ApiError && error.status === 409
          ? "A run is already in progress — Normalize from the Ingestion page when it finishes."
          : error instanceof ApiError
            ? error.message
            : "Normalize failed.",
      );
    }
  }

  function settle() {
    // A new unit changes what every source-reading surface shows.
    void queryClient.invalidateQueries({ queryKey: ["ingestion"] });
    void queryClient.invalidateQueries({ queryKey: ["sources"] });
    void queryClient.invalidateQueries({ queryKey: ["subjects"] });
    setPhase("done");
  }

  const addedCount = files.filter((row) => stateOf(row).kind === "added").length;
  const waiting = unnumbered.size;

  return (
    <Dialog open={open} onClose={onClose} label="Add sources">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <h2 className="font-serif text-lg text-ink">Add sources</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close add sources"
          className="rounded px-2 py-1 text-lg text-secondary hover:bg-hover hover:text-ink"
        >
          {"×"}
        </button>
      </div>
      {/* Header, scrolling list, fixed footer: the Add button stays in
          view however long the list is - a dropped folder can be thousands
          of rows. */}
      <div className="max-h-[60vh] overflow-y-auto p-5">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <button
            type="button"
            disabled={busy}
            onClick={() => filesInput.current?.click()}
            className="rounded border border-border bg-panel px-3 py-1 font-medium text-ink hover:bg-hover disabled:opacity-50"
          >
            Choose files
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => folderInput.current?.click()}
            className="rounded border border-border bg-panel px-3 py-1 font-medium text-ink hover:bg-hover disabled:opacity-50"
          >
            Choose a folder
          </button>
          <span className="text-muted">or drop files or folders anywhere in the window.</span>
          <input
            ref={filesInput}
            type="file"
            multiple
            hidden
            aria-label="Choose files"
            onChange={(event) => {
              if (event.target.files) onAddFiles(filesFromFileList(event.target.files));
              event.target.value = "";
            }}
          />
          <input
            ref={(node) => {
              folderInput.current = node;
              // Not in React's attribute typing; set on the node.
              if (node) {
                node.setAttribute("webkitdirectory", "");
                node.setAttribute("directory", "");
              }
            }}
            type="file"
            multiple
            hidden
            aria-label="Choose a folder"
            onChange={(event) => {
              if (event.target.files) onAddFiles(filesFromFileList(event.target.files));
              event.target.value = "";
            }}
          />
        </div>
        <p className="mt-3 text-xs text-muted">
          Each file lands under <code className="font-mono">raw/</code> at the path shown, keeping
          its folder; a file already there is left alone. The next normalize numbers them.
        </p>
        {files.length > 0 && (
          <ul className="mt-4 divide-y divide-border rounded border border-border text-xs">
            {files.map((row) => {
              const state = stateOf(row);
              return (
                <li key={row.path} className="flex items-center gap-3 px-3 py-1.5">
                  <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-body" title={row.path}>
                    {row.path}
                  </span>
                  <span className="shrink-0 text-muted">{formatBytes(row.file.size)}</span>
                  <span className="w-40 shrink-0 text-right text-muted">{describe(state)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="border-t border-border px-5 py-3">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <button
            type="button"
            onClick={() => void add()}
            disabled={busy || queued.length === 0}
            className="rounded bg-ink px-3 py-1.5 font-medium text-card hover:bg-body disabled:opacity-50"
          >
            {phase === "uploading"
              ? "Adding…"
              : phase === "normalizing"
                ? "Normalizing…"
                : `Add ${queued.length} ${queued.length === 1 ? "file" : "files"}`}
          </button>
          {waiting > 0 && !busy && (
            <span className="text-secondary">
              {waiting} {waiting === 1 ? "file" : "files"} in the archive {waiting === 1 ? "is" : "are"} not
              numbered yet.
              {locality?.is_local ? (
                <>
                  {" "}
                  <button
                    type="button"
                    onClick={() => {
                      setNormalized(null);
                      setNormalizeError(null);
                      void normalizeNow().then(settle);
                    }}
                    className="rounded border border-border bg-panel px-2 py-0.5 font-medium text-ink hover:bg-hover"
                  >
                    Normalize now
                  </button>
                </>
              ) : (
                <>
                  {" "}
                  Run <code className="font-mono">memoria normalize</code> on the machine that holds the
                  archive.
                </>
              )}
            </span>
          )}
          {phase === "done" && (
            <p role="status" className="basis-full text-secondary">
              {addedCount > 0 && `Added ${addedCount}. `}
              {normalized ? (
                <>
                  Normalize:{" "}
                  <span className="font-mono text-[11px] text-muted">{summarise(normalized)}</span>
                </>
              ) : normalizeError ? (
                normalizeError
              ) : addedCount > 0 ? (
                <>
                  Run <code className="font-mono">memoria normalize</code> on the machine that holds
                  the archive to number and convert them.
                </>
              ) : (
                "Nothing was added."
              )}
            </p>
          )}
        </div>
      </div>
    </Dialog>
  );
}

function describe(state: RowState): string {
  switch (state.kind) {
    case "queued":
      return "queued";
    case "too_large":
      return `too large (${formatBytes(MAX_RAW_UNIT_BYTES)} limit)`;
    case "present":
      return state.numbered ? "already in the archive" : "in the archive, not numbered yet";
    case "uploading":
      return "uploading…";
    case "added":
      return "added";
    case "failed":
      return state.message;
  }
}

function summarise(outcome: IngestionRunOut): string {
  return (
    Object.entries(outcome.summary)
      .map(([key, value]) => `${value} ${key.replace(/_/g, " ")}`)
      .join(" · ") + ` · ${outcome.elapsed_seconds.toFixed(1)}s`
  );
}
