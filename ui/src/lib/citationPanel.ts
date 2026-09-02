import { createContext, useContext } from "react";

export interface CitationPanelApi {
  /**
   * Open the slide-over on a reference - a citation into evidence
   * (`src-000184-p17`, `SRC-000184`) or a backlink into an entry
   * (`SUB-people/bob`). Pushes onto the panel's own small stack rather than
   * navigating, so following a citation never costs the reader their place
   * (§19.9) and a backlink traverses back into the same panel (#25's
   * "traverse in both directions").
   */
  open: (ref: string) => void;
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
