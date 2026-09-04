import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  createSection,
  grill,
  readManuscript,
  readSection,
  readSource,
  type GrillOut,
  type GrillTurnIn,
  type OutlineChapterOut,
} from "../api/client";
import { useNewSectionContext } from "../lib/newSectionContext";
import { Dialog } from "./Dialog";
import { Region } from "./SettingsRegion";
import { describeSpend, useModelReadiness } from "./DirectRun";

interface NewSectionDialogProps {
  open: boolean;
  onClose: () => void;
}

type Mode = "write" | "grill";

/**
 * One turn of the interview as the dialog shows it. The interviewer's
 * recommended answer is kept apart from its question so the author can
 * take it with one click; both go back to the server as the turn's text.
 */
interface Turn {
  role: GrillTurnIn["role"];
  text: string;
  recommended?: string;
}

/**
 * New section (ADR-0011): the dialog the floating button opens. Where the
 * section goes (a chapter - appended; the current one when opened from a
 * section page), the source it was opened from (joins the interviewer's
 * context), and two ways to arrive at prose: **Write now**, a brief and the
 * prose typed here, or **Grill me**, the writing interview - run directly
 * when Settings > Model is ready, otherwise from a session with the
 * `grill-writing` skill, and the dialog prints the exact command.
 *
 * The one durable write is `createSection`, and it is the author's act
 * whichever way the prose arrived: a grilled draft lands in the same
 * editable box and the author's Write commits it as theirs, the way an
 * applied rewrite from Review is theirs. The interview's transcript lives
 * here for as long as the dialog is open and nowhere else.
 */
export function NewSectionDialog({ open, onClose }: NewSectionDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} label="New section" width="w-[720px]">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-serif text-lg text-ink">New section</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close new section"
          className="rounded px-2 py-1 text-lg text-secondary hover:bg-hover hover:text-ink"
        >
          {"×"}
        </button>
      </div>
      <div className="max-h-[75vh] overflow-y-auto p-5">
        <NewSectionForm onClose={onClose} />
      </div>
    </Dialog>
  );
}

function NewSectionForm({ onClose }: { onClose: () => void }) {
  const context = useNewSectionContext();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const manuscript = useQuery({ queryKey: ["manuscript"], queryFn: readManuscript });
  // The same keys the Section and Source pages use, so opening the dialog
  // from one of them reads what that page already holds.
  const section = useQuery({
    queryKey: ["section", context.sectionId],
    queryFn: () => readSection(context.sectionId as string),
    enabled: Boolean(context.sectionId),
  });
  const source = useQuery({
    queryKey: ["source", context.sourceId],
    queryFn: () => readSource(context.sourceId as string),
    enabled: Boolean(context.sourceId),
  });

  const chapters = manuscript.data?.chapters ?? [];
  const [chapterId, setChapterId] = useState<string | null>(null);
  const [sourceIncluded, setSourceIncluded] = useState(true);
  const [mode, setMode] = useState<Mode>("write");
  const [brief, setBrief] = useState("");
  const [draft, setDraft] = useState("");
  const [draftedFromInterview, setDraftedFromInterview] = useState(false);
  const briefTouched = useRef(false);

  // The default chapter: the one the author is reading, once its section
  // has loaded, else the first. Chosen once; the author's pick then stands.
  useEffect(() => {
    if (chapterId !== null) return;
    if (context.sectionId && !section.isError) {
      if (section.data) setChapterId(section.data.chapter_id);
      return;
    }
    if (chapters.length > 0) setChapterId(chapters[0].id);
  }, [chapterId, chapters, context.sectionId, section.data, section.isError]);

  // A source in context starts the brief off naming it - the brief is where
  // a section says what it draws on - unless the author already wrote one.
  useEffect(() => {
    if (!source.data || !sourceIncluded || briefTouched.current) return;
    setBrief(`From ${source.data.id} (${sourceTitle(source.data)}).`);
  }, [source.data, sourceIncluded]);

  const chapter = chapters.find((item) => item.id === chapterId) ?? null;
  const sourceRef = context.sourceId && sourceIncluded ? context.sourceRef : null;

  const write = useMutation({
    mutationFn: () =>
      createSection(chapterId as string, { brief: brief.trim(), draft: draft.trim() }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["manuscript"] });
      onClose();
      navigate(`/sections/${created.id}`);
    },
  });

  const canWrite = Boolean(chapter) && draft.trim().length > 0 && !write.isPending;

  return (
    <div className="space-y-6">
      <Region
        label="Where"
        note="A new section is appended to the end of its chapter. Its place in the chapter can be changed later; the section's id never does."
      >
        {manuscript.isLoading && <p className="text-xs text-muted">Loading the manuscript…</p>}
        {manuscript.isError && (
          <p className="text-xs text-muted">The manuscript could not be loaded.</p>
        )}
        {manuscript.data && chapters.length === 0 && (
          <p className="text-xs text-muted">
            {manuscript.data.is_built
              ? "No chapters yet - a section needs a chapter to go in."
              : "No manuscript yet - there is no chapters/ directory in this repository."}
          </p>
        )}
        {chapters.length > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            <select
              aria-label="Chapter"
              value={chapterId ?? ""}
              onChange={(event) => setChapterId(event.target.value)}
              className="max-w-full rounded border border-border bg-card px-2 py-1 text-sm text-body"
            >
              {chapters.map((item) => (
                <option key={item.id} value={item.id}>
                  {chapterLabel(item)}
                </option>
              ))}
            </select>
            {chapter && (
              <span className="text-xs text-muted">
                Appended as section {chapter.number}.{nextSectionNumber(chapter)}
              </span>
            )}
          </div>
        )}
      </Region>

      {context.sourceId && (
        <Region
          label="Context"
          note="The source you were reading. It joins the interviewer's context, and the brief starts by naming it."
        >
          {sourceIncluded ? (
            <span className="inline-flex items-center gap-2 rounded-chip border border-border bg-sources-tint px-2 py-0.5 text-xs text-body">
              <span className="font-mono text-[11px]">{context.sourceId}</span>
              {source.data && <span className="text-secondary">{sourceTitle(source.data)}</span>}
              <button
                type="button"
                onClick={() => setSourceIncluded(false)}
                aria-label={`Remove ${context.sourceId} from the context`}
                className="text-muted hover:text-ink"
              >
                ×
              </button>
            </span>
          ) : (
            <p className="text-xs text-muted">
              Not included.{" "}
              <button
                type="button"
                onClick={() => setSourceIncluded(true)}
                className="underline"
              >
                Include {context.sourceId}
              </button>
            </p>
          )}
        </Region>
      )}

      <div role="tablist" aria-label="How to write it" className="flex gap-1 border-b border-border">
        <ModeTab current={mode} mode="write" onSelect={setMode}>
          Write now
        </ModeTab>
        <ModeTab current={mode} mode="grill" onSelect={setMode}>
          Grill me
        </ModeTab>
      </div>

      {mode === "write" && (
        <div role="tabpanel" aria-label="Write now" className="space-y-4">
          {draftedFromInterview && (
            <p className="rounded border border-amber bg-amber-tint-soft px-3 py-2 text-xs text-secondary">
              Drafted from the interview. Edit anything, then Write - it commits as your own.
            </p>
          )}
          <Region
            label="Brief"
            note="What this section is, covers and is for - optional. Left empty, the opening of your prose stands in, marked unconfirmed until you edit or confirm it."
          >
            <input
              value={brief}
              onChange={(event) => {
                briefTouched.current = true;
                setBrief(event.target.value);
              }}
              aria-label="Brief"
              placeholder="The evening the street saw the deck, and said nothing."
              className="w-full rounded border border-border bg-card px-2 py-1.5 font-serif text-sm text-body"
            />
          </Region>
          <Region label="Prose" note="The section itself. Committed as yours, in one commit, when you press Write.">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              aria-label="Prose"
              rows={12}
              autoFocus
              className="w-full rounded border border-border bg-card px-2 py-1.5 font-serif text-sm leading-relaxed text-body"
            />
          </Region>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => write.mutate()}
              disabled={!canWrite}
              className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
            >
              {write.isPending ? "Writing…" : "Write"}
            </button>
            {write.isError && (
              <span className="text-xs text-muted">
                {write.error instanceof ApiError
                  ? write.error.message
                  : "The section could not be written. Your text is still here."}
              </span>
            )}
          </div>
        </div>
      )}

      {mode === "grill" && (
        <div role="tabpanel" aria-label="Grill me">
          <Grilling
            chapterId={chapterId}
            sourceRef={sourceRef}
            onDrafted={(result) => {
              briefTouched.current = true;
              setBrief(result.brief);
              setDraft(result.draft);
              setDraftedFromInterview(true);
              setMode("write");
            }}
          />
        </div>
      )}
    </div>
  );
}

function ModeTab({
  current,
  mode,
  onSelect,
  children,
}: {
  current: Mode;
  mode: Mode;
  onSelect: (mode: Mode) => void;
  children: React.ReactNode;
}) {
  const selected = current === mode;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={() => onSelect(mode)}
      className={`-mb-px border-b-2 px-3 py-2 text-sm ${
        selected
          ? "border-manuscript text-ink"
          : "border-transparent text-secondary hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * The interview (ADR-0011), the `/grilling` shape: one question at a time,
 * a recommended answer with each, the author's decisions the author's.
 * Every answer is one POST carrying the whole transcript - the server keeps
 * none of it - and nothing runs until the author starts it (part 08 §12.1:
 * nothing that needs a model runs unasked). Not ready, it says how to run
 * the same interview from a session, with the exact command.
 */
function Grilling({
  chapterId,
  sourceRef,
  onDrafted,
}: {
  chapterId: string | null;
  sourceRef: string | null;
  onDrafted: (result: GrillOut) => void;
}) {
  const { ready } = useModelReadiness();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [answer, setAnswer] = useState("");
  const [lastSpend, setLastSpend] = useState<string | null>(null);
  const [rejected, setRejected] = useState<string | null>(null);

  const ask = useMutation({
    mutationFn: (transcript: Turn[]) =>
      grill({
        chapter_id: chapterId as string,
        source_ref: sourceRef,
        turns: transcript.map(toRequestTurn),
      }),
    onSuccess: (result) => {
      setLastSpend(describeSpend(result.spend));
      if (result.rejected.length > 0) {
        setRejected(result.rejected.map((item) => item.reason).join("; "));
        return;
      }
      setRejected(null);
      if (result.done) {
        onDrafted(result);
        return;
      }
      setTurns((current) => [
        ...current,
        { role: "interviewer", text: result.question, recommended: result.recommended_answer },
      ]);
    },
  });

  if (!ready) {
    const command = `/grill-writing ${chapterId ?? "CHP-…"}${sourceRef ? ` ${sourceRef}` : ""}`;
    return (
      <div className="space-y-3 text-sm text-secondary">
        <p>
          The grilling is an interview: one question at a time, a recommended answer with each,
          until you and the interviewer share what the section says - then it drafts, and you
          write. It runs from a session until direct runs are on.
        </p>
        <p>
          In Claude Code, run{" "}
          <code className="rounded bg-panel px-1.5 py-0.5 font-mono text-xs text-ink">{command}</code>
          , or switch direct runs on under Settings &gt; Model to run it here.
        </p>
      </div>
    );
  }

  function send(next: Turn[]) {
    setTurns(next);
    setAnswer("");
    ask.mutate(next);
  }

  const started = turns.length > 0 || ask.isPending;
  const awaitingAnswer =
    turns.length > 0 && turns[turns.length - 1].role === "interviewer" && !ask.isPending;

  return (
    <div className="space-y-4">
      {!started && (
        <div className="space-y-3">
          <p className="text-sm text-secondary">
            One question at a time, a recommended answer with each; the decisions are yours. When
            you share what the section says - or when you say to write - it drafts the brief and
            the prose for you to edit and write. Every turn is one metered call.
          </p>
          <button
            type="button"
            onClick={() => send([])}
            disabled={!chapterId}
            className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
          >
            Start the interview
          </button>
        </div>
      )}

      {turns.length > 0 && (
        <ol aria-label="Interview" className="space-y-3">
          {turns.map((turn, index) => (
            <li
              key={index}
              className={`rounded border px-3 py-2 text-sm ${
                turn.role === "interviewer"
                  ? "border-border bg-panel text-body"
                  : "border-border-faint bg-card text-ink"
              }`}
            >
              <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted">
                {turn.role === "interviewer" ? "Interviewer" : "You"}
              </div>
              <p className="whitespace-pre-wrap">{turn.text}</p>
              {turn.recommended && (
                <p className="mt-2 text-xs text-secondary">
                  <span className="font-mono text-[10px] uppercase tracking-wide text-muted">
                    Recommended:{" "}
                  </span>
                  {turn.recommended}
                  {index === turns.length - 1 && awaitingAnswer && (
                    <>
                      {" "}
                      <button
                        type="button"
                        onClick={() => setAnswer(turn.recommended as string)}
                        className="underline"
                      >
                        Use recommended
                      </button>
                    </>
                  )}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}

      {(ask.isPending || lastSpend) && (
        <p role="status" className="text-xs text-secondary">
          {ask.isPending ? "Asking…" : lastSpend}
        </p>
      )}
      {rejected && (
        <p className="rounded border border-amber bg-amber-tint-soft px-3 py-2 text-xs text-secondary">
          The interviewer's reply could not be used: {rejected}.{" "}
          <button type="button" onClick={() => ask.mutate(turns)} className="underline">
            Ask again
          </button>
        </p>
      )}
      {ask.isError && (
        <p className="text-xs text-muted">
          {ask.error instanceof ApiError ? ask.error.message : "The interview could not continue."}
        </p>
      )}

      {awaitingAnswer && (
        <div className="space-y-2">
          <textarea
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            aria-label="Answer"
            rows={3}
            autoFocus
            className="w-full rounded border border-border bg-card px-2 py-1.5 font-serif text-sm text-body"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => send([...turns, { role: "author", text: answer.trim() }])}
              disabled={answer.trim().length === 0}
              className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
            >
              Answer
            </button>
            <button
              type="button"
              onClick={() =>
                send([
                  ...turns,
                  ...(answer.trim() ? [{ role: "author", text: answer.trim() } as Turn] : []),
                  { role: "author", text: "Write it now." },
                ])
              }
              className="rounded border border-border px-3 py-1 text-sm text-body hover:bg-panel"
            >
              Write it now
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function toRequestTurn(turn: Turn): GrillTurnIn {
  if (turn.role === "interviewer" && turn.recommended) {
    return { role: turn.role, text: `${turn.text}\n\nRecommended answer: ${turn.recommended}` };
  }
  return { role: turn.role, text: turn.text };
}

// Position is the directory number, and a new section takes the next one
// after the chapter's last (`manuscript._next_directory_number`) - not a
// count, since a deleted section leaves a gap the numbering keeps.
function nextSectionNumber(chapter: OutlineChapterOut): number {
  return Math.max(0, ...chapter.sections.map((section) => section.number)) + 1;
}

function chapterLabel(chapter: OutlineChapterOut): string {
  return `${chapter.number}  ${chapter.excerpt || chapter.id}`;
}

function sourceTitle(source: { original_locator: string; original_file: string }): string {
  return source.original_locator || source.original_file;
}
