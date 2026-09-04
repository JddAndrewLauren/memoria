import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsDialog } from "./SettingsDialog";
import type { StyleOut } from "../api/client";
import { matchingSources } from "./WritingStyleSettings";

function style(overrides: Partial<StyleOut> = {}): StyleOut {
  return {
    exists: true,
    direction: "Stay in the moment.",
    observations: ["Keep sentences short."],
    sample_sources: ["SRC-000184"],
    samples: [{ path: "style/samples/letter.md", title: "letter", original_file: "letter.txt" }],
    token: "tok-1",
    pending: [
      { id: 7, aspect: "rhythm", observation: "End on the noun.", example: "Nobody dared touch it." },
      { id: 8, aspect: "register", observation: "Stay plain.", example: "The deck went up." },
    ],
    confirmed_count: 0,
    discarded_count: 0,
    ...overrides,
  };
}

interface Stub {
  current: StyleOut;
  onPut?: (body: unknown) => Response | undefined;
  onPost?: (url: string, body: unknown) => Response | undefined;
  // Settings > Model's answer (ADR-0010); off unless a test says so.
  model?: Record<string, unknown>;
}

const MODEL_OFF = {
  enabled: false,
  provider: "anthropic",
  model: "claude-opus-5",
  api_key_set: false,
  api_key_source: null,
  ready: false,
  reason: "direct runs are off",
};
const MODEL_READY = { ...MODEL_OFF, enabled: true, api_key_set: true, api_key_source: "settings", ready: true, reason: null };

function stubFetch(stub: Stub) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, method, body });
      if (url.includes("/api/style/observations/") && method === "POST") {
        const custom = stub.onPost?.(url, body);
        if (custom) return custom;
        const id = Number(url.split("/").pop());
        stub.current = {
          ...stub.current,
          pending: stub.current.pending.filter((o) => o.id !== id),
          observations:
            body.action === "confirm"
              ? [
                  ...stub.current.observations,
                  body.text ?? stub.current.pending.find((o) => o.id === id)!.observation,
                ]
              : stub.current.observations,
          token: body.action === "confirm" ? "tok-2" : stub.current.token,
        };
        return new Response(JSON.stringify(stub.current), { status: 200 });
      }
      if (url.includes("/api/style/samples") && method === "POST") {
        const custom = stub.onPost?.(url, body);
        if (custom) return custom;
        stub.current = {
          ...stub.current,
          samples: [
            ...stub.current.samples,
            { path: "style/samples/new.md", title: "new", original_file: body.filename },
          ],
        };
        return new Response(JSON.stringify(stub.current), { status: 200 });
      }
      if (url.endsWith("/api/style/analyse") && method === "POST") {
        const custom = stub.onPost?.(url, body);
        if (custom) return custom;
        stub.current = {
          ...stub.current,
          pending: [
            ...stub.current.pending,
            { id: 9, aspect: "diction", observation: "Reach for the plain word.", example: "The deck went up." },
          ],
        };
        return new Response(
          JSON.stringify({
            accepted: 1,
            rejected: [],
            spend: { calls: 1, model: "claude-opus-5" },
            style: stub.current,
          }),
          { status: 200 },
        );
      }
      if (url.endsWith("/api/model")) {
        return new Response(JSON.stringify(stub.model ?? MODEL_OFF), { status: 200 });
      }
      if (url.endsWith("/api/extraction")) {
        return new Response(
          JSON.stringify({
            paragraphs: 12, extracted: 4, pending: 8, candidates_raw: 0, candidates_above_threshold: 0,
            unplaced_forms: 0, proposed_match_terms: 0, clusters: 0, summaries_done: 0, summaries_pending: 0,
            derived: false,
          }),
          { status: 200 },
        );
      }
      if (url.includes("/api/style") && method === "PUT") {
        const custom = stub.onPut?.(body);
        if (custom) return custom;
        stub.current = { ...stub.current, ...body, token: "tok-2", exists: true };
        return new Response(JSON.stringify(stub.current), { status: 200 });
      }
      if (url.includes("/api/style")) {
        return new Response(JSON.stringify(stub.current), { status: 200 });
      }
      if (url.includes("/api/sources")) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "SRC-000184",
                source_type: "journal",
                recorded_date: "",
                event_date: "",
                date_confidence: "exact",
                contemporaneous: true,
                original_file: "raw/vol-01/text.txt",
                original_locator: "Journal I",
              },
              {
                id: "SRC-000185",
                source_type: "letter",
                recorded_date: "",
                event_date: "",
                date_confidence: "exact",
                contemporaneous: true,
                original_file: "raw/letters/bob.txt",
                original_locator: "To Bob",
              },
            ],
            total: 2,
            limit: 10000,
            offset: 0,
            is_built: true,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
  return calls;
}

function renderDialog(open = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SettingsDialog open={open} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { ...view, onClose };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the settings dialog", () => {
  it("renders nothing and fetches nothing while closed", () => {
    const calls = stubFetch({ current: style() });
    renderDialog(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it("shows the writing style - direction, observations, samples, and the first proposal", async () => {
    stubFetch({ current: style() });
    renderDialog();

    expect(await screen.findByLabelText("Direction")).toHaveValue("Stay in the moment.");
    expect(screen.getByText("Keep sentences short.")).toBeInTheDocument();
    expect(screen.getByText("SRC-000184")).toBeInTheDocument();
    expect(screen.getByText("letter")).toBeInTheDocument();
    const card = screen.getByRole("group", { name: "Proposed observation" });
    expect(within(card).getByText("End on the noun.")).toBeInTheDocument();
    expect(within(card).getByText("Nobody dared touch it.")).toBeInTheDocument();
    expect(within(card).getByText("1 of 2")).toBeInTheDocument();
    // The honest instruction: nothing here runs a model.
    expect(screen.getByText("/writing-style")).toBeInTheDocument();
  });

  it("saves the edited direction with the token it was served", async () => {
    const calls = stubFetch({ current: style() });
    renderDialog();
    const direction = await screen.findByLabelText("Direction");

    fireEvent.change(direction, { target: { value: "No hindsight." } });
    fireEvent.click(screen.getByRole("button", { name: "Save writing style" }));

    await screen.findByText("Saved.");
    const put = calls.find((call) => call.method === "PUT");
    expect(put?.body).toEqual({
      token: "tok-1",
      direction: "No hindsight.",
      observations: ["Keep sentences short."],
      sample_sources: ["SRC-000184"],
    });
  });

  it("keeps the author's text on a 409 and offers a reload", async () => {
    stubFetch({
      current: style(),
      onPut: () =>
        new Response(JSON.stringify({ detail: "style/writing-style.md changed" }), { status: 409 }),
    });
    renderDialog();
    const direction = await screen.findByLabelText("Direction");

    fireEvent.change(direction, { target: { value: "Kept on screen." } });
    fireEvent.click(screen.getByRole("button", { name: "Save writing style" }));

    expect(await screen.findByText(/changed on disk since it was opened/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload the writing style" })).toBeInTheDocument();
    expect(screen.getByLabelText("Direction")).toHaveValue("Kept on screen.");
  });

  it("confirms, changes and discards proposals one at a time", async () => {
    const calls = stubFetch({ current: style() });
    renderDialog();
    let card = await screen.findByRole("group", { name: "Proposed observation" });

    // Confirm as proposed.
    fireEvent.click(within(card).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(screen.getByText("2 of 2")).toBeInTheDocument());
    expect(calls.find((c) => c.url.endsWith("/observations/7"))?.body).toEqual({
      action: "confirm",
      token: "tok-1",
      text: null,
    });
    expect(within(screen.getByRole("list", { name: "Confirmed this visit" })).getByText(/End on the noun\./)).toBeInTheDocument();

    // Change, then confirm the changed text - with the fresh token.
    card = screen.getByRole("group", { name: "Proposed observation" });
    fireEvent.click(within(card).getByRole("button", { name: "Change" }));
    const draft = within(card).getByLabelText("Changed observation");
    expect(draft).toHaveValue("Stay plain.");
    fireEvent.change(draft, { target: { value: "Stay plain, and short." } });
    fireEvent.click(within(card).getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(screen.getByText("Every proposed observation has been acted on.")).toBeInTheDocument(),
    );
    expect(calls.find((c) => c.url.endsWith("/observations/8"))?.body).toEqual({
      action: "confirm",
      token: "tok-2",
      text: "Stay plain, and short.",
    });
    // The confirmed observation now sits in the style's own list.
    expect(screen.getAllByText("Stay plain, and short.").length).toBeGreaterThan(0);
  });

  it("discards without touching the style", async () => {
    const calls = stubFetch({ current: style({ pending: [style().pending[0]] }) });
    renderDialog();
    const card = await screen.findByRole("group", { name: "Proposed observation" });

    fireEvent.click(within(card).getByRole("button", { name: "Discard" }));

    await screen.findByText("Every proposed observation has been acted on.");
    expect(calls.find((c) => c.url.endsWith("/observations/7"))?.body).toEqual({
      action: "discard",
      token: "tok-1",
      text: null,
    });
    expect(screen.queryByRole("list", { name: "Confirmed this visit" })).not.toBeInTheDocument();
  });

  it("uploads a document as base64", async () => {
    const calls = stubFetch({ current: style() });
    renderDialog();
    const input = (await screen.findByLabelText("Upload a document")) as HTMLInputElement;

    const file = new File(["Dear Bob,\n\nNo."], "Letter to Bob.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    await screen.findByText("new");
    const post = calls.find((c) => c.url.endsWith("/api/style/samples"));
    expect(post?.body).toEqual({
      filename: "Letter to Bob.txt",
      content: btoa("Dear Bob,\n\nNo."),
    });
  });

  it("has a Model row that opens the direct-run settings", async () => {
    stubFetch({ current: style() });
    renderDialog();
    await screen.findByLabelText("Direction");

    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    expect(within(nav).getAllByRole("button").map((b) => b.textContent)).toEqual(["Writing style", "Model"]);
    fireEvent.click(within(nav).getByRole("button", { name: "Model" }));

    expect(await screen.findByLabelText("Let Memoria call the model directly")).not.toBeChecked();
    expect(screen.getByText("Not ready: direct runs are off.")).toBeInTheDocument();
    expect(await screen.findByText(/8 awaiting/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run extraction/i })).not.toBeInTheDocument();
  });

  it("offers Analyse now only when a direct run is ready, and shows what it proposed", async () => {
    stubFetch({ current: style() });
    renderDialog();
    await screen.findByLabelText("Direction");
    expect(screen.getByText("/writing-style")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /analyse now/i })).not.toBeInTheDocument();
    vi.unstubAllGlobals();

    const calls = stubFetch({ current: style({ pending: [] }), model: MODEL_READY });
    renderDialog();
    const button = await screen.findByRole("button", { name: /analyse now/i });
    fireEvent.click(button);

    await screen.findByText("Reach for the plain word.");
    expect(calls.some((c) => c.url.endsWith("/api/style/analyse") && c.method === "POST")).toBe(true);
    expect(screen.getByText(/1 proposed · 1 metered call/)).toBeInTheDocument();
  });

  it("adds a chosen source from the archive and removes one", async () => {
    stubFetch({ current: style() });
    renderDialog();
    await screen.findByText("SRC-000184");

    fireEvent.click(screen.getByRole("button", { name: "Remove SRC-000184" }));
    expect(screen.queryByText("SRC-000184")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Find a source to add"), { target: { value: "bob" } });
    fireEvent.click(await screen.findByText("SRC-000185"));
    expect(screen.getByRole("button", { name: "Remove SRC-000185" })).toBeInTheDocument();
  });
});

describe("matchingSources", () => {
  const sources = [
    { id: "SRC-000184", original_file: "raw/vol-01/text.txt", original_locator: "Journal I", source_type: "journal" },
    { id: "SRC-000185", original_file: "raw/letters/bob.txt", original_locator: "To Bob", source_type: "letter" },
  ].map((s) => ({ ...s, recorded_date: "", event_date: "", date_confidence: "exact", contemporaneous: true }));

  it("matches id, file, locator and type, never the ones already chosen", () => {
    expect(matchingSources(sources, "bob", []).map((s) => s.id)).toEqual(["SRC-000185"]);
    expect(matchingSources(sources, "journal", []).map((s) => s.id)).toEqual(["SRC-000184"]);
    expect(matchingSources(sources, "SRC", ["SRC-000184"]).map((s) => s.id)).toEqual(["SRC-000185"]);
    expect(matchingSources(sources, "  ", [])).toEqual([]);
  });
});
