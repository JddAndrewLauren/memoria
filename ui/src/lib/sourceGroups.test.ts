import { describe, expect, it } from "vitest";
import { groupSourcesByType } from "./sourceGroups";
import type { SourceSummary } from "../api/client";

function source(overrides: Partial<SourceSummary>): SourceSummary {
  return {
    id: "SRC-000001",
    source_type: "journal",
    recorded_date: "2011-07-17",
    event_date: "2011-07-17",
    date_confidence: "exact",
    contemporaneous: true,
    original_file: "raw/journal.txt",
    original_locator: "Journal I",
    ...overrides,
  };
}

describe("groupSourcesByType", () => {
  it("groups by the source_type values actually present", () => {
    const groups = groupSourcesByType([
      source({ id: "SRC-000001", source_type: "journal" }),
      source({ id: "SRC-000002", source_type: "letter" }),
      source({ id: "SRC-000003", source_type: "journal" }),
    ]);

    expect(groups).toEqual([
      { sourceType: "journal", sources: [expect.objectContaining({ id: "SRC-000001" }), expect.objectContaining({ id: "SRC-000003" })] },
      { sourceType: "letter", sources: [expect.objectContaining({ id: "SRC-000002" })] },
    ]);
  });

  it("never invents a group with no records behind it", () => {
    expect(groupSourcesByType([])).toEqual([]);
  });

  it("excludes editorial records - they are not browsable in SOURCES", () => {
    const groups = groupSourcesByType([
      source({ id: "SRC-000001", source_type: "journal" }),
      source({ id: "SRC-000002", source_type: "editorial" }),
    ]);

    expect(groups.map((g) => g.sourceType)).toEqual(["journal"]);
  });

  it("computes each group's count from its own records, never a stub", () => {
    const groups = groupSourcesByType([
      source({ id: "SRC-000001", source_type: "letter" }),
      source({ id: "SRC-000002", source_type: "letter" }),
      source({ id: "SRC-000003", source_type: "letter" }),
    ]);

    expect(groups[0].sources).toHaveLength(3);
  });
});
