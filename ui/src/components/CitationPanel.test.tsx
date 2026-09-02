import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CitationPanelProvider } from "./CitationPanel";
import { useCitationPanel } from "../lib/citationPanel";

const PARAGRAPH_CITATION = {
  ref: "src-000184-p17",
  citation: "SRC-000184 P17",
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
  paragraph: 17,
  overlay: { entry_links: ["SUB-people/bob"], exclusions: [], citing_settlements: [] },
};

const ENTRY_CITATION = {
  ref: "SUB-people/bob",
  citation: "SUB-people/bob",
  text: "---\nid: SUB-people/bob\n---\nBob's own words.",
  record: null,
  paragraph: null,
  overlay: null,
};

function OpenButton({ citationRef }: { citationRef: string }) {
  const { open } = useCitationPanel();
  return (
    <button type="button" onClick={() => open(citationRef)}>
      open {citationRef}
    </button>
  );
}

function renderProvider() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CitationPanelProvider>
          <OpenButton citationRef="src-000184-p17" />
        </CitationPanelProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the slide-over citation panel (§19.9)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("ref=src-000184-p17")) {
          return new Response(JSON.stringify(PARAGRAPH_CITATION), { status: 200 });
        }
        if (url.includes("ref=SUB-people%2Fbob")) {
          return new Response(JSON.stringify(ENTRY_CITATION), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens on a citation, showing the cited text, record badges and its backlinks", async () => {
    renderProvider();

    fireEvent.click(screen.getByRole("button", { name: /open src-000184-p17/i }));

    expect(await screen.findByText("I called Bob that evening.")).toBeInTheDocument();
    expect(screen.getByText("SRC-000184")).toBeInTheDocument();
    expect(screen.getByText("Contemporaneous")).toBeInTheDocument();
    expect(screen.getByText("Cited by")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "people/bob" })).toBeInTheDocument();
  });

  it("a backlink is clickable into the same panel, traversing the other direction", async () => {
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: /open src-000184-p17/i }));
    await screen.findByText("Cited by");

    fireEvent.click(screen.getByRole("button", { name: "people/bob" }));

    expect(await screen.findByText(/Bob's own words\./)).toBeInTheDocument();
    // The entry has no record/overlay of its own, so no badges or a second
    // CITED BY rail render for it - it is a plain read, the same way a
    // subject reference reads bare (memoria.records.read).
    expect(screen.queryByText("Cited by")).not.toBeInTheDocument();
    // Back returns to the paragraph citation, not a second panel stacked on
    // top of it.
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
  });

  it("back returns to the previous reference in the stack", async () => {
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: /open src-000184-p17/i }));
    await screen.findByText("Cited by");
    fireEvent.click(screen.getByRole("button", { name: "people/bob" }));
    await screen.findByText(/Bob's own words\./);

    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(await screen.findByText("I called Bob that evening.")).toBeInTheDocument();
  });

  it("closing the panel removes it entirely - the underlying page never navigated", async () => {
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: /open src-000184-p17/i }));
    await screen.findByRole("dialog", { name: "Citation" });

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Citation" })).not.toBeInTheDocument();
    });
    // The opener is still exactly where it was - nothing routed away.
    expect(screen.getByRole("button", { name: /open src-000184-p17/i })).toBeInTheDocument();
  });
});
