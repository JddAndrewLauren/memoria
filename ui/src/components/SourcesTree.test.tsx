import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SourcesTree } from "./SourcesTree";
import { AddRawUnitsContext } from "../lib/addRawUnitsContext";

/**
 * The `SOURCES` tree's rows carry the raw unit's conversion state as a
 * glyph, joined from the ingestion status by id, and the tree's foot links
 * to the `/ingestion` page - the one place a raw unit that never became a
 * record (failed, no converter) is visible at all.
 */
const SOURCES = {
  items: [
    {
      id: "SRC-000002",
      source_type: "journal",
      recorded_date: "",
      event_date: "",
      date_confidence: "unresolved",
      contemporaneous: true,
      original_file: "raw/one.txt",
      original_locator: "(whole file)",
    },
    {
      id: "SRC-000004",
      source_type: "journal",
      recorded_date: "",
      event_date: "",
      date_confidence: "unresolved",
      contemporaneous: true,
      original_file: "raw/two.txt",
      original_locator: "(whole file)",
    },
  ],
  total: 2,
  limit: 10000,
  offset: 0,
  is_built: true,
};

function unit(id: string, converted: string) {
  return {
    id,
    path: `raw/${id}.txt`,
    deleted: false,
    converted,
    failure_reason: converted === "failed" ? "boom" : null,
    record_paragraphs: converted === "failed" ? null : 1,
    indexed_paragraphs: converted === "failed" ? null : 1,
    extracted_paragraphs: converted === "failed" ? null : 0,
    email_message_index: null,
  };
}

const INGESTION = {
  units: [unit("SRC-000001", "failed"), unit("SRC-000002", "current"), unit("SRC-000004", "out_of_date")],
  counts: { current: 1, out_of_date: 1, failed: 1 },
  unnumbered: [],
  is_normalized: true,
  is_indexed: true,
  generated_at: "2026-09-03T10:00:00+00:00",
};

function renderTree() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SourcesTree />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the SOURCES tree's ingestion glyphs", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/ingestion")) return new Response(JSON.stringify(INGESTION));
        if (url.includes("/api/sources")) return new Response(JSON.stringify(SOURCES));
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("offers to add sources from the app, through whatever App hung on the context", async () => {
    const open = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AddRawUnitsContext.Provider value={open}>
            <SourcesTree />
          </AddRawUnitsContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "+ Add sources…" }));

    expect(open).toHaveBeenCalledTimes(1);
  });

  it("marks each row with its raw unit's conversion state", async () => {
    renderTree();
    fireEvent.click(await screen.findByText("journal · 2"));

    const current = await screen.findByRole("link", { name: /SRC-000002/ });
    expect(current).toContainElement(screen.getByRole("img", { name: "converted" }));
    const outOfDate = screen.getByRole("link", { name: /SRC-000004/ });
    expect(outOfDate).toContainElement(screen.getByRole("img", { name: "out of date" }));
  });

  it("opens the Sources page from its header, and flags what the tree cannot show", async () => {
    renderTree();

    expect(screen.getByRole("link", { name: "Sources" })).toHaveAttribute("href", "/sources");
    expect(screen.getByRole("button", { name: "Collapse Sources" })).toBeInTheDocument();
    // The counts arrive with the ingestion status, one read after the tree.
    const flag = await screen.findByRole("link", { name: "1 failed" });
    expect(flag).toHaveAttribute("href", "/sources");
  });

  it("still draws the rows when the ingestion status is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/ingestion"))
          return new Response(JSON.stringify({ detail: "no" }), { status: 500 });
        if (url.includes("/api/sources")) return new Response(JSON.stringify(SOURCES));
        return new Response("{}", { status: 404 });
      }),
    );
    renderTree();
    fireEvent.click(await screen.findByText("journal · 2"));

    expect(await screen.findByRole("link", { name: "SRC-000002" })).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
