import { TreeSection } from "./TreeSection";

/**
 * MANUSCRIPT stays empty until M5 - it is present and labelled, honest
 * about being empty, rather than hidden (#24's acceptance criteria).
 */
export function ManuscriptTree() {
  return (
    <TreeSection label="Manuscript">
      <p className="px-2 py-2 text-xs text-muted">
        Empty until M5 - there is no manuscript yet.
      </p>
    </TreeSection>
  );
}
