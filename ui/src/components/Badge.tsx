import type { ReactNode } from "react";

type Tone = "green" | "amber" | "blue" | "red" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  green: "bg-sources-tint text-sources",
  amber: "bg-amber-tint text-amber",
  blue: "bg-panel text-subjects",
  red: "bg-panel text-manuscript",
  neutral: "bg-panel text-secondary",
};

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`rounded-chip border border-border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
