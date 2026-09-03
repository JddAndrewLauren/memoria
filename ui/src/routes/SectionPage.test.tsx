import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SectionPage from "./SectionPage";

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

function stubApi(section: Record<string, unknown> = SECTION) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/sections/")) {
        return new Response(JSON.stringify(section), { status: 200 });
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
        <Routes>
          <Route path="/sections/:sectionId" element={<SectionPage />} />
        </Routes>
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
    expect(screen.getByText(/DEC-0088 · SES-20260912-1432-abcdef#T017/)).toBeInTheDocument();
    expect(screen.getByText("Did Bob receive the July 14 document?")).toBeInTheDocument();
    expect(screen.getByText("SES-20260912-1432-abcdef")).toBeInTheDocument();
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
    // Exactly one read was made to render this page: the section itself.
    const calls = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.map((call) => String(call[0]))).toEqual(["/api/sections/SEC-0003"]);
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
