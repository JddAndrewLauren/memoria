import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, createSubject } from "../api/client";
import { Dialog } from "./Dialog";
import { Region } from "./SettingsRegion";

interface NewSubjectDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * New subject (ADR-0014): a name and the four declarations every subject
 * prompt carries (part 06 §8.1). The id is derived from the name on the
 * server, so the author never types one. Create commits the prompt as the
 * author, through the write path, and the SUBJECTS tree re-reads.
 */
export function NewSubjectDialog({ open, onClose }: NewSubjectDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} label="New subject" width="w-[640px]">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-serif text-lg text-ink">New subject</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close new subject"
          className="rounded px-2 py-1 text-lg text-secondary hover:bg-hover hover:text-ink"
        >
          {"×"}
        </button>
      </div>
      <div className="max-h-[75vh] overflow-y-auto p-5">
        <NewSubjectForm onClose={onClose} />
      </div>
    </Dialog>
  );
}

function NewSubjectForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [match, setMatch] = useState("");
  const [hazards, setHazards] = useState("");
  const [auditQuestions, setAuditQuestions] = useState("");
  const [autoPromote, setAutoPromote] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      createSubject({
        name: name.trim(),
        match: match.trim(),
        hazards: hazards.trim(),
        audit_questions: auditQuestions.trim(),
        auto_promote: autoPromote,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["subjects"] });
      onClose();
    },
  });

  const canCreate =
    name.trim().length > 0 && match.trim().length > 0 && !create.isPending;
  const field =
    "w-full rounded border border-border bg-card px-2 py-1.5 font-serif text-sm leading-relaxed text-body";

  return (
    <div className="space-y-5">
      <Region
        label="Name"
        note="What the tree calls it. Its id is derived - Key dates becomes SUB-key-dates - and never changes."
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="Name"
          placeholder="Places"
          autoFocus
          className={field}
        />
      </Region>
      <Region
        label="Match"
        note="What counts as an entry under this subject - what the extraction looks for."
      >
        <textarea
          value={match}
          onChange={(event) => setMatch(event.target.value)}
          aria-label="Match"
          rows={3}
          placeholder="An entry under Places represents a location the archive returns to."
          className={field}
        />
      </Region>
      <Region
        label="Hazards"
        note="How matching goes wrong here - what not to merge, what not to assume. Optional now; the prompt file can be edited later."
      >
        <textarea
          value={hazards}
          onChange={(event) => setHazards(event.target.value)}
          aria-label="Hazards"
          rows={3}
          className={field}
        />
      </Region>
      <Region
        label="Audit questions"
        note="What this subject asks of new prose, one question per line. Optional now."
      >
        <textarea
          value={auditQuestions}
          onChange={(event) => setAuditQuestions(event.target.value)}
          aria-label="Audit questions"
          rows={3}
          className={field}
        />
      </Region>
      <label className="flex items-center gap-2 text-sm text-body">
        <input
          type="checkbox"
          checked={autoPromote}
          onChange={(event) => setAutoPromote(event.target.checked)}
        />
        Auto-promote
        <span className="text-xs text-muted">
          candidates above the recurrence filter become entries without your say
        </span>
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => create.mutate()}
          disabled={!canCreate}
          className="rounded bg-ink px-3 py-1 text-sm text-card hover:bg-body disabled:opacity-50"
        >
          {create.isPending ? "Creating…" : "Create"}
        </button>
        {create.isError && (
          <span className="text-xs text-muted">
            {create.error instanceof ApiError
              ? create.error.message
              : "The subject could not be created. Your text is still here."}
          </span>
        )}
      </div>
    </div>
  );
}
