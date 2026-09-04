import { useLocation, useMatch } from "react-router-dom";

export interface NewSectionContext {
  /** The section the author is reading, when they are on one - its chapter
   *  is where a new section goes by default. */
  sectionId: string | null;
  /** The source the author is reading, when they are on one - it joins the
   *  interviewer's context. */
  sourceId: string | null;
  /** The cited paragraph's anchor, when the source page was reached through
   *  a citation (`/sources/SRC-…#src-…-p17`) - a finer reference than the
   *  record, passed on when it is there. */
  sourceRef: string | null;
}

/**
 * What the New section dialog assumes from where it was opened (ADR-0011):
 * on a section page (or Review, or supplied context), the same chapter; on
 * a source page, that source in the interview's context. Anywhere else,
 * nothing. Read off the route, not passed down, so the floating button
 * needs no knowledge of the page under it.
 */
export function useNewSectionContext(): NewSectionContext {
  const section = useMatch("/sections/:sectionId/*");
  const source = useMatch("/sources/:id/*");
  const location = useLocation();
  const sourceId = source?.params.id ?? null;
  const anchor = location.hash ? location.hash.slice(1) : "";
  return {
    sectionId: section?.params.sectionId ?? null,
    sourceId,
    sourceRef: sourceId ? (anchor ? anchor : sourceId) : null,
  };
}
