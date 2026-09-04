import { describe, expect, it } from "vitest";
import { drawState, extractedLabel, indexByUnitId } from "./ingestion";
import type { IngestionStatusOut, UnitStatusOut } from "../api/client";

function unit(overrides: Partial<UnitStatusOut>): UnitStatusOut {
  return {
    id: "SRC-000001",
    path: "raw/one.txt",
    deleted: false,
    converted: "current",
    failure_reason: null,
    record_paragraphs: 4,
    indexed_paragraphs: 4,
    extracted_paragraphs: 1,
    email_message_index: null,
    ...overrides,
  };
}

describe("drawState", () => {
  it("draws every state the server names with a distinct glyph and an author-facing label", () => {
    const states = [
      "current",
      "out_of_date",
      "not_yet_converted",
      "failed",
      "unconvertible",
      "container",
      "stub",
      "deleted",
    ];
    const glyphs = new Set(states.map((state) => drawState(state).glyph));
    expect(glyphs.size).toBe(states.length);
    // The glossary's reserved words never appear as labels here.
    for (const state of states) {
      expect(drawState(state).label).not.toMatch(/stale|pending|dirty/);
    }
    expect(drawState("failed").tone).toBe("red");
    expect(drawState("out_of_date").label).toBe("out of date");
  });

  it("renders a state it has no drawing for as itself rather than dropping it", () => {
    expect(drawState("some_new_state")).toEqual({
      glyph: "?",
      tone: "neutral",
      label: "some new state",
    });
  });
});

describe("indexByUnitId", () => {
  it("joins by id and is empty for an unchecked or absent status", () => {
    const status: IngestionStatusOut = {
      units: [unit({ id: "SRC-000001" }), unit({ id: "SRC-000002", converted: "failed" })],
      counts: {},
      unnumbered: [],
      is_normalized: true,
      is_indexed: true,
      generated_at: "2026-09-03T00:00:00+00:00",
    };
    expect(indexByUnitId(status).get("SRC-000002")?.converted).toBe("failed");
    expect(indexByUnitId({ ...status, units: null }).size).toBe(0);
    expect(indexByUnitId(undefined).size).toBe(0);
  });
});

describe("extractedLabel", () => {
  it("is 'n of m' for a record and absent for a unit with none", () => {
    expect(extractedLabel(unit({ extracted_paragraphs: 1, record_paragraphs: 4 }))).toBe("1 of 4");
    expect(
      extractedLabel(unit({ record_paragraphs: null, extracted_paragraphs: null })),
    ).toBeNull();
  });
});
