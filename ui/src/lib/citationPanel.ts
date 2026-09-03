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

/**
 * A turn's text as sentences, each flagged if it is the one the highlight
 * names. `Intl.Segmenter` where the runtime has it, a terminal-punctuation
 * split otherwise - what the panel needs is a sentence boundary good enough
 * to land a reader on the right line, not a parser.
 */
export function sentencesOf(
  text: string,
  highlight?: string,
): { text: string; cited: boolean }[] {
  const pieces: string[] = [];
  const Segmenter = (Intl as unknown as { Segmenter?: new (locale: string, options: { granularity: string }) => { segment(input: string): Iterable<{ segment: string }> } }).Segmenter;
  if (Segmenter) {
    for (const { segment } of new Segmenter("en", { granularity: "sentence" }).segment(text)) {
      pieces.push(segment);
    }
  } else {
    pieces.push(...(text.match(/[^.!?]+(?:[.!?]+["')\]]*|$)\s*/g) ?? [text]));
  }
  const wanted = highlight ? collapse(highlight) : "";
  const flagged = pieces
    .filter((piece) => piece.trim().length > 0)
    .map((piece) => {
      const own = collapse(piece);
      const cited = wanted.length > 0 && (own.includes(wanted) || wanted.includes(own));
      return { text: piece, cited };
    });
  // The segmenter breaks on a newline and after "Mr." alike, so a sentence
  // the transcript wrapped, or one carrying an abbreviation, arrives as
  // several cited pieces. They are one sentence to the reader, and one mark.
  const merged: { text: string; cited: boolean }[] = [];
  for (const piece of flagged) {
    const last = merged[merged.length - 1];
    if (piece.cited && last?.cited) {
      last.text += piece.text;
    } else {
      merged.push({ ...piece });
    }
  }
  return merged;
}
