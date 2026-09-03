import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CitationPanelProvider } from "./CitationPanel";
import { SearchDialog } from "./SearchDialog";

/**
 * The dialog's no-results states (#157). An index that was never built and
 * an index that matched nothing are the same empty `results` list, and the
 * subjects group is backed by a different facet again - it is computed
 * client-side from listSubjects/listEntries and never touches /api/search.
 */

function stubFetch({
  searchIsBuilt,
  subjectsIsBuilt,
}: {
  searchIsBuilt: boolean;
  subjectsIsBuilt: boolean;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      // Ordered most-specific first: "/api/subjects" is a substring of the
      // entries path too.
      if (url.includes("/api/search")) {
        return new Response(JSON.stringify({ results: [], is_built: searchIsBuilt }), {
          status: 200,
        });
      }
      if (url.includes("/entries")) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      if (url.includes("/api/subjects")) {
        return new Response(JSON.stringify({ items: [], is_built: subjectsIsBuilt }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
}

function renderDialog() {
  const queryClient = new QueryClient();
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CitationPanelProvider>
          <SearchDialog open onClose={() => {}} />
        </CitationPanelProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  // The query is debounced 200ms, so every assertion below is a findBy*.
  fireEvent.change(screen.getByPlaceholderText(/search sources and subjects/i), {
    target: { value: "heron" },
  });
  return result;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the search dialog when a facet was never built", () => {
  it("tells the reader to run memoria rebuild when the index has never been built", async () => {
    stubFetch({ searchIsBuilt: false, subjectsIsBuilt: true });
    renderDialog();

    expect(await screen.findByText(/memoria rebuild/i)).toBeInTheDocument();
    expect(screen.queryByText(/no matching evidence/i)).not.toBeInTheDocument();
  });

  it("says nothing matched when the index is built and the query finds nothing", async () => {
    stubFetch({ searchIsBuilt: true, subjectsIsBuilt: true });
    renderDialog();

    expect(await screen.findByText(/no matching evidence/i)).toBeInTheDocument();
    expect(screen.queryByText(/memoria rebuild/i)).not.toBeInTheDocument();
  });

  it("names the subjects command in the subjects group, not the index command", async () => {
    // The cross-wiring this pins against: reading `is_built` off the search
    // response for all three groups would tell an author with a perfectly
    // good index to rebuild it because they had not seeded subjects.
    stubFetch({ searchIsBuilt: true, subjectsIsBuilt: false });
    renderDialog();

    expect(await screen.findByText(/memoria seed-subjects/i)).toBeInTheDocument();
    expect(screen.queryByText(/memoria rebuild/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no matching entries/i)).not.toBeInTheDocument();
  });
});
