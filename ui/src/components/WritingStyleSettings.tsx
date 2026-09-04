import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  listAllSources,
  readStyle,
  resolveObservation,
  runStyleAnalysis,
  updateStyle,
  uploadStyleSample,
  type SourceSummary,
  type StyleObservationOut,
  type StyleOut,
} from "../api/client";
import { Region } from "./SettingsRegion";
import { RunButton, describeSpend, useModelReadiness } from "./DirectRun";

export const STYLE_KEY = ["style"] as const;

/**
 * The writing style (ADR-0009): the author's book-wide direction for how
 * their prose is written, the samples of their own writing an analysis
 * reads, and the observations that analysis proposed for them to confirm,
 * change or discard one at a time.
 *
 * Nothing here can run the analysis. It is a Claude Code session driven by
 * the `writing-style` skill (no adapter may call a model); this panel says
 * so and shows what that session proposed.
 */
export function WritingStyleSettings() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: STYLE_KEY,
    queryFn: readStyle,
  });

  if (isLoading) return <p className="text-xs text-muted">Loading the writing style…</p>;
  if (isError || !data) {
    return (
      <p className="text-xs text-muted">
        {error instanceof ApiError ? error.message : "The writing style could not be read."}
      </p>
    );
  }
  return <WritingStyleEditor style={data} />;
}

function WritingStyleEditor({ style }: { style: StyleOut }) {
  const queryClient = useQueryClient();
  const [direction, setDirection] = useState(style.direction);
  const [observations, setObservations] = useState<string[]>(style.observations);
  const [sampleSources, setSampleSources] = useState<string[]>(style.sample_sources);
  const [token, setToken] = useState(style.token);

  // A fresh read - after a save, a confirm, or a reload following a 409 -
  // replaces the buffer and, above all, the token.
  useEffect(() => {
    setDirection(style.direction);
    setObservations(style.observations);
    setSampleSources(style.sample_sources);
    setToken(style.token);
  }, [style]);

  const save = useMutation({
    mutationFn: () =>
      updateStyle({ token, direction, observations, sample_sources: sampleSources }),
    onSuccess: (result) => {
      queryClient.setQueryData<StyleOut>(STYLE_KEY, result);
    },
  });

  const isStale = save.error instanceof ApiError && save.error.status === 409;
  const dirty =
    direction !== style.direction ||
    observations.join("\n") !== style.observations.join("\n") ||
    sampleSources.join("\n") !== style.sample_sources.join("\n");

  return (
    <div className="space-y-6">
      <header>
        <h3 className="font-serif text-base text-ink">Writing style</h3>
        <p className="mt-1 max-w-[560px] text-xs text-muted">
          Direction every writing agent receives before it drafts or rewrites your prose. Kept
          in <span className="font-mono">style/writing-style.md</span>, yours to edit here or in
          Obsidian.
        </p>
      </header>

      <Region
        label="Direction"
        note="In your own words: how this book is written. Free prose, as much or as little as you like."
      >
        <textarea
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
          aria-label="Direction"
          rows={5}
          placeholder="Keep the reader inside what I knew at the time. Short sentences; no hindsight."
          className="w-full rounded border border-border bg-card px-2 py-1.5 font-serif text-sm text-body"
        />
      </Region>

      <Region
        label="Observations"
        note="What an analysis of your own writing found, and you confirmed. Each is a directive a writer follows."
      >
        {observations.length === 0 ? (
          <p className="text-xs text-muted">No confirmed observations yet.</p>
        ) : (
          <ul className="space-y-1">
            {observations.map((observation, index) => (
              <li
                key={`${observation}-${index}`}
                className="flex items-start gap-2 rounded border border-border bg-panel px-2 py-1 text-sm text-body"
              >
                <span className="flex-1">{observation}</span>
                <button
                  type="button"
                  onClick={() => setObservations(observations.filter((_, at) => at !== index))}
                  aria-label={`Remove observation: ${observation}`}
                  className="text-muted hover:text-ink"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </Region>

      <Samples
        chosen={sampleSources}
        onChange={setSampleSources}
        uploaded={style.samples}
      />

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending || !dirty}
          className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save writing style"}
        </button>
        {save.isSuccess && !save.isPending && !dirty && (
          <span className="text-xs text-muted">Saved.</span>
        )}
      </div>
      {isStale && (
        <p className="max-w-[640px] rounded border border-amber bg-amber-tint-soft px-3 py-2 text-xs text-secondary">
          The writing style changed on disk since it was opened — nothing was written. Your
          edits are still here.{" "}
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: STYLE_KEY })}
            className="underline"
          >
            Reload the writing style
          </button>{" "}
          to see the current version and try again.
        </p>
      )}
      {save.isError && !isStale && (
        <p className="text-xs text-muted">
          {save.error instanceof ApiError
            ? save.error.message
            : "The writing style could not be saved."}
        </p>
      )}

      <Analysis style={style} />
    </div>
  );
}

// --- samples ------------------------------------------------------------------

function Samples({
  chosen,
  onChange,
  uploaded,
}: {
  chosen: string[];
  onChange: (next: string[]) => void;
  uploaded: StyleOut["samples"];
}) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const { data: sourcesData } = useQuery({ queryKey: ["sources"], queryFn: listAllSources });
  const sources = sourcesData?.items ?? [];
  const candidates = useMemo(() => matchingSources(sources, filter, chosen), [sources, filter, chosen]);

  const upload = useMutation({
    mutationFn: (file: File) => encodeFile(file).then((content) => uploadStyleSample({ filename: file.name, content })),
    onSuccess: (result) => queryClient.setQueryData<StyleOut>(STYLE_KEY, result),
  });

  return (
    <Region
      label="Samples"
      note="Your own writing, for the analysis to read: sources already in the archive, or documents uploaded for their style alone - never treated as evidence."
    >
      <div className="mb-3">
        <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted">
          Chosen sources
        </div>
        <ul className="mb-2 flex flex-wrap gap-2">
          {chosen.length === 0 && <li className="text-xs text-muted">No sources chosen.</li>}
          {chosen.map((id) => (
            <li
              key={id}
              className="flex items-center gap-2 rounded-chip border border-border bg-panel px-2 py-0.5 font-mono text-[11px] text-body"
            >
              {id}
              <button
                type="button"
                onClick={() => onChange(chosen.filter((item) => item !== id))}
                aria-label={`Remove ${id}`}
                className="text-muted hover:text-ink"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
        <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          aria-label="Find a source to add"
          placeholder="Find a source by id, file or locator…"
          className="w-full rounded border border-border bg-card px-2 py-1 text-sm text-body"
        />
        {filter.trim() && (
          <ul className="mt-1 max-h-40 overflow-y-auto rounded border border-border bg-card">
            {candidates.length === 0 && (
              <li className="px-2 py-1 text-xs text-muted">No matching source.</li>
            )}
            {candidates.map((source) => (
              <li key={source.id}>
                <button
                  type="button"
                  onClick={() => {
                    onChange([...chosen, source.id]);
                    setFilter("");
                  }}
                  className="block w-full px-2 py-1 text-left text-sm hover:bg-hover"
                >
                  <span className="font-mono text-xs text-ink">{source.id}</span>
                  <span className="ml-2 text-xs text-secondary">
                    {source.original_locator || source.original_file}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted">
          Uploaded documents
        </div>
        <ul className="mb-2 space-y-1">
          {uploaded.length === 0 && <li className="text-xs text-muted">No documents uploaded.</li>}
          {uploaded.map((sample) => (
            <li key={sample.path} className="text-sm text-body">
              {sample.title}{" "}
              <span className="font-mono text-[11px] text-muted">{sample.path}</span>
            </li>
          ))}
        </ul>
        <label className="text-xs text-secondary">
          Upload a document (.txt, .md, .docx, .pdf){" "}
          <input
            type="file"
            accept=".txt,.md,.docx,.pdf"
            aria-label="Upload a document"
            disabled={upload.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) upload.mutate(file);
              event.target.value = "";
            }}
            className="ml-2 text-xs"
          />
        </label>
        {upload.isPending && <p className="mt-1 text-xs text-muted">Uploading…</p>}
        {upload.isError && (
          <p className="mt-1 text-xs text-muted">
            {upload.error instanceof ApiError ? upload.error.message : "The document could not be uploaded."}
          </p>
        )}
      </div>
    </Region>
  );
}

export function matchingSources(
  sources: SourceSummary[],
  filter: string,
  chosen: string[],
): SourceSummary[] {
  const needle = filter.trim().toLowerCase();
  if (!needle) return [];
  return sources
    .filter((source) => !chosen.includes(source.id))
    .filter((source) =>
      [source.id, source.original_file, source.original_locator, source.source_type]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    )
    .slice(0, 20);
}

function encodeFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      // A data URL: everything after the comma is the base64 body.
      const result = String(reader.result);
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

// --- the analysis and its proposals -----------------------------------------

function Analysis({ style }: { style: StyleOut }) {
  const queryClient = useQueryClient();
  const { ready: directRunReady } = useModelReadiness();
  const [confirmedThisVisit, setConfirmedThisVisit] = useState<string[]>([]);
  const [discardedThisVisit, setDiscardedThisVisit] = useState(0);
  const pending = style.pending;
  const current: StyleObservationOut | undefined = pending[0];
  const [changing, setChanging] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setChanging(false);
    setDraft(current?.observation ?? "");
  }, [current]);

  const resolve = useMutation({
    mutationFn: ({ id, action, text }: { id: number; action: "confirm" | "discard"; text?: string }) =>
      resolveObservation(id, { action, token: style.token, text: text ?? null }),
    onSuccess: (result, variables) => {
      if (variables.action === "confirm") {
        setConfirmedThisVisit((list) => [...list, variables.text ?? current?.observation ?? ""]);
      } else {
        setDiscardedThisVisit((count) => count + 1);
      }
      queryClient.setQueryData<StyleOut>(STYLE_KEY, result);
    },
  });
  const isStale = resolve.error instanceof ApiError && resolve.error.status === 409;
  const total = pending.length + confirmedThisVisit.length + discardedThisVisit;
  const position = confirmedThisVisit.length + discardedThisVisit + 1;

  return (
    <Region
      label="Analyse your writing"
      note="A model reads the samples above and proposes observations about how you write. Its observations appear here for you to confirm, change or discard."
    >
      {directRunReady ? (
        <div className="mb-3">
          <RunButton
            label="Analyse now"
            runningLabel="Analysing…"
            step={async () => {
              const result = await runStyleAnalysis();
              queryClient.setQueryData<StyleOut>(STYLE_KEY, result.style);
              const rejected =
                result.rejected.length > 0 ? ` · ${result.rejected.length} rejected` : "";
              return {
                done: true,
                canContinue: false,
                summary: `${result.accepted} proposed${rejected} · ${describeSpend(result.spend)}`,
              };
            }}
          />
        </div>
      ) : (
        <p className="mb-3 rounded border border-border bg-panel px-3 py-2 text-xs text-secondary">
          Run <span className="font-mono">/writing-style</span> in a Claude Code session with the
          Memoria server up. With direct runs on under Settings &gt; Model, a button appears here
          instead.
        </p>
      )}

      {current ? (
        <div
          role="group"
          aria-label="Proposed observation"
          className="rounded border-l-4 border-amber bg-amber-tint-soft px-3 py-2"
        >
          <div className="mb-1 flex items-center justify-between font-mono text-[10px] uppercase tracking-wide text-muted">
            <span>
              Proposed · {current.aspect}
            </span>
            <span>
              {position} of {total}
            </span>
          </div>
          {changing ? (
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              aria-label="Changed observation"
              rows={3}
              className="mb-2 w-full rounded border border-border bg-card px-2 py-1 text-sm text-body"
            />
          ) : (
            <p className="mb-2 text-sm text-body">{current.observation}</p>
          )}
          <blockquote className="mb-3 border-l-2 border-border pl-2 font-serif text-sm text-secondary">
            {current.example}
          </blockquote>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={resolve.isPending || (changing && !draft.trim())}
              onClick={() =>
                resolve.mutate({
                  id: current.id,
                  action: "confirm",
                  text: changing ? draft.trim() : undefined,
                })
              }
              className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              type="button"
              disabled={resolve.isPending}
              onClick={() => setChanging((value) => !value)}
              className="rounded border border-border px-3 py-1 text-sm text-body hover:bg-panel"
            >
              {changing ? "Keep as proposed" : "Change"}
            </button>
            <button
              type="button"
              disabled={resolve.isPending}
              onClick={() => resolve.mutate({ id: current.id, action: "discard" })}
              className="rounded border border-border px-3 py-1 text-sm text-body hover:bg-panel"
            >
              Discard
            </button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted">
          {total === 0
            ? "No proposed observations are waiting."
            : "Every proposed observation has been acted on."}
        </p>
      )}

      {isStale && (
        <p className="mt-2 max-w-[640px] rounded border border-amber bg-amber-tint-soft px-3 py-2 text-xs text-secondary">
          The writing style changed on disk since it was opened — nothing was written.{" "}
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: STYLE_KEY })}
            className="underline"
          >
            Reload the writing style
          </button>{" "}
          and confirm again.
        </p>
      )}
      {resolve.isError && !isStale && (
        <p className="mt-2 text-xs text-muted">
          {resolve.error instanceof ApiError ? resolve.error.message : "The observation could not be recorded."}
        </p>
      )}

      {confirmedThisVisit.length > 0 && (
        <ul aria-label="Confirmed this visit" className="mt-3 space-y-1">
          {confirmedThisVisit.map((text, index) => (
            <li key={`${text}-${index}`} className="text-xs text-secondary">
              ✓ {text}
            </li>
          ))}
        </ul>
      )}
    </Region>
  );
}
