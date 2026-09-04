import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ModelSettings } from "./ModelSettings";
import type { ExtractionRunOut, ModelSettingsOut } from "../api/client";

function settings(overrides: Partial<ModelSettingsOut> = {}): ModelSettingsOut {
  return {
    enabled: false,
    provider: "anthropic",
    model: "claude-opus-5",
    effort: null,
    api_key_set: false,
    api_key_source: null,
    ready: false,
    reason: "direct runs are off",
    ...overrides,
  };
}

const READY = settings({
  enabled: true,
  api_key_set: true,
  api_key_source: "settings",
  ready: true,
  reason: null,
});

const STATUS = {
  paragraphs: 12,
  extracted: 4,
  pending: 8,
  candidates_raw: 0,
  candidates_above_threshold: 0,
  unplaced_forms: 0,
  proposed_match_terms: 0,
  clusters: 0,
  summaries_done: 0,
  summaries_pending: 0,
  derived: false,
};

function step(overrides: Partial<ExtractionRunOut>): ExtractionRunOut {
  return {
    phase: "paragraphs",
    paragraphs_read: 20,
    paragraphs_accepted: 20,
    paragraphs_remaining: 0,
    summaries_written: 0,
    summaries_remaining: 0,
    finished: false,
    promotions: [],
    rejected: [],
    spend: { calls: 20, model: "claude-opus-5" },
    ...overrides,
  };
}

interface Stub {
  current: ModelSettingsOut;
  runs?: ExtractionRunOut[];
}

function stubFetch(stub: Stub) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, method, body });
      if (url.endsWith("/api/model") && method === "PUT") {
        const key =
          body.api_key === null
            ? stub.current.api_key_set
            : body.api_key === ""
              ? false
              : true;
        stub.current = {
          ...stub.current,
          enabled: body.enabled,
          model: body.model,
          effort: body.effort,
          api_key_set: key,
          api_key_source: key ? "settings" : null,
          ready: body.enabled && key,
          reason: !body.enabled ? "direct runs are off" : key ? null : "no API key is set",
        };
        return new Response(JSON.stringify(stub.current), { status: 200 });
      }
      if (url.endsWith("/api/model")) {
        return new Response(JSON.stringify(stub.current), { status: 200 });
      }
      if (url.endsWith("/api/extraction/run") && method === "POST") {
        const queued = stub.runs ?? [];
        const served = queued.length > 1 ? queued.shift() : queued[0];
        return new Response(JSON.stringify(served ?? step({ phase: "done" })), { status: 200 });
      }
      if (url.endsWith("/api/extraction")) {
        return new Response(JSON.stringify(STATUS), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: `unexpected ${url}` }), { status: 404 });
    }),
  );
  return calls;
}

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ModelSettings />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Settings > Model", () => {
  it("saves a chosen effort level and reports it as ready", async () => {
    const calls = stubFetch({ current: READY });
    renderPanel();
    await screen.findByLabelText("Effort");

    fireEvent.change(screen.getByLabelText("Effort"), { target: { value: "low" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(
        "Ready: direct runs call claude-opus-5 at low effort, key from the settings.",
      ),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      enabled: true,
      model: "claude-opus-5",
      effort: "low",
      api_key: null,
    });
  });

  it("is off by default and says why a run is not ready", async () => {
    stubFetch({ current: settings() });
    renderPanel();

    expect(await screen.findByLabelText("Let Memoria call the model directly")).not.toBeChecked();
    expect(screen.getByLabelText("Model")).toHaveValue("claude-opus-5");
    expect(screen.getByLabelText("Effort")).toHaveValue("");
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(screen.getByText(/^Not set\./)).toBeInTheDocument();
    expect(screen.getByText("Not ready: direct runs are off.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("saves the switch and a typed key, and never shows the key back", async () => {
    const calls = stubFetch({ current: settings() });
    renderPanel();
    await screen.findByLabelText("Model");

    fireEvent.click(screen.getByLabelText("Let Memoria call the model directly"));
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "sk-ant-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(
        "Ready: direct runs call claude-opus-5 at default effort, key from the settings.",
      ),
    ).toBeInTheDocument();
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toEqual({
      enabled: true,
      model: "claude-opus-5",
      effort: null,
      api_key: "sk-ant-secret",
    });
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(screen.getByText(/Set, stored on this machine/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("sk-ant-secret");
  });

  it("leaves a stored key alone when the field is untouched, and clears it on request", async () => {
    const calls = stubFetch({ current: READY });
    renderPanel();
    await screen.findByLabelText("Model");

    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "claude-sonnet-5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      enabled: true,
      model: "claude-sonnet-5",
      effort: null,
      api_key: null,
    });

    fireEvent.click(await screen.findByRole("button", { name: "Clear stored key" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT").length).toBe(2));
    expect((calls.filter((c) => c.method === "PUT")[1].body as { api_key: string }).api_key).toBe("");
    expect(await screen.findByText(/^Not set\./)).toBeInTheDocument();
  });

  it("tells the author where an environment key comes from and offers no clearing of it", async () => {
    stubFetch({ current: settings({ api_key_set: true, api_key_source: "environment" }) });
    renderPanel();
    expect(await screen.findByText(/from ANTHROPIC_API_KEY/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /clear stored key/i })).not.toBeInTheDocument();
  });

  it("shows the extraction's numbers and no button while not ready", async () => {
    stubFetch({ current: settings() });
    renderPanel();
    expect(await screen.findByText(/4 of 12 paragraphs read · 8 awaiting extraction/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run extraction/i })).not.toBeInTheDocument();
    expect(screen.getByText("/extraction")).toBeInTheDocument();
  });

  it("runs the extraction step by step until done, then re-reads the numbers", async () => {
    const calls = stubFetch({
      current: READY,
      runs: [
        step({ paragraphs_remaining: 3 }),
        step({ phase: "summaries", paragraphs_read: 0, summaries_written: 2, finished: true, promotions: ["SUB-people/bob"] }),
        step({ phase: "done", paragraphs_read: 0, spend: { calls: 0, model: "" } }),
      ],
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /run extraction/i }));

    expect(await screen.findByText(/done - every paragraph read/)).toBeInTheDocument();
    const runs = calls.filter((c) => c.url.endsWith("/api/extraction/run"));
    expect(runs.length).toBe(3);
    expect(runs[0].body).toEqual({ limit: 20 });
    expect(calls.filter((c) => c.url.endsWith("/api/extraction") && c.method === "GET").length).toBe(2);
    expect(screen.getByRole("button", { name: /run extraction/i })).toBeEnabled();
  });

  it("requires an explicit retry after an extraction item is rejected", async () => {
    const calls = stubFetch({
      current: READY,
      runs: [
        step({
          paragraphs_accepted: 0,
          paragraphs_remaining: 1,
          rejected: [{ anchor: "src-000001-p1", reason: "the model refused" }],
        }),
        step({ phase: "done", paragraphs_read: 0, spend: { calls: 0, model: "" } }),
      ],
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /run extraction/i }));

    expect(await screen.findByText(/1 rejected/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /run extraction/i })).toBeEnabled(),
    );
    expect(calls.filter((c) => c.url.endsWith("/api/extraction/run"))).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /run extraction/i }));
    await waitFor(() =>
      expect(calls.filter((c) => c.url.endsWith("/api/extraction/run"))).toHaveLength(2),
    );
  });

  it("reports a refused run rather than looping on it", async () => {
    stubFetch({ current: READY });
    vi.mocked(globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/extraction/run") && init?.method === "POST") {
        return new Response(JSON.stringify({ detail: "anthropic rate-limited the call - try again later" }), { status: 502 });
      }
      if (url.endsWith("/api/model")) return new Response(JSON.stringify(READY), { status: 200 });
      return new Response(JSON.stringify(STATUS), { status: 200 });
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /run extraction/i }));
    expect(await screen.findByText(/rate-limited/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run extraction/i })).toBeEnabled();
  });
});
