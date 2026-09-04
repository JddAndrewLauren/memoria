import { useEffect } from "react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  label: string;
  /** Tailwind width classes for the panel; the search dialog's default. */
  width?: string;
  children: React.ReactNode;
}

/**
 * The one modal idiom in the app: a scrim that closes on click, a panel
 * that does not, and Escape. Extracted from the search dialog (§19.8) so
 * the settings dialog (§19.1's footer) does not carry a second copy.
 */
export function Dialog({ open, onClose, label, width = "w-[620px]", children }: DialogProps) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    if (open) document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/40 pt-24"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onClick={(event) => event.stopPropagation()}
        className={`${width} max-w-[90vw] rounded-card border border-border bg-card shadow-lg`}
      >
        {children}
      </div>
    </div>
  );
}
