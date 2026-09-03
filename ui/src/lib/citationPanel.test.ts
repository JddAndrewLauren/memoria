import { describe, expect, it } from "vitest";
import { isTurnRef, sentencesOf } from "./citationPanel";

describe("a transcript turn in the citation panel (#34)", () => {
  it("recognises a turn reference and nothing else", () => {
    expect(isTurnRef("SES-20260912-1432#T017")).toBe(true);
    expect(isTurnRef("ses-20260912-1432-abcdef#t3")).toBe(true);
    expect(isTurnRef("SES-20260912-1432")).toBe(false);
    expect(isTurnRef("src-000184-p17")).toBe(false);
    expect(isTurnRef("SUB-people/bob")).toBe(false);
  });

  it("marks the one sentence the highlight names, whitespace collapsed", () => {
    const turn =
      "I have been going back and forth.  Keep Bob's knowledge\nambiguous until chapter 9. Nothing else changes.";
    const sentences = sentencesOf(turn, "Keep Bob's knowledge ambiguous until chapter 9.");
    expect(sentences.map((s) => s.cited)).toEqual([false, true, false]);
    expect(sentences.map((s) => s.text).join("")).toBe(turn);
  });

  it("marks the sentences a multi-sentence highlight spans as one mark", () => {
    const turn = "First. Second sentence here. Third one. Fourth.";
    const sentences = sentencesOf(turn, "Second sentence here. Third one.");
    expect(sentences.map((s) => s.cited)).toEqual([false, true, false]);
    expect(sentences[1].text.trim()).toBe("Second sentence here. Third one.");
  });

  it("marks nothing when the turn does not contain the highlight", () => {
    const sentences = sentencesOf("One. Two.", "Something the author never said.");
    expect(sentences.every((s) => !s.cited)).toBe(true);
    expect(sentences).toHaveLength(2);
  });

  it("lands on the right sentence past an abbreviation, and marks one that carries one as one mark", () => {
    const turn = "See Mr. Skilling's deck of Jan. 4. That is the fact this chapter turns on.";
    const after = sentencesOf(turn, "That is the fact this chapter turns on.");
    expect(after.filter((s) => s.cited).map((s) => s.text.trim())).toEqual([
      "That is the fact this chapter turns on.",
    ]);
    const within = sentencesOf(turn, "See Mr. Skilling's deck of Jan. 4.");
    expect(within.filter((s) => s.cited).map((s) => s.text.trim())).toEqual([
      "See Mr. Skilling's deck of Jan. 4.",
    ]);
    expect(within.map((s) => s.text).join("")).toBe(turn);
  });
});
