import { useState, type ReactNode } from "react";

interface TreeSectionProps {
  label: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** One collapsible section of the sidebar - the shape all three trees and
 * every source-type/subject group inside them share (§19.1). */
export function TreeSection({ label, defaultOpen = true, children }: TreeSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="mb-1">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded px-3 py-1.5 text-left font-mono text-[11px] uppercase tracking-wide text-secondary hover:bg-hover hover:text-ink"
      >
        <span>{label}</span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="px-1">{children}</div>}
    </section>
  );
}
