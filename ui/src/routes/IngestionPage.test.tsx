import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import IngestionPage from "./IngestionPage";

const STATUS = {
  units: [
    {
      id: "SRC-000001",
      path: "raw/bad.pdf",
      deleted: false,
      converted: "failed",
      failure_reason: "PDFSyntaxError: No /Root object",
      record_paragraphs: null,
      indexed_paragraphs: null,
      extracted_paragraphs: null,
      email_message_index: null,
    },
    {
      id: "SRC-000002",
      path: "raw/one.txt",
      deleted: false,
      converted: "current",
      failure_reason: null,
      record_paragraphs: 2,
      indexed_paragraphs: 2,
      extracted_paragraphs: 1,
      email_message_index: null,
    },
    {
      id: "SRC-000003",
      path: "raw/box.mbox",
      deleted: false,
      converted: "container",
      failure_reason: null,
      record_paragraphs: null,
      indexed_paragraphs: null,
      extracted_paragraphs: null,
      email_message_index: null,
    },
    {
      id: "SRC-000004",
      path: "raw/box.mbox",
      deleted: false,
      converted: "out_of_date",
      failure_reason: null,
      record_paragraphs: 3,
      indexed_paragraphs: 3,
      extracted_paragraphs: 3,
      email_message_index: 1,
    },
  ],
  counts: {
    current: 1,
    out_of_date: 1,
    not_yet_converted: 0,
    failed: 1,
    unconvertible: 0,
    container: 1,
    stub: 0,
    deleted: 0,
    indexed: 2,
    extracted_complete: 1,
  },
  is_normalized: true,
  is_indexed: true,
  generated_at: "2026-09-03T10:00:00+00:00",
};

type Stub = (url: string, init?: RequestInit) => Response | Promise<Response>;

function stubFetch(handler: Stub) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(String(input), init),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/ingestion"]}>
        <IngestionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("the ingestion status page", () => {
  it("lists every ledger unit with its three stages, failed ones included", async () => {
    stubFetch((url) => {
      if (url.includes("/api/ingestion")) return json(STATUS);
      if (url.includes("/api/locality")) return json({ is_local: false });
      return json({ detail: "not found" }, 404);
    });
    renderPage();

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);

    // A failed unit is a row - it has no record and so no link - with its
    // reason beside it.
    expect(within(rows[0]).getByText("SRC-000001")).not.toHaveAttribute("href");
    expect(within(rows[0]).getByText("failed")).toBeInTheDocument();
    expect(within(rows[0]).getByText("PDFSyntaxError: No /Root object")).toBeInTheDocument();

    // A converted unit links to its record and shows its counts.
    expect(within(rows[1]).getByRole("link", { name: "SRC-000002" })).toHaveAttribute(
      "href",
      "/sources/SRC-000002",
    );
    expect(within(rows[1]).getByText("converted")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2")).toBeInTheDocument();
    expect(within(rows[1]).getByText("1 of 2")).toBeInTheDocument();

    expect(within(rows[2]).getByText("email export")).toBeInTheDocument();
    expect(within(rows[3]).getByText("out of date")).toBeInTheDocument();
    expect(within(rows[3]).getByText("message 1")).toBeInTheDocument();
  });

  it("tallies the states present and the index's two counts", async () => {
    stubFetch((url) => {
      if (url.includes("/api/ingestion")) return json(STATUS);
      return json({ is_local: false });
    });
    renderPage();

    expect(await screen.findByText("4 raw units")).toBeInTheDocument();
    expect(screen.getByText("2 indexed · 1 fully read by the extraction")).toBeInTheDocument();
    // States with a zero count earn no chip.
    expect(screen.queryByText("no converter")).not.toBeInTheDocument();
  });

  it("says the index is not built rather than showing zeros", async () => {
    stubFetch((url) => {
      if (url.includes("/api/ingestion"))
        return json({
          ...STATUS,
          is_indexed: false,
          units: STATUS.units.map((unit) => ({ ...unit, indexed_paragraphs: null })),
        });
      return json({ is_local: false });
    });
    renderPage();

    expect(await screen.findByText(/index not built/)).toBeInTheDocument();
    expect(screen.getAllByText("not built").length).toBeGreaterThan(0);
  });

  it("is honest about an unchecked status and an empty ledger", async () => {
    stubFetch((url) => {
      if (url.includes("/api/ingestion")) return json({ ...STATUS, units: null });
      return json({ is_local: false });
    });
    const { unmount } = renderPage();
    expect(await screen.findByText(/no evidence corpus is configured/)).toBeInTheDocument();
    unmount();

    stubFetch((url) => {
      if (url.includes("/api/ingestion")) return json({ ...STATUS, units: [] });
      return json({ is_local: false });
    });
    renderPage();
    expect(await screen.findByText(/The ledger is empty/)).toBeInTheDocument();
  });

  it("offers Normalize and Rebuild index only on a local connection", async () => {
    stubFetch((url) => {
      if (url.includes("/api/ingestion")) return json(STATUS);
      return json({ is_local: false });
    });
    const { unmount } = renderPage();
    await screen.findByRole("table");
    expect(screen.queryByRole("button", { name: "Normalize" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rebuild index" })).not.toBeInTheDocument();
    unmount();

    stubFetch((url) => {
      if (url.includes("/api/ingestion")) return json(STATUS);
      return json({ is_local: true });
    });
    renderPage();
    expect(await screen.findByRole("button", { name: "Normalize" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Rebuild index" })).toBeEnabled();
  });

  it("runs a pass, shows its report, and re-reads the status", async () => {
    let reads = 0;
    const mock = stubFetch((url, init) => {
      if (url.includes("/api/ingestion/normalize") && init?.method === "POST")
        return json({
          kind: "normalize",
          summary: { converted: 3, failed: 1 },
          elapsed_seconds: 1.25,
        });
      if (url.includes("/api/ingestion")) {
        reads += 1;
        return json(STATUS);
      }
      return json({ is_local: true });
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Normalize" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Normalize: 3 converted · 1 failed · 1.3s",
    );
    await waitFor(() => expect(reads).toBeGreaterThan(1));
    expect(
      mock.mock.calls.some(
        ([input, init]) =>
          String(input).includes("/api/ingestion/normalize") &&
          (init as RequestInit | undefined)?.method === "POST",
      ),
    ).toBe(true);
  });

  it("tells a 409 apart from a failure - another pass is still running", async () => {
    stubFetch((url, init) => {
      if (url.includes("/api/ingestion/rebuild") && init?.method === "POST")
        return json({ detail: "a normalize or rebuild is already running" }, 409);
      if (url.includes("/api/ingestion")) return json(STATUS);
      return json({ is_local: true });
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Rebuild index" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Rebuild index: A run is already in progress",
    );
  });
});
