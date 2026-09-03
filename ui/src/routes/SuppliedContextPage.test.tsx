import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import App from "../App";
import SuppliedContextPage, { REFRESH_INTERVAL_MS } from "./SuppliedContextPage";

// A session that assembled the section, fell back on one phrase, and then
// read a paragraph the working context never loaded.
const SESSION = {
  session_id: "SES-20260902-1000-aaaaaaaaaaaa",
  assembled_at: "2026-09-02T10:00:00+00:00",
  briefs: ["SEC-0001"],
  entries: [{ entry_id: "SUB-people/bob", matched_by: ["bob"], sources: ["src-000184-p1"] }],
  fallbacks: [{ subject_id: "SUB-people", candidate_id: "CAN-0001", label: "Carol" }],
  unconfirmed: false,
  empty: false,
  served_since: [
    { tool: "read", ref: "src-000201-p3", served: ["SRC-000201 ¶3"] },
    { tool: "search_text", ref: null, served: ["src-000184-p1", "src-000199-p2"] },
  ],
};

const ACCOUNT = { section_id: "SEC-0001", sessions: [SESSION] };

function stubApi(account: Record<string, unknown> = ACCOUNT) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/supplied-context")) {
        return new Response(JSON.stringify(account), { status: 200 });
      }
      if (url.includes("/api/sources") || url.includes("/api/subjects") || url.includes("/api/manuscript")) {
        return new Response(
          JSON.stringify({ items: [], chapters: [], total: 0, limit: 0, offset: 0, is_built: true }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: `unexpected ${url}` }), { status: 404 });
    }),
  );
}

function accountReads(): number {
  return (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.filter((call) =>
    String(call[0]).endsWith("/supplied-context"),
  ).length;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/sections/SEC-0001/supplied-context"]}>
        <Routes>
          <Route path="/" element={<App />}>
            <Route path="sections/:sectionId/supplied-context" element={<SuppliedContextPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const FIGURES = [/\d\s*%/, /\btokens?\b/i, /\bbytes?\b/i, /\bcapacity\b/i, /\bpercent/i, /\d+\s*\/\s*\d+/];
const MODEL_CLAIMS = [
  /\bhas seen\b/i,
  /\bhave seen\b/i,
  /\bmodel holds\b/i,
  /\bmodel knows\b/i,
  /\bin context\b/i,
  /\bcontext window\b/i,
  /\bcontext usage\b/i,
  /\bbudget\b/i,
];

describe("the supplied-context surface", () => {
  beforeEach(() => stubApi());
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reports the entries the declared scope resolved to, and the briefs assembly loaded", async () => {
    renderPage();

    const working = await screen.findByRole("region", { name: "Working context" });
    expect(within(working).getByText("SEC-0001")).toBeInTheDocument();
    expect(within(working).getByRole("link", { name: "SUB-people/bob" })).toHaveAttribute(
      "href",
      "/subjects/SUB-people/entries/bob",
    );
    expect(within(working).getByText(/named by bob/)).toBeInTheDocument();
    // The gathered set is reported, not loaded (#38).
    expect(within(working).getByText(/gathered set of 1 source, reported as identifiers, not loaded/)).toBeInTheDocument();
  });

  it("names a fallback to an unpromoted candidate explicitly, never in silence", async () => {
    renderPage();

    const working = await screen.findByRole("region", { name: "Working context" });
    const fallback = within(working).getByText(/named no entry/).closest("li") as HTMLElement;
    expect(fallback).toHaveTextContent("“Carol” named no entry");
    expect(fallback).toHaveTextContent("fell back to the unpromoted candidate CAN-0001 under SUB-people");
    expect(fallback).toHaveTextContent("nothing of it was loaded");
  });

  it("keeps the reads served since assembly apart from what assembly loaded", async () => {
    renderPage();

    const working = await screen.findByRole("region", { name: "Working context" });
    const since = screen.getByRole("region", { name: "Served since assembly" });

    // The read beyond the assembly is in the served-since half only.
    expect(within(since).getByText("SRC-000201 ¶3")).toBeInTheDocument();
    expect(within(working).queryByText(/SRC-000201/)).not.toBeInTheDocument();
    // The entry assembly resolved is in the working-context half only.
    expect(within(working).getByRole("link", { name: "SUB-people/bob" })).toBeInTheDocument();
    expect(within(since).queryByText(/SUB-people\/bob/)).not.toBeInTheDocument();
    // Each served read names its tool and what it served.
    expect(within(since).getByText("read")).toBeInTheDocument();
    expect(within(since).getByText("asked for src-000201-p3")).toBeInTheDocument();
    expect(within(since).getByText("text search")).toBeInTheDocument();
    expect(within(since).getByText("src-000184-p1, src-000199-p2")).toBeInTheDocument();
    // The summary line counts domain units: briefs, entries, fallbacks, sources served.
    expect(screen.getByText("1 brief · 1 entry · 1 fallback · 3 sources served since")).toBeInTheDocument();
  });

  it("shows no token, byte, percentage or capacity figure anywhere", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Working context" });

    const text = document.body.textContent ?? "";
    for (const figure of FIGURES) {
      expect(text, String(figure)).not.toMatch(figure);
    }
    // And there is no path to one: the page's own source names no such
    // figure except in the comment saying it never will.
    const source = readFileSync(join(process.cwd(), "src", "routes", "SuppliedContextPage.tsx"), "utf8");
    for (const word of ["token", "byte", "percent", "capacity"]) {
      expect(source.split(word).length - 1, word).toBeLessThanOrEqual(1);
    }
  });

  it("claims what Memoria supplied and never what the model holds or has seen", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Working context" });

    const text = document.body.textContent ?? "";
    expect(text).toMatch(/What Memoria supplied for/);
    expect(text).toMatch(/what Memoria served, never of what the client kept/);
    for (const claim of MODEL_CLAIMS) {
      expect(text, String(claim)).not.toMatch(claim);
    }
    const source = readFileSync(join(process.cwd(), "src", "routes", "SuppliedContextPage.tsx"), "utf8");
    expect(source).not.toMatch(/has seen|context window|in context|what the model (holds|knows)/i);
  });

  it("re-reads while open and does nothing once closed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const page = renderPage();
    await screen.findByRole("region", { name: "Working context" });
    expect(accountReads()).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2 + 100);
    });
    const whileOpen = accountReads();
    expect(whileOpen).toBeGreaterThan(1);

    page.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 4);
    });
    expect(accountReads()).toBe(whileOpen);
  });

  it("says so when no session has assembled the section", async () => {
    stubApi({ section_id: "SEC-0001", sessions: [] });
    renderPage();

    expect(await screen.findByText(/No session has assembled this section/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Working context" })).not.toBeInTheDocument();
  });

  it("tells a scope that named nothing apart from one whose reads are still to come", async () => {
    stubApi({
      section_id: "SEC-0001",
      sessions: [{ ...SESSION, entries: [], fallbacks: [], empty: true, unconfirmed: true, served_since: [] }],
    });
    renderPage();

    const working = await screen.findByRole("region", { name: "Working context" });
    expect(within(working).getByText("The declared scope named no entry.")).toBeInTheDocument();
    expect(screen.getByText("unconfirmed brief")).toBeInTheDocument();
    const since = screen.getByRole("region", { name: "Served since assembly" });
    expect(within(since).getByText(/Nothing has been served to this session since assembly/)).toBeInTheDocument();
  });
});
