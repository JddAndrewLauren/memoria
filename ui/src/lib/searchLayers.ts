import type { SearchResultOut } from "../api/client";
import { EDITORIAL_SOURCE_TYPE } from "./sourceGroups";

export interface SplitSearchResults {
  evidence: SearchResultOut[];
  editorial: SearchResultOut[];
}

/**
 * Splits `/api/search`'s hits into the evidence layer and the editorial
 * layer. Cross-layer search defaults to evidence only; editorial voice is
 * shown only once the caller asks for it, and stays a visibly distinct
 * group rather than being merged in unmarked (#24's acceptance criteria).
 */
export function splitSearchResultsByLayer(results: SearchResultOut[]): SplitSearchResults {
  const evidence: SearchResultOut[] = [];
  const editorial: SearchResultOut[] = [];
  for (const result of results) {
    (result.source_type === EDITORIAL_SOURCE_TYPE ? editorial : evidence).push(result);
  }
  return { evidence, editorial };
}
