import { describe, expect, it } from "vitest";
import { buildRawTree, pruneRawTree } from "./rawTree";
import type { IngestionStatusOut, UnitStatusOut } from "../api/client";

function unit(id: string, path: string, overrides: Partial<UnitStatusOut> = {}): UnitStatusOut {
  return {
    id,
    path,
    deleted: false,
    converted: "current",
    failure_reason: null,
    record_paragraphs: 1,
    indexed_paragraphs: null,
    extracted_paragraphs: 0,
    email_message_index: null,
    ...overrides,
  };
}

const STATUS: IngestionStatusOut = {
  units: [
    unit("SRC-000001", "raw/box/two.txt"),
    unit("SRC-000002", "raw/one.txt"),
    unit("SRC-000003", "raw/mail.mbox", { converted: "container", record_paragraphs: null }),
    unit("SRC-000004", "raw/mail.mbox", { email_message_index: 0 }),
    unit("SRC-000005", "raw/gone.txt", { deleted: true, converted: "deleted", record_paragraphs: null }),
  ],
  counts: {},
  unnumbered: ["raw/box/deep/waiting.eml", "raw/loose.eml"],
  is_normalized: true,
  is_indexed: false,
  generated_at: "",
};

describe("the raw tree", () => {
  it("nests every file under its folders, folders first, with counts rolled up", () => {
    const tree = buildRawTree(STATUS);

    expect(tree.children.map((c) => `${c.kind}:${c.name}`)).toEqual([
      "folder:box",
      "file:loose.eml",
      "file:mail.mbox",
      "file:one.txt",
    ]);
    expect(tree.files).toBe(5);
    expect(tree.waiting).toBe(2);
    const box = tree.children[0];
    expect(box.kind === "folder" && box.children.map((c) => c.name)).toEqual(["deep", "two.txt"]);
    expect(box.kind === "folder" && [box.files, box.waiting]).toEqual([2, 1]);
  });

  it("joins a file to every unit at its path, and leaves a deleted unit out", () => {
    const tree = buildRawTree(STATUS);
    const mail = tree.children.find((c) => c.name === "mail.mbox");
    expect(mail?.kind === "file" && mail.units.map((u) => u.id)).toEqual(["SRC-000003", "SRC-000004"]);
    expect(tree.children.some((c) => c.name === "gone.txt")).toBe(false);
  });

  it("prunes to the files whose path matches, keeping only the folders on the way", () => {
    const pruned = pruneRawTree(buildRawTree(STATUS), "WAIT");
    expect(pruned?.files).toBe(1);
    expect(pruned?.children.map((c) => c.name)).toEqual(["box"]);
    const box = pruned?.children[0];
    expect(box?.kind === "folder" && box.children.map((c) => c.name)).toEqual(["deep"]);
    expect(pruneRawTree(buildRawTree(STATUS), "nothing-like-this")).toBeNull();
    expect(pruneRawTree(buildRawTree(STATUS), "  ")?.files).toBe(5);
  });
});
