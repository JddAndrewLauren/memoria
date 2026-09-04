import { useState } from "react";
import { Dialog } from "./Dialog";
import { WritingStyleSettings } from "./WritingStyleSettings";
import { ModelSettings } from "./ModelSettings";

interface SettingsDialogProps {
  open: boolean;
  onClose: () => void;
}

// One entry per setting. The rail exists so the next one is a row here,
// not a second dialog.
const SECTIONS = [
  { id: "writing-style", label: "Writing style" },
  // ADR-0010: the switch for direct runs, the model and the key.
  { id: "model", label: "Model" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

/**
 * Settings (§19.1's footer `⚙ Settings`, ADR-0009): a rail of settings and
 * the selected one's panel. Every setting here is a durable file the author
 * owns, edited through the same write path as everything else - the dialog
 * is a window onto the repository, not a preferences store of its own.
 */
export function SettingsDialog({ open, onClose }: SettingsDialogProps) {
  const [section, setSection] = useState<SectionId>("writing-style");

  return (
    <Dialog open={open} onClose={onClose} label="Settings" width="w-[860px]">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-serif text-lg text-ink">Settings</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close settings"
          className="rounded px-2 py-1 text-lg text-secondary hover:bg-hover hover:text-ink"
        >
          {"×"}
        </button>
      </div>
      <div className="flex max-h-[75vh]">
        <nav aria-label="Settings sections" className="w-[180px] shrink-0 border-r border-border py-2">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              aria-current={section === item.id ? "page" : undefined}
              className={`block w-full px-4 py-2 text-left text-sm ${
                section === item.id
                  ? "border-l-[3px] border-manuscript bg-panel text-ink"
                  : "border-l-[3px] border-transparent text-secondary hover:bg-hover hover:text-ink"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="flex-1 overflow-y-auto p-5">
          {section === "writing-style" && open && <WritingStyleSettings />}
          {section === "model" && open && <ModelSettings />}
        </div>
      </div>
    </Dialog>
  );
}
