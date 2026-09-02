import { ManuscriptTree } from "./ManuscriptTree";
import { SubjectsTree } from "./SubjectsTree";
import { SourcesTree } from "./SourcesTree";

interface SidebarProps {
  onOpenSearch: () => void;
}

/**
 * The persistent shell (§19.1): identity, the search glyph, and the three
 * trees - MANUSCRIPT, SUBJECTS, SOURCES. "Ask Memoria" and "Review" are not
 * here: both need the model driver #24 explicitly does not build.
 */
export function Sidebar({ onOpenSearch }: SidebarProps) {
  return (
    <aside className="flex w-[232px] shrink-0 flex-col border-r border-border bg-rail">
      <div className="flex items-center justify-between border-b border-border px-3 py-4">
        <div>
          <div className="font-serif text-lg text-ink">Memoria</div>
          <div className="font-mono text-[10px] uppercase tracking-wide text-muted">
            The archive
          </div>
        </div>
        <button
          type="button"
          onClick={onOpenSearch}
          aria-label="Search"
          className="rounded px-2 py-1 text-lg text-secondary hover:bg-hover hover:text-ink"
        >
          {"⌕"}
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        <ManuscriptTree />
        <SubjectsTree />
        <SourcesTree />
      </nav>
    </aside>
  );
}
