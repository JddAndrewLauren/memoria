import { describe, expect, it } from "vitest";
import { wordDiff } from "./wordDiff";

describe("wordDiff", () => {
  it("keeps unchanged words and marks the changed ones", () => {
    const ops = wordDiff("He came back on July 15.", "He came back on July 18.");
    expect(ops).toEqual([
      { kind: "same", text: "He came back on July " },
      { kind: "removed", text: "15." },
      { kind: "added", text: "18." },
    ]);
  });

  it("is lossless in both directions", () => {
    const before = "Bob knew by then.  Or so the draft says.";
    const after = "Bob probably knew by the eighteenth.";
    const ops = wordDiff(before, after);
    expect(ops.filter((op) => op.kind !== "added").map((op) => op.text).join("")).toBe(before);
    expect(ops.filter((op) => op.kind !== "removed").map((op) => op.text).join("")).toBe(after);
  });

  it("reports identical text as one unchanged run and empty text as nothing", () => {
    expect(wordDiff("same words", "same words")).toEqual([{ kind: "same", text: "same words" }]);
    expect(wordDiff("", "")).toEqual([]);
    expect(wordDiff("", "new")).toEqual([{ kind: "added", text: "new" }]);
  });
});
