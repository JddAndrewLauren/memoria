import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

interface TreeSectionProps {
  label: string;
  defaultOpen?: boolean;
  /** A route the header itself opens; the fold then lives on its own glyph. */
  to?: string;
  children: ReactNode;
}

/** One collapsible section of the sidebar - the shape all three trees and
 * every source-type/subject group inside them share (§19.1). */
export function TreeSection({ label, defaultOpen = true, to, children }: TreeSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const header = "font-mono text-[11px] uppercase tracking-wide text-secondary hover:bg-hover hover:text-ink";
  if (to) {
    return (
      <section className="mb-1">
        <div className="flex items-stretch">
          <NavLink
            to={to}
            end
            className={({ isActive }) =>
              `flex-1 rounded px-3 py-1.5 text-left ${header} ${isActive ? "bg-hover text-ink" : ""}`
            }
          >
            {label}
          </NavLink>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
            className={`rounded px-3 ${header}`}
          >
            {open ? "−" : "+"}
          </button>
        </div>
        {open && <div className="px-1">{children}</div>}
      </section>
    );
  }
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
