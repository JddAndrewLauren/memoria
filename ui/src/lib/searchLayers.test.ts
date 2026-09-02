import { describe, expect, it } from "vitest";
import { splitSearchResultsByLayer } from "./searchLayers";
import type { SearchResultOut } from "../api/client";

function hit(overrides: Partial<SearchResultOut>): SearchResultOut {
  return {
    src_id: "SRC-000001",
    anchor: "src-000001-p1",
    source_type: "journal",
    snippet: "a heron flew",
    ...overrides,
  };
}

describe("splitSearchResultsByLayer", () => {
  it("puts editorial hits in their own layer, never mixed into evidence", () => {
    const { evidence, editorial } = splitSearchResultsByLayer([
      hit({ src_id: "SRC-000001", source_type: "journal" }),
      hit({ src_id: "SRC-000002", source_type: "editorial" }),
    ]);

    expect(evidence.map((r) => r.src_id)).toEqual(["SRC-000001"]);
    expect(editorial.map((r) => r.src_id)).toEqual(["SRC-000002"]);
  });

  it("is empty in both layers for no hits", () => {
    expect(splitSearchResultsByLayer([])).toEqual({ evidence: [], editorial: [] });
  });
});
