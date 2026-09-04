// The archive as a folder tree: every file under `raw/`, numbered by the
// ledger or not, joined to its units. Pure, so the shape is testable
// without a render - and pruned by a filter the same way, so the page
// shows one tree whether or not the author is searching it.
import type { IngestionStatusOut, UnitStatusOut } from "../api/client";

export interface RawFile {
  kind: "file";
  name: string;
  /** Ledger-relative, `raw/...`. */
  path: string;
  /** The ledger's rows for this file - none while it waits for a normalize;
   *  several for an email export, one per message plus the container. */
  units: UnitStatusOut[];
}

export interface RawFolder {
  kind: "folder";
  name: string;
  path: string;
  children: (RawFolder | RawFile)[];
  /** Files below, at any depth, and how many of them the ledger has not numbered. */
  files: number;
  waiting: number;
}

export type RawNode = RawFolder | RawFile;

export function buildRawTree(status: IngestionStatusOut): RawFolder {
  const byPath = new Map<string, UnitStatusOut[]>();
  for (const unit of status.units ?? []) {
    if (unit.deleted) continue;
    const list = byPath.get(unit.path) ?? [];
    list.push(unit);
    byPath.set(unit.path, list);
  }
  for (const path of status.unnumbered ?? []) if (!byPath.has(path)) byPath.set(path, []);

  const root: RawFolder = { kind: "folder", name: "raw", path: "raw", children: [], files: 0, waiting: 0 };
  const folders = new Map<string, RawFolder>([["raw", root]]);
  const folderAt = (path: string): RawFolder => {
    const known = folders.get(path);
    if (known) return known;
    const slash = path.lastIndexOf("/");
    const parent = folderAt(path.slice(0, slash));
    const made: RawFolder = { kind: "folder", name: path.slice(slash + 1), path, children: [], files: 0, waiting: 0 };
    parent.children.push(made);
    folders.set(path, made);
    return made;
  };
  for (const [path, units] of byPath) {
    const slash = path.lastIndexOf("/");
    folderAt(path.slice(0, slash)).children.push({ kind: "file", name: path.slice(slash + 1), path, units });
  }
  finish(root);
  return root;
}

// Folders first, then files, each by name; the counts rolled up.
function finish(folder: RawFolder): void {
  folder.children.sort((a, b) =>
    a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "folder" ? -1 : 1,
  );
  for (const child of folder.children) {
    if (child.kind === "folder") {
      finish(child);
      folder.files += child.files;
      folder.waiting += child.waiting;
    } else {
      folder.files += 1;
      if (child.units.length === 0) folder.waiting += 1;
    }
  }
}

/** The tree with only the files whose path contains `needle` (case-folded),
 *  and only the folders that still hold one; `null` when nothing matches. */
export function pruneRawTree(folder: RawFolder, needle: string): RawFolder | null {
  const lower = needle.trim().toLowerCase();
  if (!lower) return folder;
  const kept: RawNode[] = [];
  for (const child of folder.children) {
    if (child.kind === "folder") {
      const sub = pruneRawTree(child, lower);
      if (sub) kept.push(sub);
    } else if (child.path.toLowerCase().includes(lower)) {
      kept.push(child);
    }
  }
  if (kept.length === 0) return null;
  const pruned: RawFolder = { ...folder, children: kept, files: 0, waiting: 0 };
  for (const child of kept) {
    if (child.kind === "folder") {
      pruned.files += child.files;
      pruned.waiting += child.waiting;
    } else {
      pruned.files += 1;
      if (child.units.length === 0) pruned.waiting += 1;
    }
  }
  return pruned;
}
