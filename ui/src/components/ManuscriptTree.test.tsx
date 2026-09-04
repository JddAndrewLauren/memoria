import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ManuscriptTree } from "./ManuscriptTree";
import { NewItemsContext } from "../lib/newItemsContext";

describe("the MANUSCRIPT tree's create row (ADR-0014)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the New section dialog through the app's context", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ chapters: [], is_built: true }), {
            status: 200,
          }),
      ),
    );
    const openNewSection = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <NewItemsContext.Provider
            value={{ openNewSection, openNewSubject: vi.fn() }}
          >
            <ManuscriptTree />
          </NewItemsContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "+ New section…" }));
    expect(openNewSection).toHaveBeenCalled();
    expect(await screen.findByText(/No chapters yet/)).toBeInTheDocument();
  });
});
