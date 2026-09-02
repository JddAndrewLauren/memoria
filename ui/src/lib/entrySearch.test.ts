import { describe, expect, it } from "vitest";
import { searchEntries } from "./entrySearch";
import type { EntrySummary } from "../api/client";

const bob: EntrySummary = { id: "SUB-people/bob", match_terms: ["Bob", "Robert", "my brother-in-law"] };
const alice: EntrySummary = { id: "SUB-people/alice", match_terms: ["Alice"] };

describe("searchEntries", () => {
  it("matches on the entry's own slug", () => {
    const hits = searchEntries("SUB-people", [bob, alice], "bob");
    expect(hits.map((h) => h.entry.id)).toEqual(["SUB-people/bob"]);
  });

  it("matches on a match term the slug does not carry", () => {
    const hits = searchEntries("SUB-people", [bob, alice], "brother-in-law");
    expect(hits.map((h) => h.entry.id)).toEqual(["SUB-people/bob"]);
    expect(hits[0].matchedOn).toBe("my brother-in-law");
  });

  it("is case-insensitive", () => {
    expect(searchEntries("SUB-people", [alice], "ALICE")).toHaveLength(1);
  });

  it("returns nothing for a blank query", () => {
    expect(searchEntries("SUB-people", [bob, alice], "   ")).toEqual([]);
  });
});
