// Collecting the files the author picked or dropped, as the paths the
// ledger will record them at (ADR-0013). Pure and React-free so the folder
// walk - the one piece of browser API here jsdom does not have - can be
// exercised with hand-rolled entries.

export interface PickedFile {
  file: File;
  /** Relative to `raw/`, forward-slash, keeping the folder it came from. */
  path: string;
}

/** The server's per-file cap (`RawUnitUpload`): refused there at 422, so
 *  named here and never sent. */
export const MAX_RAW_UNIT_BYTES = 64 * 1024 * 1024;

/** A dotfile or dot-folder anywhere in the path. The ledger numbers every
 *  file under `raw/`, so a `.DS_Store` would hold a SRC id forever; the
 *  server refuses these too, this just keeps them out of the list. */
export function isHiddenPath(path: string): boolean {
  return path.split("/").some((segment) => segment.startsWith("."));
}

function normalise(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "");
}

/** From a file input: `webkitRelativePath` is set when the input had
 *  `webkitdirectory`, and empty for a plain multi-file pick. */
export function filesFromFileList(list: FileList | File[]): PickedFile[] {
  const picked: PickedFile[] = [];
  for (const file of Array.from(list)) {
    const path = normalise(file.webkitRelativePath || file.name);
    if (!isHiddenPath(path)) picked.push({ file, path });
  }
  return picked;
}

// The File and Directory Entries API, typed by hand: TypeScript's DOM lib
// carries `FileSystemEntry` but not `webkitGetAsEntry` on every target.
interface FileEntry {
  isFile: true;
  isDirectory: false;
  name: string;
  file(ok: (file: File) => void, fail?: (error: unknown) => void): void;
}
interface DirectoryEntry {
  isFile: false;
  isDirectory: true;
  name: string;
  createReader(): { readEntries(ok: (entries: Entry[]) => void, fail?: (error: unknown) => void): void };
}
type Entry = FileEntry | DirectoryEntry;
export interface DropItem {
  kind: string;
  getAsFile(): File | null;
  /** Typed loosely: the DOM lib's `FileSystemEntry` lacks the members
   *  above, which every browser that has the API provides. */
  webkitGetAsEntry?: () => unknown;
}

/**
 * From a drop. Every `webkitGetAsEntry()` is called before the first
 * `await`: the DataTransfer is dead once the drop handler returns. Folders
 * recurse; `readEntries` is looped until it hands back an empty batch,
 * since Chrome returns at most a hundred per call. A browser without the
 * entries API falls back to the flat files.
 */
export async function filesFromDataTransfer(items: ArrayLike<DropItem>): Promise<PickedFile[]> {
  const roots: { entry: Entry | null; file: File | null }[] = [];
  for (const item of Array.from(items)) {
    if (item.kind !== "file") continue;
    roots.push({ entry: (item.webkitGetAsEntry?.() as Entry | null | undefined) ?? null, file: item.getAsFile() });
  }
  const picked: PickedFile[] = [];
  for (const root of roots) {
    if (root.entry) await walk(root.entry, "", picked);
    else if (root.file) {
      const path = normalise(root.file.name);
      if (!isHiddenPath(path)) picked.push({ file: root.file, path });
    }
  }
  return picked;
}

async function walk(entry: Entry, prefix: string, out: PickedFile[]): Promise<void> {
  const path = prefix ? `${prefix}/${entry.name}` : entry.name;
  if (isHiddenPath(path)) return;
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => entry.file(resolve, reject));
    out.push({ file, path });
    return;
  }
  const reader = entry.createReader();
  for (;;) {
    const batch = await new Promise<Entry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (batch.length === 0) break;
    for (const child of batch) await walk(child, path, out);
  }
}

/** A file's bytes as the base64 body of a data URL - what `RawUnitUpload`
 *  and `SampleUpload` carry. */
export function encodeFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const result = String(reader.result);
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
