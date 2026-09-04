import { describe, expect, it } from "vitest";
import {
  filesFromDataTransfer,
  filesFromFileList,
  formatBytes,
  isHiddenPath,
  type DropItem,
} from "./rawUnits";

function file(name: string, relativePath = ""): File {
  const made = new File(["x"], name);
  Object.defineProperty(made, "webkitRelativePath", { value: relativePath });
  return made;
}

// jsdom has no File and Directory Entries API: these are the shapes a
// browser hands back, hand-rolled.
function fileEntry(name: string) {
  return {
    isFile: true,
    isDirectory: false,
    name,
    file: (ok: (f: File) => void) => ok(new File(["x"], name)),
  };
}
function directoryEntry(name: string, children: unknown[], batch = 100) {
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader() {
      let offset = 0;
      return {
        readEntries(ok: (entries: unknown[]) => void) {
          const slice = children.slice(offset, offset + batch);
          offset += slice.length;
          ok(slice);
        },
      };
    },
  };
}
function item(entry: unknown, fallback: File | null = null): DropItem {
  return { kind: "file", getAsFile: () => fallback, webkitGetAsEntry: () => entry };
}

describe("files from a picker", () => {
  it("uses the folder-relative path when the input was a folder pick, else the name", () => {
    const picked = filesFromFileList([file("a.txt"), file("b.txt", "box/1952/b.txt")]);
    expect(picked.map((row) => row.path)).toEqual(["a.txt", "box/1952/b.txt"]);
  });

  it("drops dotfiles and dot-folders, which the ledger would otherwise number", () => {
    const picked = filesFromFileList([file(".DS_Store"), file("x", "box/.git/x"), file("ok.txt")]);
    expect(picked.map((row) => row.path)).toEqual(["ok.txt"]);
    expect(isHiddenPath("a/.b/c")).toBe(true);
    expect(isHiddenPath("a/b.c")).toBe(false);
  });
});

describe("files from a drop", () => {
  it("walks a dropped folder, keeping its shape and looping readEntries past one batch", async () => {
    const children = Array.from({ length: 150 }, (_, i) => fileEntry(`n${String(i).padStart(3, "0")}.txt`));
    const tree = directoryEntry("box", [directoryEntry("inner", [fileEntry("deep.txt"), fileEntry(".hidden")]), ...children], 100);

    const picked = await filesFromDataTransfer([item(tree), item(fileEntry("loose.txt"))]);

    const paths = picked.map((row) => row.path);
    expect(paths).toHaveLength(152);
    expect(paths[0]).toBe("box/inner/deep.txt");
    expect(paths).toContain("box/n149.txt");
    expect(paths.at(-1)).toBe("loose.txt");
    expect(paths.some((p) => p.includes(".hidden"))).toBe(false);
  });

  it("falls back to the flat file where the entries API is missing, and skips non-files", async () => {
    const picked = await filesFromDataTransfer([
      { kind: "file", getAsFile: () => new File(["x"], "plain.txt") },
      { kind: "string", getAsFile: () => null },
    ]);
    expect(picked.map((row) => row.path)).toEqual(["plain.txt"]);
  });
});

describe("formatBytes", () => {
  it("picks a unit", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(20 * 1024)).toBe("20 KB");
    expect(formatBytes(64 * 1024 * 1024)).toBe("64.0 MB");
  });
});
