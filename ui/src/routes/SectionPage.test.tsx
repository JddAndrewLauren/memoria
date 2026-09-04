import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SectionPage from "./SectionPage";
import { CitationPanelProvider } from "../components/CitationPanel";

const SECTION = {
  id: "SEC-0003",
  chapter_id: "CHP-0008",
  chapter_number: 8,
  section_number: 3,
  brief:
    "Show the first point at which the narrator realizes that Bob may have known more than he admitted.",
  unconfirmed: false,
  has_draft: true,
  paragraphs: [
    { index: 1, text: "The opening paragraph, audited and current.", not_current: [] },
    {
      index: 2,
      text: "The middle paragraph, which Bob's entry changed underneath.",
      not_current: [
        { entry_id: "SUB-people/bob", kind: "engagement", cause: "entry_changed" },
        { entry_id: "SUB-people/bob", kind: "audit_verdict", cause: "entry_changed" },
        { entry_id: "SUB-events/acquisition", kind: "audit_verdict", cause: "never_audited" },
      ],
    },
  ],
  scope: [
    { entry_id: "SUB-people/bob", matched_by: ["bob", "Bob"] },
    { entry_id: "SUB-events/acquisition", matched_by: ["acquisition"] },
  ],
  scope_empty: false,
  sessions: ["SES-20260912-1432-abcdef"],
  decisions: [
    {
      id: "DEC-0088",
      text: "Do not reveal Alice's later account until §8.5.",
      citation: "SES-20260912-1432-abcdef#T017",
    },
  ],
  questions: [
    { text: "Did Bob receive the July 14 document?", citation: "SES-20260912-1432-abcdef#T019" },
  ],
};

// What `/api/read?ref=SES-...#T017` serves (#34): the turn, and nothing
// else. The decision's sentence sits in the middle so "lands on the
// sentence" is a real question and not "the turn is the sentence".
const TURN_017 = {
  ref: "SES-20260912-1432-abcdef#T017",
  citation: "SES-20260912-1432-abcdef#T017",
  text: "I have been going back and forth on this. Do not reveal Alice's later account until §8.5. The reader needs to sit with Bob's version first.",
  record: null,
  paragraph: null,
  anchor: null,
  overlay: null,
};

// Settings > Model's answer (ADR-0010): off by default, so the page keeps
// its "from a session" wording and offers no button.
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

function stubApi(
  section: Record<string, unknown> = SECTION,
  model: Record<string, unknown> = MODEL_OFF,
  onAudit?: () => Record<string, unknown>,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/audit") && init?.method === "POST") {
        const body = onAudit?.() ?? {
          accepted: 3,
          findings: 0,
          remaining: 0,
          rejected: [],
          spend: { calls: 3, model: "claude-opus-5" },
        };
        return new Response(JSON.stringify(body), { status: 200 });
      }
      if (url.includes("/api/sections/")) {
        return new Response(JSON.stringify(section), { status: 200 });
      }
      if (url.endsWith("/api/model")) {
        return new Response(JSON.stringify(model), { status: 200 });
      }
      if (url.includes("/api/read?ref=SES-20260912-1432-abcdef%23T017")) {
        return new Response(JSON.stringify(TURN_017), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: `unexpected ${url}` }), { status: 404 });
    }),
  );
}

function renderSection() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/sections/SEC-0003"]}>
        <CitationPanelProvider>
          <Routes>
            <Route path="/sections/:sectionId" element={<SectionPage />} />
            <Route path="*" element={<p>navigated away</p>} />
          </Routes>
        </CitationPanelProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the Section view", () => {
  beforeEach(() => stubApi());
  afterEach(() => vi.unstubAllGlobals());

  it("renders the brief, the draft, the in-scope entries and the not-current tint with its cause", async () => {
    renderSection();

    expect(await screen.findByText(/first point at which the narrator/)).toBeInTheDocument();
    expect(screen.getByText("Purpose")).toBeInTheDocument();

    const current = screen.getByText(/The opening paragraph/).closest("p");
    const stale = screen.getByText(/The middle paragraph/).closest("p");
    expect(current).not.toHaveClass("not-current");
    expect(stale).toHaveClass("not-current");

    // One line per distinct (cause, entry), so the reader learns why, not
    // just that - and the two judgement kinds against the same entry for
    // the same cause collapse into one line.
    expect(
      screen.getByText("not current · entry changed since · SUB-people/bob"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("not current · never audited · SUB-events/acquisition"),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 of 2 paragraphs not current/)).toBeInTheDocument();

    const scope = screen.getByText("In scope").closest("section") as HTMLElement;
    expect(within(scope).getByRole("link", { name: "SUB-people/bob" })).toHaveAttribute(
      "href",
      "/subjects/SUB-people/entries/bob",
    );
    expect(within(scope).getByRole("link", { name: "SUB-events/acquisition" })).toBeInTheDocument();
  });

  it("composes decisions and questions from the sessions that touched the section", async () => {
    renderSection();

    expect(await screen.findByText(/Do not reveal Alice's later account/)).toBeInTheDocument();
    expect(screen.getByText("DEC-0088")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "SES-20260912-1432-abcdef#T017" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Did Bob receive the July 14 document?")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "SES-20260912-1432-abcdef#T019" }),
    ).toBeInTheDocument();
    expect(screen.getByText("SES-20260912-1432-abcdef")).toBeInTheDocument();
  });

  it("opens a decision's citation in the slide-over on the sentence it was decided in, without navigating (#34)", async () => {
    renderSection();
    await screen.findByText(/Do not reveal Alice's later account/);

    fireEvent.click(screen.getByRole("button", { name: "SES-20260912-1432-abcdef#T017" }));

    const panel = await screen.findByRole("dialog", { name: "Citation" });
    expect(await within(panel).findByText(/going back and forth/)).toBeInTheDocument();
    const cited = within(panel).getByTestId("cited-sentence");
    expect(cited.textContent?.trim()).toBe("Do not reveal Alice's later account until §8.5.");
    expect(within(panel).getAllByTestId("cited-sentence")).toHaveLength(1);
    // The mechanism behind "keeps my place": the section is still mounted
    // underneath, and no route changed. Whether the reader's scroll offset
    // survived is the browser walk's question (docs/gates/m4-gate-walk.md).
    expect(screen.queryByText("navigated away")).not.toBeInTheDocument();
    expect(screen.getByText(/first point at which the narrator/)).toBeInTheDocument();
  });

  it("displays no checkpoint and no unresolved-impacts state", async () => {
    renderSection();
    await screen.findByText("Purpose");

    expect(screen.queryByText(/checkpoint/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unresolved impacts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/needs attention/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^next\b/i)).not.toBeInTheDocument();
  });

  it("carries the opener onto the supplied-context surface, and that opener shows no count", async () => {
    renderSection();

    const opener = await screen.findByRole("link", { name: /supplied context/i });
    expect(opener).toHaveAttribute("href", "/sections/SEC-0003/supplied-context");
    // No count, no badge - "opened, not watched" (ADR-0001, #61).
    expect(opener.textContent).not.toMatch(/\d/);
    expect(opener.querySelector("span, sup, [class*=badge]")).toBeNull();
  });

  it("links to Review as the results view rather than running anything itself", async () => {
    renderSection();

    const review = await screen.findByRole("link", { name: /review audit results/i });
    expect(review).toHaveAttribute("href", "/sections/SEC-0003/review");
    // Two reads render this page: the section itself, and whether a
    // direct run is ready (ADR-0010) - which decides only whether the
    // audit's button appears, never runs anything.
    const calls = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.map((call) => String(call[0]))).toEqual(["/api/sections/SEC-0003", "/api/model"]);
    expect(screen.queryByRole("button", { name: /run audit/i })).not.toBeInTheDocument();
    expect(screen.getByText(/audit this section from a session/)).toBeInTheDocument();
  });

  it("offers the audit's button only when direct runs are ready, and refreshes the section after", async () => {
    stubApi(SECTION, MODEL_READY);
    renderSection();

    const button = await screen.findByRole("button", { name: /run audit/i });
    expect(screen.queryByText(/from a session/)).not.toBeInTheDocument();
    fireEvent.click(button);

    await screen.findByText(/3 judgements recorded/);
    const calls = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    const audit = calls.find((call) => String(call[0]).endsWith("/audit"));
    expect(audit).toBeDefined();
    expect(String(audit![0])).toBe("/api/sections/SEC-0003/audit");
    expect(JSON.parse(String((audit![1] as RequestInit).body))).toEqual({ limit: 20 });
    await waitFor(() =>
      expect(calls.filter((call) => String(call[0]) === "/api/sections/SEC-0003").length).toBe(2),
    );
  });

  it("renders an unconfirmed brief, an empty scope and a planned section honestly", async () => {
    stubApi({
      ...SECTION,
      unconfirmed: true,
      has_draft: false,
      paragraphs: [],
      scope: [],
      scope_empty: true,
      sessions: [],
      decisions: [],
      questions: [],
    });
    renderSection();

    expect(await screen.findByText("unconfirmed brief")).toBeInTheDocument();
    expect(screen.getByText(/A planned section/)).toBeInTheDocument();
    expect(screen.getByText(/The brief names no entry/)).toBeInTheDocument();
    expect(screen.getByText(/No decisions from the sessions/)).toBeInTheDocument();
    expect(screen.getByText(/No open questions from the sessions/)).toBeInTheDocument();
    expect(screen.getByText(/No session has touched this section/)).toBeInTheDocument();
  });
});
