import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";
import EntryPage from "./EntryPage";
import SourceDetailPage from "./SourceDetailPage";

const ENTRY = {
  id: "SUB-people/bob",
  match_terms: ["Bob", "Robert"],
  statements: [
    { badge: null, text: "Bob was born in 1962 in Cleveland." },
    { badge: "source", text: "Bob called on July 17." },
    { badge: "open", text: "Did Bob receive the July 14 document?" },
  ],
  overlay: [],
  token: "token-one",
};

const GATHERED = {
  items: [
    { src_id: "SRC-000184", anchor: "src-000184-p17", pinned: false, overlay_action: null, actor_name: null, at: null },
    {
      src_id: "SRC-000185",
      anchor: "src-000185-p2",
      pinned: true,
      overlay_action: "pin",
      actor_name: "A Person",
      at: "2026-09-02T00:00:00Z",
    },
  ],
  excluded: [],
  is_built: true,
};

const APPEARANCES = {
  items: [{ src_id: "SRC-000900", anchor: "src-000900-p4", note: 'matched "Bob"' }],
  is_built: true,
  engine_supported: true,
};

const CITATION = {
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

const SOURCE = {
  ...CITATION.record,
  paragraphs: [
    { anchor: "src-000184-p16", text: "The morning was clear." },
    { anchor: "src-000184-p17", text: "I called Bob that evening." },
  ],
  apparatus: [],
};

type Overrides = {
  entry?: Record<string, unknown>;
  gathered?: Record<string, unknown>;
  appearances?: Record<string, unknown>;
  onPut?: (body: unknown) => Response;
};

function stubApi(overrides: Overrides = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "PUT" && url.includes("/match-terms")) {
        const handler =
          overrides.onPut ??
          (() =>
            new Response(
              JSON.stringify({ match_terms: ["Bob", "Bobby"], token: "token-two" }),
              { status: 200 },
            ));
        return handler(JSON.parse(String(init.body)));
      }
      if (url.includes("/gathered")) {
        return new Response(JSON.stringify({ ...GATHERED, ...overrides.gathered }), {
          status: 200,
        });
      }
      if (url.includes("/appearances")) {
        return new Response(JSON.stringify({ ...APPEARANCES, ...overrides.appearances }), {
          status: 200,
        });
      }
      if (url.includes("/api/subjects/SUB-people/entries/bob")) {
        return new Response(JSON.stringify({ ...ENTRY, ...overrides.entry }), { status: 200 });
      }
      if (url.includes("/api/subjects/SUB-themes/entries/control")) {
        return new Response(
          JSON.stringify({ id: "SUB-themes/control", match_terms: [], statements: [], overlay: [], token: "t" }),
          { status: 200 },
        );
      }
      if (url.includes("ref=src-000184-p17")) {
        return new Response(JSON.stringify(CITATION), { status: 200 });
      }
      if (url.includes("/api/sources/SRC-000184")) {
        return new Response(JSON.stringify(SOURCE), { status: 200 });
      }
      if (url.includes("/api/subjects")) {
        return new Response(JSON.stringify({ items: [], is_built: true }), { status: 200 });
      }
      if (url.includes("/api/sources")) {
        return new Response(
          JSON.stringify({ items: [], total: 0, limit: 10, offset: 0, is_built: true }),
          { status: 200 },
        );
      }
      if (url.includes("/api/locality")) {
        return new Response(JSON.stringify({ is_local: false }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    }),
  );
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}

function renderAt(path: string) {
  // `retry: false` so a 404 or a 409 surfaces immediately rather than after
  // react-query's default retries.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path="/" element={<App />}>
            <Route path="subjects/:subjectId/entries/:entrySlug" element={<EntryPage />} />
            <Route path="sources/:id" element={<SourceDetailPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const BOB = "/subjects/SUB-people/entries/bob";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the entry view's body (part 06 §8.2)", () => {
  beforeEach(() => stubApi());

  it("renders the audit-visible body with badges, and names testimony as the author's", async () => {
    renderAt(BOB);

    expect(await screen.findByText("Bob was born in 1962 in Cleveland.")).toBeInTheDocument();
    expect(screen.getByText("Bob called on July 17.")).toBeInTheDocument();
    // The absence of a badge *is* the attribution (§9.5) - so it is said,
    // and it carries the author's own colour.
    const testimony = screen.getByText("testimony · author");
    expect(testimony).toHaveClass("text-subjects");
    expect(screen.getByText("source")).toHaveClass("text-sources");
  });

  it("renders an [open] line outside the audit-visible body, and says why", async () => {
    renderAt(BOB);

    const outside = await screen.findByRole("heading", {
      name: /outside the audit-visible body/i,
    });
    const region = outside.closest("section");
    expect(region).not.toBeNull();
    expect(region?.textContent).toContain("Did Bob receive the July 14 document?");
    expect(region?.textContent).toMatch(/assembly never loads these/i);
    expect(region?.textContent).toMatch(/audit never evaluates against them/i);

    // And it is *not* in the audit-visible body's own region.
    const body = screen
      .getByRole("heading", { name: /^audit-visible body$/i })
      .closest("section");
    expect(body?.textContent).not.toContain("Did Bob receive the July 14 document?");
  });

  it("draws every not-yet-built region, naming the milestone that fills it", async () => {
    renderAt(BOB);

    await screen.findByText("Bob was born in 1962 in Cleveland.");
    // Present, not hidden - a reviewer walking the gate must be able to see
    // what is not built yet (#26).
    expect(screen.getByRole("heading", { name: /^settlements$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^memoria notes$/i })).toBeInTheDocument();
    expect(screen.getByText(/settlements .* arrive at M4 \(#33\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Memoria notes .* arrive at M4 \(#32\)/i)).toBeInTheDocument();
    // Settlements are part *of* the audit-visible body (part 06 §8.2), so
    // they are nested inside it rather than made a sibling region.
    const body = screen
      .getByRole("heading", { name: /^audit-visible body$/i })
      .closest("section");
    expect(body?.textContent).toMatch(/settlements .* arrive at M4 \(#33\)/i);
  });

  it("says the body is unwritten rather than stubbing a statement into it", async () => {
    stubApi({ entry: { statements: [] } });
    renderAt(BOB);

    expect(await screen.findByText(/no statements yet/i)).toBeInTheDocument();
    expect(screen.getByText(/record extractor/i).textContent).toMatch(/#31/);
    // No fabricated badge stands in for the absent statements.
    expect(screen.queryByText("testimony · author")).not.toBeInTheDocument();
  });
});

describe("the gathered set and appearances (part 06 §8.3, §8.11)", () => {
  beforeEach(() => stubApi());

  it("marks a pinned source and attributes the act", async () => {
    renderAt(BOB);

    expect(await screen.findByRole("button", { name: "src-000185-p2" })).toBeInTheDocument();
    expect(screen.getByText("pinned")).toBeInTheDocument();
    expect(screen.getByText(/by A Person/)).toBeInTheDocument();
  });

  it("renders an exclusion, so an author act is never an unexplained absence", async () => {
    stubApi({
      gathered: {
        items: [],
        excluded: [
          {
            anchor: "src-000184-p17",
            action: "exclude",
            actor_name: "A Person",
            at: "2026-09-02T00:00:00Z",
          },
        ],
      },
    });
    renderAt(BOB);

    expect(await screen.findByText(/excluded from this set/i)).toBeInTheDocument();
    expect(screen.getByText(/by A Person/)).toBeInTheDocument();
  });

  it("keeps appearances in their own region, labelled as prose already written", async () => {
    renderAt(BOB);

    const appearances = (
      await screen.findByRole("heading", { name: /^appearances$/i })
    ).closest("section");
    expect(appearances?.textContent).toContain("src-000900-p4");
    expect(appearances?.textContent).toMatch(/prose already written/i);
    expect(appearances?.textContent).toMatch(/never merged into the gathered set/i);

    const gathered = screen
      .getByRole("heading", { name: /^gathered set$/i })
      .closest("section");
    expect(gathered?.textContent).not.toContain("src-000900-p4");
    expect(appearances?.textContent).not.toContain("src-000184-p17");
  });

  it("a theme says its engine does not exist yet rather than showing an empty list", async () => {
    stubApi({ appearances: { items: [], engine_supported: false } });
    renderAt("/subjects/SUB-themes/entries/control");

    expect(
      await screen.findByText(/no appearances yet — the model engine arrives with the audit/i),
    ).toBeInTheDocument();
  });

  it("an empty gathered set on a built index is a valid state, not an error", async () => {
    stubApi({ gathered: { items: [], excluded: [], is_built: true } });
    renderAt(BOB);

    expect(await screen.findByText(/nothing gathered.*valid state/i)).toBeInTheDocument();
  });

  it("an unbuilt index names the command instead of claiming nothing matched", async () => {
    stubApi({ gathered: { items: [], excluded: [], is_built: false } });
    renderAt(BOB);

    expect(await screen.findByText(/no index yet — run memoria rebuild/i)).toBeInTheDocument();
  });
});

describe("the M3 gate: citation → slide-over → exact paragraph → raw original", () => {
  beforeEach(() => stubApi());

  it("opens the slide-over on the cited paragraph without costing the reader their place", async () => {
    renderAt(BOB);

    const chip = await screen.findByRole("button", { name: "src-000184-p17" });
    fireEvent.click(chip);

    // The exact evidence paragraph, in the panel.
    expect(await screen.findByText("I called Bob that evening.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Citation" })).toBeInTheDocument();
    // The place is kept: the panel is a sibling overlay, not a route, so
    // the entry is still the page underneath and still rendered.
    expect(screen.getByTestId("path")).toHaveTextContent(BOB);
    expect(screen.getByText("Bob was born in 1962 in Cleveland.")).toBeInTheDocument();
  });

  it("offers the raw original from inside the panel, in its own tab", async () => {
    renderAt(BOB);

    fireEvent.click(await screen.findByRole("button", { name: "src-000184-p17" }));
    const original = await screen.findByRole("link", { name: /open original/i });

    expect(original).toHaveAttribute("href", "/sources/SRC-000184/raw");
    // Its own tab, so the reading surface is never navigated away from.
    expect(original).toHaveAttribute("target", "_blank");
    expect(screen.getByTestId("path")).toHaveTextContent(BOB);
  });

  it("closing the panel leaves the entry exactly where it was", async () => {
    renderAt(BOB);

    fireEvent.click(await screen.findByRole("button", { name: "src-000184-p17" }));
    await screen.findByRole("dialog", { name: "Citation" });
    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Citation" })).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("path")).toHaveTextContent(BOB);
    expect(screen.getByText("Bob was born in 1962 in Cleveland.")).toBeInTheDocument();
  });
});

describe("editing match terms - the first durable write (ADR-0003)", () => {
  it("saves the edited terms, presenting the token the entry was served with", async () => {
    const seen: unknown[] = [];
    stubApi({
      onPut: (body) => {
        seen.push(body);
        return new Response(
          JSON.stringify({ match_terms: ["Bob", "Bobby"], token: "token-two" }),
          { status: 200 },
        );
      },
    });
    renderAt(BOB);

    await screen.findByText("Bob was born in 1962 in Cleveland.");
    fireEvent.click(screen.getByRole("button", { name: "Remove Robert" }));
    fireEvent.change(screen.getByLabelText("New match term"), {
      target: { value: "Bobby" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toEqual({ token: "token-one", match_terms: ["Bob", "Bobby"] });
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("a stale write is refused whole, and the author's edits survive the refusal", async () => {
    stubApi({
      onPut: () =>
        new Response(
          JSON.stringify({ detail: "subjects/people/bob.md changed since it was read" }),
          { status: 409 },
        ),
    });
    renderAt(BOB);

    await screen.findByText("Bob was born in 1962 in Cleveland.");
    fireEvent.change(screen.getByLabelText("New match term"), { target: { value: "Bobby" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(/this entry changed on disk since it was opened/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/nothing was written/i)).toBeInTheDocument();
    // Never merged, never silently retried: the edit is still in the editor.
    expect(screen.getByText("Bobby")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload the entry/i })).toBeInTheDocument();
    expect(screen.queryByText("Saved.")).not.toBeInTheDocument();
  });

  it("tells an ordinary failure apart from a staleness rejection", async () => {
    stubApi({
      onPut: () =>
        new Response(JSON.stringify({ detail: "no author identity" }), { status: 500 }),
    });
    renderAt(BOB);

    await screen.findByText("Bob was born in 1962 in Cleveland.");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("no author identity")).toBeInTheDocument();
    expect(
      screen.queryByText(/this entry changed on disk since it was opened/i),
    ).not.toBeInTheDocument();
  });

  it("is the only control on this surface that writes", async () => {
    // Pins and exclusions are author acts with their own attribution and
    // belong to #18: rendered here, never authored here.
    stubApi();
    renderAt(BOB);

    await screen.findByText("Bob was born in 1962 in Cleveland.");
    expect(screen.queryByRole("button", { name: /^pin$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^exclude$/i })).not.toBeInTheDocument();
  });
});

describe("the staleness token across a save (ADR-0003)", () => {
  it("a second save presents the token the first one returned, not the one it consumed", async () => {
    const seen: unknown[] = [];
    let nextToken = 1;
    stubApi({
      onPut: (body) => {
        seen.push(body);
        nextToken += 1;
        return new Response(
          JSON.stringify({ match_terms: ["Bob"], token: `token-${nextToken}` }),
          { status: 200 },
        );
      },
    });
    renderAt(BOB);

    await screen.findByText("Bob was born in 1962 in Cleveland.");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(seen).toHaveLength(1));

    fireEvent.change(screen.getByLabelText("New match term"), { target: { value: "R." } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(seen).toHaveLength(2));
    // The first write invalidated `token-one` by making it; presenting it
    // again would be rejected as stale against a change only this editor
    // made.
    expect(seen[0]).toEqual({ token: "token-one", match_terms: ["Bob", "Robert"] });
    expect(seen[1]).toEqual({ token: "token-2", match_terms: ["Bob", "R."] });
  });
});
