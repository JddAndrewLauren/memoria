import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  // retry: false - a stubbed 404 should surface as isError on the first
  // attempt, not after react-query's default retry/backoff outlasts
  // findByText's timeout.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

  it("KNOWN LIMITATION: drops apparatus whose linked_anchor names no paragraph in the record", async () => {
    // Pinned, not endorsed. groupApparatusByAnchor buckets apparatus by
    // `linked_anchor` and the render only reads the buckets belonging to
    // paragraphs that exist, so an orphaned note vanishes silently. Whether
    // such a note should instead surface somewhere is a design decision this
    // test does not make - it only makes the current behaviour visible.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            ...SOURCE_DETAIL,
            apparatus: [
              ...SOURCE_DETAIL.apparatus,
              {
                editorial_type: "headnote",
                retrospective: false,
                linked_record_id: "SRC-000184",
                linked_anchor: "src-000184-p9",
                text: "Orphaned: no paragraph carries this anchor.",
              },
            ],
          }),
          { status: 200 },
        ),
      ),
    );

    renderAt("/sources/SRC-000184");

    // The anchored note still renders...
    expect(await screen.findByText("Added by the editor in 2019.")).toBeInTheDocument();
    // ...and the orphan is dropped without a trace.
    expect(
      screen.queryByText("Orphaned: no paragraph carries this anchor."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("headnote")).not.toBeInTheDocument();
  });

  it("shows a distinct failure line, not silence, when the cited paragraph's backlinks can't be read", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/read")) {
          return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
        }
        if (url.includes("/api/sources/SRC-000184")) {
          return new Response(JSON.stringify(SOURCE_DETAIL), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }),
    );

    renderAt("/sources/SRC-000184#src-000184-p2");

    expect(await screen.findByText("This reference could not be read.")).toBeInTheDocument();
    // Not indistinguishable from "this paragraph has no backlinks": that
    // renders "Cited by" plus "Nothing links this paragraph yet.", neither
    // of which should appear on an actual read failure.
    expect(screen.queryByText("Cited by")).not.toBeInTheDocument();
  });

  it("gives all five date_confidence values distinguishable tones, not just different text", async () => {
    // The tone, not the word, is what a reader sees first: every one of the
    // five values must reach the badge as its own color. Asserted by class,
    // because asserting the text would still pass with every tone collapsed
    // into one.
    const cases: Array<[confidence: string, expectedClass: string]> = [
      ["exact", "text-sources"],
      ["inferred", "text-amber"],
      ["published", "text-subjects"],
      ["chapter-only", "text-secondary"],
      ["unresolved", "text-manuscript"],
    ];

    for (const [confidence, expectedClass] of cases) {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
          new Response(
            JSON.stringify({ ...SOURCE_DETAIL, date_confidence: confidence, apparatus: [] }),
            { status: 200 },
          ),
        ),
      );

      const { unmount } = renderAt("/sources/SRC-000184");
      const badge = await screen.findByText(new RegExp(confidence));
      expect(badge.closest("span")).toHaveClass(expectedClass);
      unmount();
      vi.unstubAllGlobals();
    }
  });

  it("gives chapter-only and unresolved different tones despite both lacking a resolved date_confidence badge color", async () => {
    // chapter-only's own no-date badge is covered by the "renders an honest
    // absence" test below; this is the same record shape but with a date
    // present and date_confidence: unresolved - the case the review found
    // collapsed into an identical neutral badge as chapter-only.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ ...SOURCE_DETAIL, date_confidence: "unresolved", apparatus: [] }),
          { status: 200 },
        ),
      ),
    );

    renderAt("/sources/SRC-000184");

    const badge = await screen.findByText(/unresolved/);
    expect(badge.closest("span")).toHaveClass("text-manuscript");
    expect(badge.closest("span")).not.toHaveClass("text-secondary");
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

describe('"Reveal in editor" (#65)', () => {
  function stubFetch(isLocal: boolean, onReveal?: (url: string) => void) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/locality")) {
          return new Response(JSON.stringify({ is_local: isLocal }), { status: 200 });
        }
        if (url.includes("/reveal") && init?.method === "POST") {
          onReveal?.(url);
          return new Response(JSON.stringify({ opened: true }), { status: 200 });
        }
        if (url.includes("/api/sources/SRC-000184")) {
          return new Response(JSON.stringify(SOURCE_DETAIL), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }),
    );
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is absent - not disabled, not erroring - when the client is not local", async () => {
    stubFetch(false);

    renderAt("/sources/SRC-000184");

    await screen.findByText("SRC-000184");
    expect(screen.queryByText("Reveal in editor")).not.toBeInTheDocument();
  });

  it("appears beside Open original, and asks the server to reveal the file, when the client is local", async () => {
    const onReveal = vi.fn();
    stubFetch(true, onReveal);

    renderAt("/sources/SRC-000184");

    expect(await screen.findByText(/Open original/)).toBeInTheDocument();
    const button = screen.getByText("Reveal in editor");

    fireEvent.click(button);

    await waitFor(() =>
      expect(onReveal).toHaveBeenCalledWith(
        expect.stringContaining("/api/sources/SRC-000184/reveal"),
      ),
    );
  });

  it("shows a distinct failure line, not silence, when the server refuses the reveal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/locality")) {
          return new Response(JSON.stringify({ is_local: true }), { status: 200 });
        }
        if (url.includes("/reveal") && init?.method === "POST") {
          return new Response(JSON.stringify({ detail: "local-only" }), { status: 403 });
        }
        if (url.includes("/api/sources/SRC-000184")) {
          return new Response(JSON.stringify(SOURCE_DETAIL), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }),
    );

    renderAt("/sources/SRC-000184");

    fireEvent.click(await screen.findByText("Reveal in editor"));

    expect(await screen.findByText("Could not reveal the original file.")).toBeInTheDocument();
  });
});
