import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SubjectsTree } from "./SubjectsTree";

function renderTree() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <SubjectsTree />
    </QueryClientProvider>,
  );
}

describe("the SUBJECTS tree's own entry read (#148)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/entries/bob")) {
          return new Response(
            JSON.stringify({
              id: "SUB-people/bob",
              match_terms: ["Bob", "Robert"],
              statements: [
                { badge: null, text: "Bob kept a journal." },
                { badge: "inferred", text: "Bob likely wrote most nights." },
              ],
            }),
            { status: 200 },
          );
        }
        if (url.includes("/api/subjects/SUB-people/entries")) {
          return new Response(
            JSON.stringify({ items: [{ id: "SUB-people/bob", match_terms: ["Bob", "Robert"] }] }),
            { status: 200 },
          );
        }
        if (url.includes("/api/subjects")) {
          return new Response(
            JSON.stringify({ items: [{ id: "SUB-people", entry_count: 1 }] }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads the entry's statements when expanded - not just its match terms", async () => {
    renderTree();

    fireEvent.click(await screen.findByText("people"));
    fireEvent.click(await screen.findByText("bob"));

    expect(await screen.findByText("Bob kept a journal.")).toBeInTheDocument();
    expect(screen.getByText(/Bob likely wrote most nights\./)).toBeInTheDocument();
    expect(screen.getByText(/inferred/i)).toBeInTheDocument();
    expect(screen.getByText(/Match terms: Bob, Robert/)).toBeInTheDocument();
  });
});
