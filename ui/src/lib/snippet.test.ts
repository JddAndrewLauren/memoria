import { describe, expect, it } from "vitest";
import { splitSnippet } from "./snippet";

const START = "\x01";
const END = "\x02";

describe("splitSnippet", () => {
  it("splits a snippet with one matched term", () => {
    const parts = splitSnippet(`a ${START}heron${END} flew`);
    expect(parts).toEqual([
      { text: "a ", matched: false },
      { text: "heron", matched: true },
      { text: " flew", matched: false },
    ]);
  });

  it("handles a snippet with no match marks at all", () => {
    expect(splitSnippet("plain text")).toEqual([{ text: "plain text", matched: false }]);
  });

  it("handles more than one matched term", () => {
    const parts = splitSnippet(`${START}Bob${END} saw ${START}Alice${END}`);
    expect(parts.filter((p) => p.matched).map((p) => p.text)).toEqual(["Bob", "Alice"]);
  });

  it("never renders the raw control characters as text", () => {
    const parts = splitSnippet(`x ${START}y${END} z`);
    expect(parts.every((p) => !p.text.includes(START) && !p.text.includes(END))).toBe(true);
  });
});
