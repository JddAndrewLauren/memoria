import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NewSubjectDialog } from "./NewSubjectDialog";

/** New subject (ADR-0014): the four declarations posted as one create, the
 * id derived server-side, the tree re-read on success. */
function renderDialog(onClose = vi.fn()) {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <NewSubjectDialog open onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose, invalidate };
}

describe("the New subject dialog (ADR-0014)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/subjects" && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        if (body.name === "People") {
          return new Response(
            JSON.stringify({
              detail: "SUB-people already exists (exists); nothing written",
            }),
            { status: 409 },
          );
        }
        return new Response(JSON.stringify({ id: "SUB-key-dates" }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({ items: [], is_built: true }), {
        status: 200,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("needs a name and a match before Create is enabled", () => {
    renderDialog();
    const create = screen.getByRole("button", { name: "Create" });
    expect(create).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Key dates" },
    });
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Match"), {
      target: { value: "A date." },
    });
    expect(create).toBeEnabled();
  });

  it("posts the declarations, re-reads the tree and closes", async () => {
    const { onClose, invalidate } = renderDialog();
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Key dates" },
    });
    fireEvent.change(screen.getByLabelText("Match"), {
      target: { value: "A date." },
    });
    fireEvent.change(screen.getByLabelText("Hazards"), {
      target: { value: "Two calendars." },
    });
    fireEvent.change(screen.getByLabelText("Audit questions"), {
      target: { value: "Is it dated?" },
    });
    fireEvent.click(screen.getByLabelText(/Auto-promote/));

    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls.find(
      ([url]) => String(url) === "/api/subjects",
    )!;
    expect(JSON.parse(String(init.body))).toEqual({
      name: "Key dates",
      match: "A date.",
      hazards: "Two calendars.",
      audit_questions: "Is it dated?",
      auto_promote: true,
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["subjects"] });
  });

  it("shows the server's reason when the subject already exists, and stays open", async () => {
    const { onClose } = renderDialog();
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "People" },
    });
    fireEvent.change(screen.getByLabelText("Match"), {
      target: { value: "A person." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(
      await screen.findByText(/SUB-people already exists/),
    ).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Name")).toHaveValue("People");
  });
});
