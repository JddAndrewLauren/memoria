import { createContext, useContext } from "react";

export interface OpenOptions {
  /**
   * The words the citation was made for - a decision's text, say - so that
   * when the reference is one transcript turn (`SES-...#T017`, #34) the
   * panel can land on the sentence the author decided in, not merely the
   * turn. Matched with whitespace collapsed; a highlight the turn does not
   * contain marks nothing and the turn is shown whole.
   */
  highlight?: string;
}

export interface CitationPanelApi {
  /**
   * Open the slide-over on a reference - a citation into evidence
   * (`src-000184-p17`, `SRC-000184`), a backlink into an entry
   * (`SUB-people/bob`), or one transcript turn (`SES-20260912-1432#T017`).
   * Pushes onto the panel's own small stack rather than navigating, so
   * following a citation never costs the reader their place (§19.9) and a
   * backlink traverses back into the same panel (#25's "traverse in both
   * directions").
   */
  open: (ref: string, options?: OpenOptions) => void;
  /** Close the panel entirely, returning to the page underneath unchanged. */
  close: () => void;
}

export const CitationPanelContext = createContext<CitationPanelApi | null>(null);

export function useCitationPanel(): CitationPanelApi {
  const context = useContext(CitationPanelContext);
  if (!context) {
    throw new Error("useCitationPanel must be used within a CitationPanelContext.Provider");
  }
  return context;
}

/** A transcript turn reference, the one shape the panel renders as speech. */
export function isTurnRef(ref: string): boolean {
  return /^SES-\d{8}-\d{4}(?:-[0-9a-f]+)?#T\d+$/i.test(ref);
}

const collapse = (text: string) => text.replace(/\s+/g, " ").trim();

type Segmenter = new (
  locale: string,
  options: { granularity: string },
) => { segment(input: string): Iterable<{ segment: string }> };

/**
 * A turn's text as sentences, with the run of sentences the highlight
 * names marked as one. `Intl.Segmenter` does the splitting - every runtime
 * this ships to has it; without it the turn is one sentence, which is
 * honest rather than a second, worse splitter.
 *
 * The highlight is located *by position* in the whitespace-collapsed turn
 * and the pieces overlapping that span are marked, so a short sentence that
 * happens to also occur inside the highlight ("Yes.") is not marked where
 * it stands elsewhere in the turn. The segmenter also breaks on a wrapped
 * line and after "Mr.", so the marked pieces are merged: one sentence to
 * the reader, one mark.
 */
export function sentencesOf(
  text: string,
  highlight?: string,
): { text: string; cited: boolean }[] {
  const Segmenter = (Intl as unknown as { Segmenter?: Segmenter }).Segmenter;
  const pieces: string[] = [];
  if (Segmenter) {
    for (const { segment } of new Segmenter("en", { granularity: "sentence" }).segment(text)) {
      pieces.push(segment);
    }
  } else {
    pieces.push(text);
  }
  const kept = pieces.filter((piece) => piece.trim().length > 0);

  // Each piece's span in the collapsed turn, the pieces joined by one space.
  const spans: { start: number; end: number }[] = [];
  let joined = "";
  for (const piece of kept) {
    const own = collapse(piece);
    if (joined.length > 0) joined += " ";
    spans.push({ start: joined.length, end: joined.length + own.length });
    joined += own;
  }
  const wanted = highlight ? collapse(highlight) : "";
  const at = wanted.length > 0 ? joined.indexOf(wanted) : -1;
  const citedEnd = at + wanted.length;

  const merged: { text: string; cited: boolean }[] = [];
  kept.forEach((piece, index) => {
    const { start, end } = spans[index];
    const cited = at >= 0 && start < citedEnd && end > at;
    const last = merged[merged.length - 1];
    if (cited && last?.cited) {
      last.text += piece;
    } else {
      merged.push({ text: piece, cited });
    }
  });
  return merged;
}
