import type { ReactNode } from "react";

/**
 * One labelled region of a Settings panel: a small-caps heading, an
 * optional note, and its controls. Shared by every panel so the rail's
 * sections read as one surface.
 */
export function Region({
  label,
  note,
  children,
}: {
  label: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h4 className="font-mono text-[11px] uppercase tracking-wide text-secondary">{label}</h4>
      {note && <p className="mb-2 mt-0.5 max-w-[560px] text-xs text-muted">{note}</p>}
      {children}
    </section>
  );
}
