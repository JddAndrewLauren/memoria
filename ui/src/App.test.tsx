import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
      if (url.includes("/api/manuscript")) {
        return new Response(JSON.stringify({ chapters: [], is_built: isBuilt }), {
          status: 200,
        });
      }
      if (url.includes("/api/style")) {
        return new Response(
          JSON.stringify({
            exists: false,
            direction: "",
            observations: [],
            sample_sources: [],
            samples: [],
            token: null,
            pending: [],
            confirmed_count: 0,
            discarded_count: 0,
          }),
          { status: 200 },
        );
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
    // MANUSCRIPT is present and labelled, not hidden - and honest about a
    // repository with no chapters/ directory (#43).
    expect(await screen.findByText(/no manuscript yet/i)).toBeInTheDocument();
    expect(screen.getByText("Manuscript")).toBeInTheDocument();
    expect(screen.getByText("Subjects")).toBeInTheDocument();
    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  it("opens Settings from the footer gear, on the writing style (ADR-0009)", async () => {
    renderApp();
    expect(screen.queryByRole("dialog", { name: "Settings" })).not.toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "Settings" }));

    const dialog = await screen.findByRole("dialog", { name: "Settings" });
    expect(
      await within(dialog).findByRole("heading", { name: "Writing style" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Direction")).toHaveValue("");
    // No style yet is an honest empty state, not an error.
    expect(within(dialog).getByText("No confirmed observations yet.")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Close settings" }));
    expect(screen.queryByRole("dialog", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("carries the floating New section button, which opens its dialog (ADR-0011)", async () => {
    renderApp();
    expect(screen.queryByRole("dialog", { name: "New section" })).not.toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "New section" }));

    const dialog = await screen.findByRole("dialog", { name: "New section" });
    expect(within(dialog).getByRole("tab", { name: "Write now" })).toBeInTheDocument();
    expect(within(dialog).getByRole("tab", { name: "Grill me" })).toBeInTheDocument();
    // A repository with no manuscript is an honest empty state here too.
    expect(await within(dialog).findByText(/No manuscript yet/)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Close new section" }));
    expect(screen.queryByRole("dialog", { name: "New section" })).not.toBeInTheDocument();
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
