/**
 * The floating `+ New section` button (ADR-0011): the one affordance for
 * starting a piece of manuscript from anywhere in the app. Fixed to the
 * bottom-right corner, under the overlays (`z-30`; a dialog's scrim is
 * `z-50`), so it never sits on top of one. Design tokens only.
 */
export function NewSectionButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="New section"
      title="New section"
      className="fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-sm text-card shadow-lg hover:bg-body"
    >
      <span className="text-lg leading-none" aria-hidden="true">
        {"+"}
      </span>
      New section
    </button>
  );
}
