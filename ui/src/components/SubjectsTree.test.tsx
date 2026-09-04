import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SubjectsTree } from "./SubjectsTree";
import { NewItemsContext } from "../lib/newItemsContext";

/**
 * The `SUBJECTS` tree's entry rows, after #26 gave entries a view of their
 * own.
 *
 * #148 made this row an expander that read the entry and drew its statements
 * and match terms inline, because there was nowhere else to see them. There
 * is now: the entry view (#26) shows the same fields and is the only place
 * that can *edit* the match terms. Two places to read one field, one place to
 * write it, is how an author comes to trust a stale copy - so the row is a
 * link, and the read it used to make is gone with it.
 */
function renderTree() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SubjectsTree />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the SUBJECTS tree's entry rows (#148, #26)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/subjects/SUB-people/entries")) {
        return new Response(
          JSON.stringify({
            items: [{ id: "SUB-people/bob", match_terms: ["Bob", "Robert"] }],
          }),
          { status: 200 },
        );
      }
      if (url.includes("/api/subjects")) {
        return new Response(
          JSON.stringify({ items: [{ id: "SUB-people", entry_count: 1 }] }),
          {
            status: 200,
          },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("links the entry to its own view rather than expanding it in the tree", async () => {
    renderTree();

    fireEvent.click(await screen.findByText("people"));

    const link = await screen.findByRole("link", { name: "bob" });
    expect(link).toHaveAttribute("href", "/subjects/SUB-people/entries/bob");
  });

  it("does not read the entry itself - the entry view owns that read", async () => {
    renderTree();

    fireEvent.click(await screen.findByText("people"));
    fireEvent.click(await screen.findByRole("link", { name: "bob" }));

    const read = fetchMock.mock.calls.some(([input]) =>
      String(input).includes("/entries/bob"),
    );
    expect(read).toBe(false);
  });
});

describe("the SUBJECTS tree's create row (ADR-0014)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the New subject dialog through the app's context", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ items: [], is_built: false }), {
            status: 200,
          }),
      ),
    );
    const openNewSubject = vi.fn();
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <NewItemsContext.Provider
            value={{ openNewSection: vi.fn(), openNewSubject }}
          >
            <SubjectsTree />
          </NewItemsContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "+ New subject…" }));
    expect(openNewSubject).toHaveBeenCalled();
    // The empty state names the button before the CLI.
    expect(await screen.findByText(/Add one above/)).toBeInTheDocument();
  });
});
