import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SourceDetailPage from "./SourceDetailPage";
import { CitationPanelProvider } from "../components/CitationPanel";

const SOURCE_DETAIL = {
  id: "SRC-000184",
  source_type: "journal",
  recorded_date: "Jul. 17.",
  event_date: "Jul. 17., 2011",
  date_confidence: "exact",
  contemporaneous: true,
  original_file: "raw/vol-01/text.txt",
  original_locator: "Journal I, entry dated Jul. 17.",
  paragraphs: [
    { anchor: "src-000184-p1", text: "A blue heron flew over." },
    { anchor: "src-000184-p2", text: "I called Bob that evening." },
  ],
  apparatus: [
    {
      editorial_type: "footnote",
      retrospective: true,
      linked_record_id: "SRC-000184",
      linked_anchor: "src-000184-p1",
      text: "Added by the editor in 2019.",
    },
  ],
};

const READ_RESPONSE = {
  ref: "src-000184-p2",
  citation: "SRC-000184 P2",
  text: "I called Bob that evening.",
  record: {
    id: "SRC-000184",
    source_type: "journal",
    recorded_date: "Jul. 17.",
    event_date: "Jul. 17., 2011",
    date_confidence: "exact",
    contemporaneous: true,
    original_file: "raw/vol-01/text.txt",
    original_locator: "Journal I, entry dated Jul. 17.",
  },
  paragraph: 2,
  overlay: { entry_links: ["SUB-people/bob"], exclusions: [], citing_settlements: [] },
};

function renderAt(path: string) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <CitationPanelProvider>
          <Routes>
            <Route path="/sources/:id" element={<SourceDetailPage />} />
          </Routes>
        </CitationPanelProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the source viewer (§19.4)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/sources/SRC-000184/raw")) {
          return new Response(JSON.stringify({ text: "raw", original_locator: "x" }), {
            status: 200,
          });
        }
        if (url.includes("/api/sources/SRC-000184")) {
          return new Response(JSON.stringify(SOURCE_DETAIL), { status: 200 });
        }
        if (url.includes("/api/read")) {
          return new Response(JSON.stringify(READ_RESPONSE), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders temporal metadata, date_confidence and the original locator", async () => {
    renderAt("/sources/SRC-000184");

    expect(await screen.findByText("SRC-000184")).toBeInTheDocument();
    expect(screen.getByText("Contemporaneous")).toBeInTheDocument();
    expect(screen.getByText(/exact/)).toBeInTheDocument();
    expect(screen.getByText("Journal I, entry dated Jul. 17.")).toBeInTheDocument();
  });

  it("highlights the cited paragraph named by the URL's anchor, and shows its backlinks", async () => {
    renderAt("/sources/SRC-000184#src-000184-p2");

    const cited = await screen.findByText(/I called Bob that evening\./);
    expect(cited.closest("p")).toHaveClass("cited");
    const uncited = screen.getByText(/A blue heron flew over\./).closest("p");
    expect(uncited).not.toHaveClass("cited");

    expect(await screen.findByText("Cited by")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "people/bob" })).toBeInTheDocument();
  });

  it("shows no CITED BY rail when the source is browsed without a citation", async () => {
    renderAt("/sources/SRC-000184");

    await screen.findByText("SRC-000184");
    expect(screen.queryByText("Cited by")).not.toBeInTheDocument();
  });

  it("renders editorial apparatus beside the paragraph it annotates, marked retrospective and by type, never inline", async () => {
    renderAt("/sources/SRC-000184");

    await screen.findByText("SRC-000184");
    const note = screen.getByText("Added by the editor in 2019.");
    expect(note).toBeInTheDocument();
    expect(screen.getByText("footnote")).toBeInTheDocument();
    expect(screen.getByText("retrospective")).toBeInTheDocument();
    // Never folded into the evidence paragraph's own text.
    expect(screen.getByText(/A blue heron flew over\./).textContent).not.toContain(
      "Added by the editor",
    );
  });

  it("renders an honest absence when a record carries no date at all", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            ...SOURCE_DETAIL,
            recorded_date: "",
            event_date: "",
            date_confidence: "chapter-only",
            apparatus: [],
          }),
          { status: 200 },
        ),
      ),
    );

    renderAt("/sources/SRC-000184");

    expect(await screen.findByText("no date resolved")).toBeInTheDocument();
    // The context stays recoverable from original_locator rather than an
    // invented date.
    expect(screen.getByText("Journal I, entry dated Jul. 17.")).toBeInTheDocument();
  });
});
