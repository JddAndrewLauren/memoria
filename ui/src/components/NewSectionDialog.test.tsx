import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NewSectionDialog } from "./NewSectionDialog";
import type { GrillOut, ModelSettingsOut } from "../api/client";

const MANUSCRIPT = {
  is_built: true,
  chapters: [
    {
      id: "CHP-0001",
      number: 1,
      excerpt: "The summer the deck went up.",
      sections: [{ id: "SEC-0001", number: 1, excerpt: "How it started.", has_draft: true }],
    },
    {
      id: "CHP-0008",
      number: 8,
      excerpt: "What Bob knew.",
      sections: [
        { id: "SEC-0003", number: 3, excerpt: "The first point.", has_draft: true },
        { id: "SEC-0004", number: 4, excerpt: "Planned.", has_draft: false },
      ],
    },
  ],
};

const SECTION = {
  id: "SEC-0003",
  chapter_id: "CHP-0008",
  chapter_number: 8,
  section_number: 3,
  brief: "The first point.",
  unconfirmed: false,
  has_draft: true,
  paragraphs: [],
  scope: [],
  scope_empty: true,
  sessions: [],
  decisions: [],
  questions: [],
};

const SOURCE = {
  id: "SRC-000184",
  source_type: "journal",
  recorded_date: "Oct. 22.",
  event_date: "Oct. 22.",
  date_confidence: "exact",
  contemporaneous: true,
  original_file: "raw/vol-01/text.txt",
  original_locator: "Journal I",
  paragraphs: [{ anchor: "src-000184-p1", text: "The deck went up unchanged." }],
  apparatus: [],
};

const OFF: ModelSettingsOut = {
  enabled: false,
  provider: "anthropic",
  model: "claude-opus-5",
  api_key_set: false,
  api_key_source: null,
  ready: false,
  reason: "direct runs are off",
};
const READY: ModelSettingsOut = {
  ...OFF,
  enabled: true,
  api_key_set: true,
  api_key_source: "settings",
  ready: true,
  reason: null,
};

function question(text: string, recommended: string): GrillOut {
  return {
    done: false,
    question: text,
    recommended_answer: recommended,
    brief: "",
    draft: "",
    rejected: [],
    spend: { calls: 1, model: "claude-opus-5" },
  };
}

const DRAFTED: GrillOut = {
  done: true,
  question: "",
  recommended_answer: "",
  brief: "The evening the street saw the deck.",
  draft: "The deck went up unchanged.\n\nBy evening the whole street had seen it.",
  rejected: [],
  spend: { calls: 1, model: "claude-opus-5" },
};

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function stubFetch({
  model = OFF,
  manuscript = MANUSCRIPT,
  grillReplies = [] as GrillOut[],
} = {}) {
  const calls: Call[] = [];
  const replies = [...grillReplies];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, method, body });
      const json = (value: unknown, status = 200) =>
        new Response(JSON.stringify(value), { status });
      if (url.endsWith("/sections") && method === "POST") {
        return json({
          id: "SEC-0009",
          chapter_id: "CHP-0008",
          chapter_number: 8,
          section_number: 5,
          unconfirmed: body.brief === "",
        });
      }
      if (url.endsWith("/api/grill") && method === "POST") {
        const reply = replies.shift();
        return reply ? json(reply) : json({ detail: "no scripted reply" }, 500);
      }
      if (url.includes("/api/manuscript")) return json(manuscript);
      if (url.includes("/api/sections/SEC-0003")) return json(SECTION);
      if (url.includes("/api/sources/SRC-000184")) return json(SOURCE);
      if (url.includes("/api/model")) return json(model);
      return json({ detail: `unexpected ${method} ${url}` }, 404);
    }),
  );
  return calls;
}

function SectionSentinel() {
  const { sectionId } = useParams();
  return <p>section page {sectionId}</p>;
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<p>home</p>} />
          <Route path="/sections/:sectionId" element={<SectionSentinel />} />
          <Route path="/sources/:id" element={<p>source page</p>} />
          <Route path="*" element={<p>navigated away</p>} />
        </Routes>
        <NewSectionDialog open onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onClose };
}

async function dialog() {
  return screen.findByRole("dialog", { name: "New section" });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("where the section goes", () => {
  it("defaults to the first chapter from the home page, appended", async () => {
    stubFetch();
    renderAt("/");

    const picker = (await screen.findByLabelText("Chapter")) as HTMLSelectElement;
    await waitFor(() => expect(picker.value).toBe("CHP-0001"));
    expect(screen.getByText("Appended as section 1.2")).toBeInTheDocument();
    expect(screen.queryByText(/context/i)).not.toBeInTheDocument();
  });

  it("assumes the chapter of the section the author is reading", async () => {
    stubFetch();
    renderAt("/sections/SEC-0003");

    const picker = (await screen.findByLabelText("Chapter")) as HTMLSelectElement;
    await waitFor(() => expect(picker.value).toBe("CHP-0008"));
    expect(screen.getByText("Appended as section 8.5")).toBeInTheDocument();
  });

  it("lets the author pick another chapter", async () => {
    stubFetch();
    renderAt("/sections/SEC-0003");
    const picker = (await screen.findByLabelText("Chapter")) as HTMLSelectElement;
    await waitFor(() => expect(picker.value).toBe("CHP-0008"));

    fireEvent.change(picker, { target: { value: "CHP-0001" } });

    expect(picker.value).toBe("CHP-0001");
    expect(screen.getByText("Appended as section 1.2")).toBeInTheDocument();
  });

  it("is honest about a manuscript with no chapters, and cannot write", async () => {
    stubFetch({ manuscript: { is_built: true, chapters: [] } });
    renderAt("/");

    expect(await screen.findByText(/No chapters yet/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Chapter")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Prose"), { target: { value: "Some prose." } });
    expect(screen.getByRole("button", { name: "Write" })).toBeDisabled();
  });
});

describe("Write now", () => {
  it("writes the brief and the prose to the chosen chapter, then opens the new section", async () => {
    const calls = stubFetch();
    const { onClose } = renderAt("/sections/SEC-0003");
    const picker = (await screen.findByLabelText("Chapter")) as HTMLSelectElement;
    await waitFor(() => expect(picker.value).toBe("CHP-0008"));

    fireEvent.change(screen.getByLabelText("Brief"), {
      target: { value: "The evening the street saw it." },
    });
    fireEvent.change(screen.getByLabelText("Prose"), {
      target: { value: "The deck went up unchanged.\n\nBy evening the street had seen it." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Write" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const write = calls.find((call) => call.method === "POST");
    expect(write?.url).toBe("/api/chapters/CHP-0008/sections");
    expect(write?.body).toEqual({
      brief: "The evening the street saw it.",
      draft: "The deck went up unchanged.\n\nBy evening the street had seen it.",
    });
    expect(await screen.findByText("section page SEC-0009")).toBeInTheDocument();
    // The outline is re-read so the tree shows the new section.
    expect(calls.filter((call) => call.url.includes("/api/manuscript")).length).toBeGreaterThan(1);
  });

  it("writes prose alone with an empty brief, which the server marks unconfirmed", async () => {
    const calls = stubFetch();
    renderAt("/");
    await waitFor(() =>
      expect((screen.getByLabelText("Chapter") as HTMLSelectElement).value).toBe("CHP-0001"),
    );

    fireEvent.change(screen.getByLabelText("Prose"), { target: { value: "Just prose." } });
    fireEvent.click(screen.getByRole("button", { name: "Write" }));

    await waitFor(() => expect(calls.some((call) => call.method === "POST")).toBe(true));
    const write = calls.find((call) => call.method === "POST");
    expect(write?.url).toBe("/api/chapters/CHP-0001/sections");
    expect(write?.body).toEqual({ brief: "", draft: "Just prose." });
  });

  it("will not write empty prose", async () => {
    stubFetch();
    renderAt("/");
    await screen.findByLabelText("Chapter");
    expect(screen.getByRole("button", { name: "Write" })).toBeDisabled();
  });

  it("keeps the author's text on screen when the write fails", async () => {
    stubFetch();
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          return new Response(JSON.stringify({ detail: "no author identity: set user.name" }), {
            status: 500,
          });
        }
        if (url.includes("/api/manuscript")) {
          return new Response(JSON.stringify(MANUSCRIPT), { status: 200 });
        }
        return new Response(JSON.stringify(OFF), { status: 200 });
      },
    );
    renderAt("/");
    await screen.findByLabelText("Chapter");

    fireEvent.change(screen.getByLabelText("Prose"), { target: { value: "Kept." } });
    fireEvent.click(screen.getByRole("button", { name: "Write" }));

    expect(await screen.findByText(/no author identity/)).toBeInTheDocument();
    expect(screen.getByLabelText("Prose")).toHaveValue("Kept.");
    expect(screen.queryByText("navigated away")).not.toBeInTheDocument();
  });
});

describe("a source in context", () => {
  it("shows the source as a chip, starts the brief by naming it, and can be removed", async () => {
    stubFetch();
    renderAt("/sources/SRC-000184");
    const box = await dialog();

    expect(await within(box).findByText("Journal I")).toBeInTheDocument();
    expect(within(box).getByText("SRC-000184")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("Brief")).toHaveValue("From SRC-000184 (Journal I)."),
    );

    fireEvent.click(
      within(box).getByRole("button", { name: "Remove SRC-000184 from the context" }),
    );
    expect(within(box).getByText("Not included.")).toBeInTheDocument();
  });

  it("does not overwrite a brief the author already wrote", async () => {
    stubFetch();
    renderAt("/sources/SRC-000184");
    await dialog();
    fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "Mine." } });
    await screen.findByText("Journal I");
    expect(screen.getByLabelText("Brief")).toHaveValue("Mine.");
  });
});

describe("Grill me", () => {
  it("says how to run the interview from a session while direct runs are off", async () => {
    stubFetch({ model: OFF });
    renderAt("/sources/SRC-000184");
    await dialog();

    fireEvent.click(screen.getByRole("tab", { name: "Grill me" }));

    expect(await screen.findByText("/grill-writing CHP-0001 SRC-000184")).toBeInTheDocument();
    expect(screen.getByText(/Settings > Model/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start the interview" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Answer")).not.toBeInTheDocument();
  });

  it("names the paragraph anchor in the command when the source was reached by citation", async () => {
    stubFetch({ model: OFF });
    renderAt("/sources/SRC-000184#src-000184-p17");
    await dialog();
    fireEvent.click(screen.getByRole("tab", { name: "Grill me" }));
    expect(
      await screen.findByText("/grill-writing CHP-0001 src-000184-p17"),
    ).toBeInTheDocument();
  });

  it("runs nothing until the author starts it, then carries the whole transcript each turn", async () => {
    const calls = stubFetch({
      model: READY,
      grillReplies: [
        question("What does the reader know by the end?", "That the deck stayed."),
        question("Where does it open?", "On the street at dusk."),
      ],
    });
    renderAt("/sources/SRC-000184");
    await dialog();
    fireEvent.click(screen.getByRole("tab", { name: "Grill me" }));

    const start = await screen.findByRole("button", { name: "Start the interview" });
    expect(calls.filter((call) => call.url.endsWith("/api/grill"))).toHaveLength(0);
    fireEvent.click(start);

    expect(await screen.findByText("What does the reader know by the end?")).toBeInTheDocument();
    expect(screen.getByText("That the deck stayed.")).toBeInTheDocument();
    const first = calls.find((call) => call.url.endsWith("/api/grill"));
    expect(first?.body).toEqual({
      chapter_id: "CHP-0001",
      source_ref: "SRC-000184",
      turns: [],
    });
    expect(screen.getByRole("status")).toHaveTextContent("1 metered call on claude-opus-5");

    fireEvent.click(screen.getByRole("button", { name: "Use recommended" }));
    expect(screen.getByLabelText("Answer")).toHaveValue("That the deck stayed.");
    fireEvent.click(screen.getByRole("button", { name: "Answer" }));

    expect(await screen.findByText("Where does it open?")).toBeInTheDocument();
    const second = calls.filter((call) => call.url.endsWith("/api/grill"))[1];
    expect(second.body).toEqual({
      chapter_id: "CHP-0001",
      source_ref: "SRC-000184",
      turns: [
        {
          role: "interviewer",
          text: "What does the reader know by the end?\n\nRecommended answer: That the deck stayed.",
        },
        { role: "author", text: "That the deck stayed." },
      ],
    });
  });

  it("puts the draft into Write now for the author to edit and write", async () => {
    const calls = stubFetch({
      model: READY,
      grillReplies: [question("What is it about?", "The deck."), DRAFTED],
    });
    renderAt("/sections/SEC-0003");
    await dialog();
    fireEvent.click(screen.getByRole("tab", { name: "Grill me" }));
    fireEvent.click(await screen.findByRole("button", { name: "Start the interview" }));
    await screen.findByText("What is it about?");

    fireEvent.change(screen.getByLabelText("Answer"), { target: { value: "The deck." } });
    fireEvent.click(screen.getByRole("button", { name: "Write it now" }));

    expect(await screen.findByText(/Drafted from the interview/)).toBeInTheDocument();
    expect(screen.getByLabelText("Brief")).toHaveValue("The evening the street saw the deck.");
    expect(screen.getByLabelText("Prose")).toHaveValue(DRAFTED.draft);
    const last = calls.filter((call) => call.url.endsWith("/api/grill")).at(-1);
    expect((last?.body as { turns: unknown[] }).turns.slice(-2)).toEqual([
      { role: "author", text: "The deck." },
      { role: "author", text: "Write it now." },
    ]);
    // Nothing was written by the interview itself: the Write button is the act.
    expect(calls.some((call) => call.url.endsWith("/sections") && call.method === "POST")).toBe(
      false,
    );

    fireEvent.click(screen.getByRole("button", { name: "Write" }));
    await waitFor(() =>
      expect(
        calls.some((call) => call.url.endsWith("/sections") && call.method === "POST"),
      ).toBe(true),
    );
    const write = calls.find((call) => call.url.endsWith("/sections") && call.method === "POST");
    expect(write?.url).toBe("/api/chapters/CHP-0008/sections");
    expect(write?.body).toEqual({ brief: DRAFTED.brief, draft: DRAFTED.draft });
  });

  it("shows why a reply could not be used and lets the author ask again", async () => {
    const calls = stubFetch({
      model: READY,
      grillReplies: [
        {
          ...DRAFTED,
          done: false,
          brief: "",
          draft: "",
          rejected: [{ anchor: "interview", reason: "the model refused: no" }],
        },
        question("Second try?", "Yes."),
      ],
    });
    renderAt("/");
    await dialog();
    fireEvent.click(screen.getByRole("tab", { name: "Grill me" }));
    fireEvent.click(await screen.findByRole("button", { name: "Start the interview" }));

    expect(await screen.findByText(/could not be used: the model refused: no/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ask again" }));

    expect(await screen.findByText("Second try?")).toBeInTheDocument();
    expect(calls.filter((call) => call.url.endsWith("/api/grill"))).toHaveLength(2);
  });
});
