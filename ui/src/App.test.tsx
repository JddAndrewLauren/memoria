import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import Home from "./routes/Home";

function stubFetch(isBuilt: boolean) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/sources")) {
        return new Response(
          JSON.stringify({
            items: [],
            total: 0,
            limit: 10000,
            offset: 0,
            is_built: isBuilt,
          }),
          { status: 200 },
        );
      }
      if (url.includes("/api/subjects")) {
        return new Response(JSON.stringify({ items: [], is_built: isBuilt }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
}

function renderApp() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<Home />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the app shell on a fresh checkout", () => {
  beforeEach(() => {
    stubFetch(false);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders all three trees, and an honest empty state rather than an error", async () => {
    renderApp();

    // #24's acceptance criteria: an un-normalized/un-seeded checkout renders
    // an honest empty state, not an error and not a bare zero.
    expect(await screen.findByText(/no sources yet/i)).toBeInTheDocument();
    expect(await screen.findByText(/no subjects yet/i)).toBeInTheDocument();
    // MANUSCRIPT is present and labelled, not hidden, even though it is
    // always empty at M3.
    expect(screen.getByText(/empty until m5/i)).toBeInTheDocument();
    expect(screen.getByText("Manuscript")).toBeInTheDocument();
    expect(screen.getByText("Subjects")).toBeInTheDocument();
    expect(screen.getByText("Sources")).toBeInTheDocument();
  });
});

describe("the app shell on a built but empty corpus", () => {
  beforeEach(() => {
    stubFetch(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("says the corpus is empty rather than naming a command already run (#157)", async () => {
    renderApp();

    // The same empty lists as the fresh-checkout case above. Only `is_built`
    // separates them, which is the whole point: telling an author to run
    // `memoria normalize` when they already have is the lie #157 removes.
    expect(await screen.findByText(/produced no records/i)).toBeInTheDocument();
    expect(await screen.findByText(/holds no subject prompts/i)).toBeInTheDocument();
    expect(screen.queryByText(/against an evidence root/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/run .*seed-subjects/i)).not.toBeInTheDocument();
  });
});
