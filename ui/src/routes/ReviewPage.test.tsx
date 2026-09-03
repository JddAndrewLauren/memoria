import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import App from "../App";
import ReviewPage from "./ReviewPage";

const FINDING_WITH_SOURCE = {
  paragraph_index: 7,
  paragraph_text: "The draft states Bob knew by July 15.",
  entry_id: "SUB-people/bob",
  subject_id: "SUB-timeline",
  confidence: "high",
  statement: "Contemporaneous evidence places his probable knowledge on July 18.",
  disagreement_set: [
    { kind: "passage", ref: "02/01#7" },
    { kind: "entry", ref: "SUB-people/bob" },
    { kind: "source", ref: "src-000184-p17" },
  ],
  resolutions: ["settle toward the entry", "settle toward the source", "settle toward the passage"],
  patch: "The draft states Bob knew by July 18.",
  entry_token: "entry-token-one",
};

const FINDING_WITH_BRIEF = {
  paragraph_index: 9,
  paragraph_text: "A paragraph the brief did not ask for.",
  entry_id: "SUB-events/acquisition",
  subject_id: "SUB-events",
  confidence: "low",
  statement: "The brief scopes this section to the acquisition; this paragraph is elsewhere.",
  disagreement_set: [
    { kind: "passage", ref: "02/01#9" },
    { kind: "brief", ref: "SEC-0001" },
  ],
  resolutions: ["rewrite the passage", "open a conversation about the brief"],
  patch: null,
  entry_token: "entry-token-two",
};

const REVIEW = {
  section_id: "SEC-0001",
  chapter_number: 2,
  section_number: 1,
  findings: [FINDING_WITH_SOURCE, FINDING_WITH_BRIEF],
  verdicts_current: 14,
  verdicts_not_current: 2,
  token: "token-one",
  sessions: ["SES-20260912-1432", "SES-20260913-0900"],
};

const CITATION = {
  ref: "src-000184-p17",
  citation: "SRC-000184 ¶17",
  text: "Bob rang on the eighteenth to say he had only just heard.",
  record: {
    id: "SRC-000184",
    source_type: "journal",
    recorded_date: "Jul. 18.",
    event_date: "Jul. 18., 2011",
    date_confidence: "exact",
    contemporaneous: true,
    original_file: "raw/vol-01/text.txt",
    original_locator: "Journal I, entry dated Jul. 18.",
  },
  paragraph: 17,
  anchor: "src-000184-p17",
  overlay: { entry_links: ["SUB-people/bob"], exclusions: [], citing_settlements: [] },
};

type Overrides = {
  review?: Record<string, unknown>;
  // What each successive read of the review serves; the last one repeats.
  reviews?: Record<string, unknown>[];
  onPut?: (url: string, body: unknown) => Response;
  onPost?: (url: string, body: unknown) => Response;
};

function stubApi(overrides: Overrides = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "PUT") {
        const handler =
          overrides.onPut ??
          (() =>
            new Response(
              JSON.stringify({ paragraph_index: 7, text: "applied", token: "token-two" }),
              { status: 200 },
            ));
        return handler(url, JSON.parse(String(init.body)));
      }
      if (init?.method === "POST") {
        const handler =
          overrides.onPost ??
          (() =>
            new Response(
              JSON.stringify({
                entry_id: "SUB-people/bob",
                settled_line: "[settled] knew by July 18 — SUB-people/bob, chosen over SRC-000184 ¶17, 2026-09-03",
                claim_id: "CLM-0001",
              }),
              { status: 200 },
            ));
        return handler(url, JSON.parse(String(init.body)));
      }
      if (url.includes("/review")) {
        const queued = overrides.reviews;
        const served =
          queued && queued.length > 0 ? (queued.length > 1 ? queued.shift() : queued[0]) : overrides.review;
        return new Response(JSON.stringify(served ?? REVIEW), { status: 200 });
      }
      if (url.includes("/api/read?ref=")) {
        return new Response(JSON.stringify(CITATION), { status: 200 });
      }
      if (url.includes("/api/sources") || url.includes("/api/subjects") || url.includes("/api/manuscript")) {
        return new Response(JSON.stringify({ items: [], chapters: [], total: 0, limit: 0, offset: 0, is_built: true }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({ detail: `unexpected ${url}` }), { status: 404 });
    }),
  );
}

function fetchCalls(): string[] {
  return (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map((call) =>
    String(call[0]),
  );
}

function renderReview() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/sections/SEC-0001/review"]}>
        <Routes>
          <Route path="/" element={<App />}>
            <Route path="sections/:sectionId/review" element={<ReviewPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the Review surface", () => {
  beforeEach(() => stubApi());
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("renders findings as disagreement sets with their admissible resolutions", async () => {
    renderReview();

    expect(await screen.findByText(/Contemporaneous evidence places/)).toBeInTheDocument();
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;
    expect(within(card).getByText("Disagreement set")).toBeInTheDocument();
    expect(within(card).getByText("passage · ¶7")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "entry · SUB-people/bob" })).toHaveAttribute(
      "href",
      "/subjects/SUB-people/entries/bob",
    );
    expect(within(card).getByRole("button", { name: "source · src-000184-p17" })).toBeInTheDocument();
    expect(within(card).getByText("settle toward the entry")).toBeInTheDocument();
    expect(within(card).getByText("settle toward the source")).toBeInTheDocument();
    expect(within(card).getByText("settle toward the passage")).toBeInTheDocument();
    expect(within(card).getByText("raised by SUB-timeline")).toBeInTheDocument();
  });

  it("takes its labels and counts from the data, not from part 19's example content", async () => {
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);

    expect(screen.getByText("2 findings")).toBeInTheDocument();
    const bar = screen.getByText("2 findings").closest("div") as HTMLElement;
    expect(within(bar).getByText("high")).toBeInTheDocument();
    expect(within(bar).getByText("low")).toBeInTheDocument();
    expect(within(bar).queryByText("moderate")).not.toBeInTheDocument();
    expect(screen.getByText("14 judgements current · 2 not current")).toBeInTheDocument();
    for (const example of [/contradicted/i, /overstated/i, /hindsight leakage/i, /supported/i, /IMP-/]) {
      expect(screen.queryByText(example)).not.toBeInTheDocument();
    }
  });

  it("names no example verdict in its own source", () => {
    // vitest runs from `ui/` (vitest.config.ts scopes `include` to src/).
    const source = readFileSync(join(process.cwd(), "src", "routes", "ReviewPage.tsx"), "utf8");
    for (const example of ["CONTRADICTED", "OVERSTATED", "HINDSIGHT", "SUPPORTED", "IMP-"]) {
      // Part 19 §19.3's verdicts are example content. The one place a name
      // may appear is the comment saying so - never a label, a map or a type.
      expect(source.split(example).length - 1, example).toBeLessThanOrEqual(1);
    }
  });

  it("offers view evidence, preview diff, apply and settle, and no path that edits a brief", async () => {
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);

    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;
    const actions = within(card)
      .getAllByRole("button")
      .map((button) => button.textContent?.trim())
      .filter((label) => label && !label.startsWith("source ·"));
    expect(actions).toEqual(["View evidence", "Preview diff", "Apply", "Settle"]);

    // The passage + brief finding: the brief is a member, rendered as text,
    // and its resolution is a conversation - there is no control on this
    // surface whose label mentions editing, rewriting or opening a brief.
    const briefCard = screen.getByText(/The brief scopes this section/).closest("li") as HTMLElement;
    expect(within(briefCard).getByText("brief · SEC-0001")).toBeInTheDocument();
    expect(within(briefCard).getByText("open a conversation about the brief")).toBeInTheDocument();
    for (const control of screen.getAllByRole("button").concat(screen.getAllByRole("link"))) {
      expect(control.textContent ?? "").not.toMatch(/brief/i);
    }
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    // Settle is live on the three-way set (#33), and absent as an act on a
    // set whose resolutions are a rewrite or a conversation.
    expect(within(card).getByRole("button", { name: "Settle" })).toBeEnabled();
    expect(within(briefCard).getByRole("button", { name: "Settle" })).toBeDisabled();
  });

  it("settles a finding through the write path with the entry's token and the session it happened in", async () => {
    let received: unknown = null;
    let receivedUrl = "";
    stubApi({
      // The settlement silences its finding: the second read drops it.
      reviews: [REVIEW, { ...REVIEW, findings: [FINDING_WITH_BRIEF] }],
      onPost: (url, body) => {
        receivedUrl = url;
        received = body;
        return new Response(
          JSON.stringify({
            entry_id: "SUB-people/bob",
            settled_line: "[settled] knew by July 18 — SUB-people/bob, chosen over SRC-000184 ¶17, 2026-09-03",
            claim_id: "CLM-0001",
          }),
          { status: 200 },
        );
      },
    });
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "Settle" }));
    const form = within(card).getByRole("form", { name: "Settle this finding" });
    // The sides offered are the set's own resolutions, and the sessions
    // offered are the ones that touched the section.
    expect(within(form).getAllByRole("radio").map((radio) => (radio as HTMLInputElement).value)).toEqual([
      "entry",
      "source",
      "passage",
    ]);
    expect(within(form).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "SES-20260912-1432",
      "SES-20260913-0900",
    ]);
    expect(within(form).getByRole("button", { name: "Record settlement" })).toBeDisabled();

    fireEvent.click(within(form).getByRole("radio", { name: "the entry" }));
    fireEvent.change(within(form).getByLabelText("Proposition"), { target: { value: "knew by July 18" } });
    fireEvent.change(within(form).getByLabelText("Reason"), {
      target: { value: "the journal entry is contemporaneous" },
    });
    fireEvent.change(within(form).getByLabelText("Session"), { target: { value: "SES-20260913-0900" } });
    fireEvent.click(within(form).getByRole("button", { name: "Record settlement" }));

    await waitFor(() => expect(received).not.toBeNull());
    expect(receivedUrl).toBe("/api/sections/SEC-0001/settlements");
    expect(received).toEqual({
      entry_id: "SUB-people/bob",
      disagreement_set: FINDING_WITH_SOURCE.disagreement_set,
      side: "entry",
      proposition: "knew by July 18",
      reason: "the journal entry is contemporaneous",
      session_id: "SES-20260913-0900",
      entry_token: "entry-token-one",
    });
    expect(await screen.findByText(/Settled on SUB-people\/bob as CLM-0001/)).toBeInTheDocument();
    // The settlement moved the entry, so the review is re-read - and the
    // finding it silenced leaves, while the record of the act stays.
    await waitFor(() =>
      expect(fetchCalls().filter((url) => url.endsWith("/review")).length).toBeGreaterThan(1),
    );
    await waitFor(() =>
      expect(screen.queryByText(/Contemporaneous evidence places/)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/Settled on SUB-people\/bob as CLM-0001/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Settle this finding" })).not.toBeInTheDocument();
  });

  it("shows the server's reason when a settlement is refused", async () => {
    stubApi({
      onPost: () =>
        new Response(JSON.stringify({ detail: "a settlement's reason is one non-empty line" }), {
          status: 400,
        }),
    });
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "Settle" }));
    const form = within(card).getByRole("form", { name: "Settle this finding" });
    fireEvent.change(within(form).getByLabelText("Proposition"), { target: { value: "knew by July 18" } });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "x" } });
    fireEvent.click(within(form).getByRole("button", { name: "Record settlement" }));

    expect(await within(form).findByText("a settlement's reason is one non-empty line")).toBeInTheDocument();
    expect(screen.queryByText(/The entry changed since/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Settled on/)).not.toBeInTheDocument();
  });

  it("asks for the session in a text field when no session touched the section", async () => {
    stubApi({ review: { ...REVIEW, sessions: [] } });
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "Settle" }));
    const form = within(card).getByRole("form", { name: "Settle this finding" });
    const session = within(form).getByLabelText("Session");
    expect(session.tagName).toBe("INPUT");
    expect(within(form).queryByRole("combobox")).not.toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText("Proposition"), { target: { value: "knew by July 18" } });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "contemporaneous" } });
    expect(within(form).getByRole("button", { name: "Record settlement" })).toBeDisabled();

    fireEvent.change(session, { target: { value: "SES-20260913-0900" } });
    expect(within(form).getByRole("button", { name: "Record settlement" })).toBeEnabled();
  });

  it("closes the settlement form on Cancel without settling", async () => {
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "Settle" }));
    const form = within(card).getByRole("form", { name: "Settle this finding" });
    fireEvent.click(within(form).getByRole("button", { name: "Cancel" }));

    expect(within(card).queryByRole("form", { name: "Settle this finding" })).not.toBeInTheDocument();
    expect(fetchCalls().some((url) => url.endsWith("/settlements"))).toBe(false);
  });

  it("tells an entry that moved apart from a failure and settles nothing", async () => {
    stubApi({
      onPost: () =>
        new Response(JSON.stringify({ detail: "subjects/people/bob.md changed since the review was read" }), {
          status: 409,
        }),
    });
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "Settle" }));
    const form = within(card).getByRole("form", { name: "Settle this finding" });
    fireEvent.change(within(form).getByLabelText("Proposition"), { target: { value: "knew by July 18" } });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "contemporaneous" } });
    fireEvent.click(within(form).getByRole("button", { name: "Record settlement" }));

    expect(await screen.findByText(/The entry changed since this review was read/)).toBeInTheDocument();
    expect(screen.queryByText(/Settled on/)).not.toBeInTheDocument();
  });

  it("opens the evidence in the slide-over and previews the diff", async () => {
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "View evidence" }));
    expect(await screen.findByText(/Bob rang on the eighteenth/)).toBeInTheDocument();
    expect(fetchCalls()).toContain("/api/read?ref=src-000184-p17");

    fireEvent.click(within(card).getByRole("button", { name: "Preview diff" }));
    expect(within(card).getByText("15.")).toHaveProperty("tagName", "DEL");
    expect(within(card).getByText("18.")).toHaveProperty("tagName", "INS");
  });

  it("applies a change through the write path with the draft's token", async () => {
    let received: unknown = null;
    let receivedUrl = "";
    stubApi({
      onPut: (url, body) => {
        receivedUrl = url;
        received = body;
        return new Response(
          JSON.stringify({ paragraph_index: 7, text: FINDING_WITH_SOURCE.patch, token: "token-two" }),
          { status: 200 },
        );
      },
    });
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(received).not.toBeNull());
    expect(receivedUrl).toBe("/api/sections/SEC-0001/paragraphs/7");
    expect(received).toEqual({ token: "token-one", text: FINDING_WITH_SOURCE.patch });
    // The write moved the draft, so the review is re-read rather than
    // trusted: the card shown next is what the audit still stands behind.
    await waitFor(() =>
      expect(fetchCalls().filter((url) => url.endsWith("/review")).length).toBeGreaterThan(1),
    );
  });

  it("tells a stale draft apart from a failure and writes nothing", async () => {
    stubApi({
      onPut: () =>
        new Response(JSON.stringify({ detail: "draft.md changed since it was read" }), {
          status: 409,
        }),
    });
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const card = screen.getByText(/Contemporaneous evidence places/).closest("li") as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: "Apply" }));

    expect(await screen.findByText(/The draft changed since this review was read/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reload the review/ })).toBeInTheDocument();
  });

  it("does not offer apply or a diff for a finding with no proposed rewrite", async () => {
    renderReview();
    await screen.findByText(/The brief scopes this section/);
    const card = screen.getByText(/The brief scopes this section/).closest("li") as HTMLElement;

    expect(within(card).getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(within(card).getByRole("button", { name: "Preview diff" })).toBeDisabled();
    expect(within(card).queryByRole("button", { name: "View evidence" })).not.toBeInTheDocument();
  });

  it("reads once when opened and nothing populates it in the background", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderReview();
    await screen.findByText(/Contemporaneous evidence places/);
    const before = fetchCalls().filter((url) => url.endsWith("/review")).length;
    expect(before).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000);
    });

    expect(fetchCalls().filter((url) => url.endsWith("/review")).length).toBe(1);
  });

  it("tells a section nobody audited apart from an audit that found nothing", async () => {
    stubApi({ review: { ...REVIEW, findings: [], verdicts_current: 0, verdicts_not_current: 6 } });
    renderReview();
    expect(await screen.findByText(/No audit has been run on this section/)).toBeInTheDocument();
    expect(screen.getByText("0 findings")).toBeInTheDocument();

    vi.unstubAllGlobals();
    stubApi({ review: { ...REVIEW, findings: [], verdicts_current: 6, verdicts_not_current: 0 } });
    renderReview();
    expect(await screen.findByText(/The audit found nothing to disagree with/)).toBeInTheDocument();
  });
});
