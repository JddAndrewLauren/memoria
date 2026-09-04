import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  EXTRACTION_KEY,
  MODEL_KEY,
  readExtractionStatus,
  readModelSettings,
  runExtraction,
  updateModelSettings,
  type ExtractionRunOut,
  type ModelSettingsOut,
} from "../api/client";
import { Region } from "./SettingsRegion";
import { RunButton, describeSpend } from "./DirectRun";

/**
 * Settings > Model (ADR-0010): the switch that lets Memoria call a model
 * directly, the model it calls, the key it calls with, and - once it is
 * ready - the extraction's Run button. Off by default. The key is written
 * to a machine-local file the server owns and never comes back to this
 * panel; the panel shows only that one is set and where it came from.
 */
export function ModelSettings() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: MODEL_KEY,
    queryFn: readModelSettings,
  });

  if (isLoading) return <p className="text-xs text-muted">Loading the model settings…</p>;
  if (isError || !data) {
    return (
      <p className="text-xs text-muted">
        {error instanceof ApiError ? error.message : "The model settings could not be read."}
      </p>
    );
  }
  return (
    <div className="space-y-6">
      <header>
        <h3 className="font-serif text-base text-ink">Model</h3>
        <p className="mt-1 max-w-[560px] text-xs text-muted">
          By default every pass that needs a model - the extraction, an audit, the writing-style
          analysis - runs in a Claude Code session. Switch direct runs on and Memoria calls the
          model itself, from this app or from a session, against your own metered API key.
        </p>
      </header>
      <ModelForm settings={data} />
      <ExtractionRegion ready={data.ready} />
    </div>
  );
}

function ModelForm({ settings }: { settings: ModelSettingsOut }) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(settings.enabled);
  const [model, setModel] = useState(settings.model);
  // Write-only: the field starts empty on every read and is sent only
  // when the author typed into it. Clearing is its own explicit act.
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);

  useEffect(() => {
    setEnabled(settings.enabled);
    setModel(settings.model);
    setApiKey("");
    setClearKey(false);
  }, [settings]);

  const save = useMutation({
    mutationFn: () =>
      updateModelSettings({
        enabled,
        model: model.trim(),
        api_key: clearKey ? "" : apiKey.trim() ? apiKey.trim() : null,
      }),
    onSuccess: (result) => {
      queryClient.setQueryData<ModelSettingsOut>(MODEL_KEY, result);
    },
  });

  const dirty =
    enabled !== settings.enabled ||
    model.trim() !== settings.model ||
    apiKey.trim() !== "" ||
    clearKey;

  return (
    <>
      <Region label="Direct runs">
        <label className="flex items-start gap-2 text-sm text-body">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            aria-label="Let Memoria call the model directly"
            className="mt-1"
          />
          <span>
            Let Memoria call the model directly
            <span className="block text-xs text-muted">
              Metered against your key, and the text of a pass - archive paragraphs, manuscript
              prose, your samples - leaves this machine for the provider. Every call is recorded in
              the session ledger. Nothing runs until you ask for it.
            </span>
          </span>
        </label>
      </Region>

      <Region label="Model" note="The model id a direct run asks the provider for.">
        <input
          type="text"
          value={model}
          onChange={(event) => setModel(event.target.value)}
          aria-label="Model"
          className="w-full max-w-[360px] rounded border border-border bg-card px-2 py-1 font-mono text-sm text-body"
        />
      </Region>

      <Region
        label="API key"
        note={
          settings.api_key_set
            ? settings.api_key_source === "environment"
              ? "Set, from ANTHROPIC_API_KEY in the server's environment - it overrides any stored key and is never written to disk."
              : "Set, stored on this machine beside the index and readable by you alone. It is never shown here again."
            : "Not set. Store one here, or export ANTHROPIC_API_KEY in the shell that starts the server."
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={apiKey}
            onChange={(event) => {
              setApiKey(event.target.value);
              setClearKey(false);
            }}
            aria-label="API key"
            placeholder={settings.api_key_set ? "set (hidden) - type to replace" : "sk-ant-…"}
            autoComplete="off"
            className="w-full max-w-[360px] rounded border border-border bg-card px-2 py-1 font-mono text-sm text-body"
          />
          {settings.api_key_set && settings.api_key_source === "settings" && (
            <button
              type="button"
              onClick={() => {
                setClearKey(true);
                setApiKey("");
              }}
              disabled={clearKey}
              className="rounded border border-border px-3 py-1 text-sm text-body hover:bg-panel disabled:opacity-50"
            >
              {clearKey ? "Will be cleared on save" : "Clear stored key"}
            </button>
          )}
        </div>
      </Region>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!dirty || save.isPending || !model.trim()}
          onClick={() => save.mutate()}
          className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
        >
          Save
        </button>
        <p role="status" className="text-xs text-secondary">
          {settings.ready
            ? `Ready: direct runs call ${settings.model}, key from the ${settings.api_key_source}.`
            : `Not ready: ${settings.reason}.`}
        </p>
        {save.isError && (
          <p className="text-xs text-muted">
            {save.error instanceof ApiError ? save.error.message : "The settings could not be saved."}
          </p>
        )}
      </div>
    </>
  );
}

function describeExtraction(result: ExtractionRunOut): string {
  const parts: string[] = [];
  if (result.phase === "paragraphs") {
    parts.push(
      `${result.paragraphs_read} paragraphs read, ${result.paragraphs_accepted} recorded, ${result.paragraphs_remaining} still awaiting extraction`,
    );
  } else if (result.phase === "summaries") {
    parts.push(
      `${result.summaries_written} summaries written, ${result.summaries_remaining} still pending`,
    );
  } else {
    parts.push("done - every paragraph read and every cluster summarised");
  }
  if (result.promotions.length > 0) parts.push(`auto-promoted ${result.promotions.join(", ")}`);
  if (result.rejected.length > 0) parts.push(`${result.rejected.length} rejected`);
  parts.push(describeSpend(result.spend));
  return parts.join(" · ");
}

function ExtractionRegion({ ready }: { ready: boolean }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: EXTRACTION_KEY, queryFn: readExtractionStatus });
  const counts = status.data;
  return (
    <Region
      label="Extraction"
      note="The author-launched pass that reads every paragraph of the archive for what it mentions. It asserts nothing; match terms decide."
    >
      {counts && (
        <p className="mb-2 font-mono text-[11px] text-muted">
          {counts.extracted} of {counts.paragraphs} paragraphs read · {counts.pending} awaiting
          extraction · {counts.summaries_pending} summaries pending
        </p>
      )}
      {ready ? (
        <RunButton
          label="Run extraction"
          runningLabel="Extracting…"
          step={async () => {
            const result = await runExtraction(20);
            return { done: result.phase === "done", summary: describeExtraction(result) };
          }}
          onFinished={() => queryClient.invalidateQueries({ queryKey: EXTRACTION_KEY })}
        />
      ) : (
        <p className="text-xs text-muted">
          Run <span className="font-mono">/extraction</span> in a Claude Code session with the
          Memoria server up; with direct runs on, a button appears here instead.
        </p>
      )}
    </Region>
  );
}
