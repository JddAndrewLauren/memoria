import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WindowDropZone } from "./WindowDropZone";

/** The window as a drop target (ADR-0013): a scrim while a drag carrying
 *  files is over the window, nothing for any other drag, and the dropped
 *  entries handed on as picked files. */
function drag(type: string, dataTransfer: Partial<DataTransfer>) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
  return event;
}

describe("the window drop zone", () => {
  it("shows the scrim only for a drag that carries files", () => {
    render(<WindowDropZone onFiles={() => {}} />);

    fireEvent(window, drag("dragenter", { types: ["text/plain"] }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    fireEvent(window, drag("dragenter", { types: ["Files"] }));
    fireEvent(window, drag("dragenter", { types: ["Files"] }));
    expect(screen.getByRole("status")).toHaveTextContent("Drop files or folders");
    fireEvent(window, drag("dragleave", { types: ["Files"] }));
    expect(screen.getByRole("status")).toBeInTheDocument();
    fireEvent(window, drag("dragleave", { types: ["Files"] }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("hands the dropped files on, walking a folder, and clears the scrim", async () => {
    const onFiles = vi.fn();
    render(<WindowDropZone onFiles={onFiles} />);
    const entry = {
      isFile: false,
      isDirectory: true,
      name: "box",
      createReader: () => {
        let done = false;
        return {
          readEntries: (ok: (entries: unknown[]) => void) => {
            const batch = done
              ? []
              : [{ isFile: true, isDirectory: false, name: "a.txt", file: (cb: (f: File) => void) => cb(new File(["x"], "a.txt")) }];
            done = true;
            ok(batch);
          },
        };
      },
    };
    const items = [{ kind: "file", getAsFile: () => null, webkitGetAsEntry: () => entry }];

    fireEvent(window, drag("dragenter", { types: ["Files"] }));
    fireEvent(window, drag("drop", { types: ["Files"], items: items as unknown as DataTransferItemList }));

    await waitFor(() => expect(onFiles).toHaveBeenCalledTimes(1));
    expect(onFiles.mock.calls[0][0].map((row: { path: string }) => row.path)).toEqual(["box/a.txt"]);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
