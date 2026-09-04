import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AddRawUnitsDialog } from "./AddRawUnitsDialog";
import type { PickedFile } from "../lib/rawUnits";

/**
 * Adding raw units (ADR-0013): one POST per file with its path and base64
 * bytes, a 409 read as "already in the archive", an oversize file never
 * sent, and the normalize that numbers them run after - only when the
 * browser is local, else the author is told it is still needed.
 */
function picked(path: string, size = 5): PickedFile {
  const file = new File([new Uint8Array(size).fill(104)], path.split("/").pop() ?? path);
  return { file, path };
}

type Call = { url: string; method: string; body: unknown };

const EMPTY_STATUS = {
  units: [],
  counts: {},
  unnumbered: [],
  is_normalized: false,
  is_indexed: false,
  generated_at: "2026-09-04T18:00:00+00:00",
};

function stubFetch(
  local: boolean,
  onUnit?: (body: { path: string }) => Response | undefined,
  status: Record<string, unknown> = EMPTY_STATUS,
) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, method, body });
      if (url.endsWith("/api/locality")) return new Response(JSON.stringify({ is_local: local }), { status: 200 });
      if (url.endsWith("/api/ingestion")) return new Response(JSON.stringify(status), { status: 200 });
      if (url.endsWith("/api/ingestion/units")) {
        return (
          onUnit?.(body) ??
          new Response(JSON.stringify({ path: `raw/${body.path}`, size: 5 }), { status: 200 })
        );
      }
      if (url.endsWith("/api/ingestion/normalize")) {
        return new Response(
          JSON.stringify({ kind: "normalize", summary: { added_units: 2, converted: 2 }, elapsed_seconds: 0.4 }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    }),
  );
  return calls;
}

function Harness({ initial }: { initial: PickedFile[] }) {
  const [files, setFiles] = useState(initial);
  return (
    <AddRawUnitsDialog
      open
      onClose={() => {}}
      files={files}
      onAddFiles={(more) => setFiles((current) => [...current, ...more])}
    />
  );
}

function renderDialog(initial: PickedFile[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Harness initial={initial} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("the Add sources dialog", () => {
  it("posts one unit per file with its path and bytes, then normalizes when local", async () => {
    const calls = stubFetch(true);
    renderDialog([picked("box/a.txt"), picked("b.txt")]);

    fireEvent.click(await screen.findByRole("button", { name: "Add 2 files" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Added 2. Normalize:"));
    const units = calls.filter((c) => c.url.endsWith("/api/ingestion/units"));
    expect(units.map((c) => c.body)).toEqual([
      { path: "box/a.txt", content: "aGhoaGg=" },
      { path: "b.txt", content: "aGhoaGg=" },
    ]);
    const normalize = calls.findIndex((c) => c.url.endsWith("/api/ingestion/normalize"));
    expect(normalize).toBeGreaterThan(calls.indexOf(units[1]));
    expect(screen.getByRole("status")).toHaveTextContent("2 added units · 2 converted · 0.4s");
    expect(screen.getAllByText("added")).toHaveLength(2);
  });

  it("reads a 409 as already in the archive and still normalizes the rest", async () => {
    const calls = stubFetch(true, (body) =>
      body.path === "dup.txt"
        ? new Response(JSON.stringify({ detail: "raw/dup.txt already exists" }), { status: 409 })
        : undefined,
    );
    renderDialog([picked("dup.txt"), picked("new.txt")]);

    fireEvent.click(await screen.findByRole("button", { name: "Add 2 files" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Added 1."));
    expect(screen.getByText("already in the archive")).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/api/ingestion/normalize"))).toBe(true);
  });

  it("never sends a file over the cap, and says nothing was added when none went", async () => {
    const calls = stubFetch(true);
    renderDialog([picked("huge.pdf", 64 * 1024 * 1024 + 1)]);

    expect(await screen.findByText("too large (64.0 MB limit)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add 0 files" })).toBeDisabled();
    expect(calls.some((c) => c.url.endsWith("/api/ingestion/units"))).toBe(false);
  });

  it("hosted, uploads without normalizing and names the step still needed", async () => {
    const calls = stubFetch(false);
    renderDialog([picked("a.txt")]);

    fireEvent.click(await screen.findByRole("button", { name: "Add 1 file" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Added 1. Run memoria normalize"));
    expect(calls.some((c) => c.url.endsWith("/api/ingestion/normalize"))).toBe(false);
  });

  it("marks files already in the archive before anything is sent, and offers the normalize the unnumbered ones wait for", async () => {
    const calls = stubFetch(true, undefined, {
      ...EMPTY_STATUS,
      units: [{ id: "SRC-000001", path: "raw/old.txt", deleted: false, converted: "current" }],
      unnumbered: ["raw/box/waiting.eml"],
    });
    renderDialog([picked("old.txt"), picked("box/waiting.eml"), picked("new.txt")]);

    expect(await screen.findByText("already in the archive")).toBeInTheDocument();
    expect(screen.getByText("in the archive, not numbered yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add 1 file" })).toBeEnabled();
    expect(screen.getByText(/1 file in the archive is not numbered yet/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Normalize now" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Normalize: 2 added units"));
    expect(calls.filter((c) => c.url.endsWith("/api/ingestion/units"))).toHaveLength(0);
    expect(calls.some((c) => c.url.endsWith("/api/ingestion/normalize"))).toBe(true);
  });

  it("takes files from the pickers - the folder one keeps relative paths", async () => {
    stubFetch(true);
    renderDialog([]);
    const folder = screen.getByLabelText("Choose a folder") as HTMLInputElement;
    expect(folder.hasAttribute("webkitdirectory")).toBe(true);
    const inner = new File(["x"], "n.txt");
    Object.defineProperty(inner, "webkitRelativePath", { value: "box/n.txt" });

    fireEvent.change(folder, { target: { files: [inner] } });
    fireEvent.change(screen.getByLabelText("Choose files"), { target: { files: [new File(["x"], "loose.txt")] } });

    expect(await screen.findByText("box/n.txt")).toBeInTheDocument();
    expect(screen.getByText("loose.txt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add 2 files" })).toBeEnabled();
  });
});
