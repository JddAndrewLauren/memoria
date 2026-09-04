import { useEffect, useState } from "react";
import { filesFromDataTransfer, type PickedFile } from "../lib/rawUnits";

/**
 * The whole window as a drop target for raw units (ADR-0013). Listens on
 * `window` so no page needs to know; reacts only to a drag that carries
 * files, and counts enter/leave so the scrim does not flicker as the drag
 * crosses child elements. The DataTransfer is read before the handler
 * returns - it is dead after.
 */
export function WindowDropZone({ onFiles }: { onFiles: (files: PickedFile[]) => void }) {
  const [depth, setDepth] = useState(0);

  useEffect(() => {
    const carriesFiles = (event: DragEvent) =>
      Boolean(event.dataTransfer?.types && Array.from(event.dataTransfer.types).includes("Files"));
    function onEnter(event: DragEvent) {
      if (!carriesFiles(event)) return;
      event.preventDefault();
      setDepth((value) => value + 1);
    }
    function onOver(event: DragEvent) {
      if (!carriesFiles(event)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    }
    function onLeave(event: DragEvent) {
      if (!carriesFiles(event)) return;
      setDepth((value) => Math.max(0, value - 1));
    }
    function onDrop(event: DragEvent) {
      if (!carriesFiles(event)) return;
      event.preventDefault();
      setDepth(0);
      const items = event.dataTransfer?.items;
      if (!items) return;
      void filesFromDataTransfer(Array.from(items)).then((files) => {
        if (files.length > 0) onFiles(files);
      });
    }
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragover", onOver);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, [onFiles]);

  if (depth === 0) return null;
  return (
    <div
      role="status"
      aria-label="Drop to add sources"
      className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center border-4 border-dashed border-sources bg-card/80"
    >
      <p className="rounded-card bg-card px-6 py-4 font-serif text-lg text-ink shadow-lg">
        Drop files or folders to add them as sources
      </p>
    </div>
  );
}
