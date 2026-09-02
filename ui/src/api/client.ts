// A thin, typed fetch wrapper over the JSON API - the client's only read
// path (docs/adr/0002-ui-is-a-react-client.md: "no view reaches SQLite or
// the evidence repo directly; every read goes through the API"). Types come
// from the generated `schema.d.ts`, never hand-written, so a backend field
// rename is a compile error here (ADR-0002's mitigation for a two-language
// stack).
import type { components } from "./schema.d.ts";

export type SourceSummary = components["schemas"]["SourceSummary"];
export type SourceDetail = components["schemas"]["SourceDetail"];
export type SourceListResponse = components["schemas"]["SourceListResponse"];
export type RawSourceResponse = components["schemas"]["RawSourceResponse"];
export type SubjectSummary = components["schemas"]["SubjectSummary"];
export type EntrySummary = components["schemas"]["EntrySummary"];
export type SearchResultOut = components["schemas"]["SearchResultOut"];

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}

// A large-enough page to render the whole corpus in the sidebar tree in one
// call - #24's groups and counts are computed over every record, and the
// PoC has no evidence corpus large enough yet to need real pagination here
// (list_sources still exists, paginated, for callers that do).
const WHOLE_CORPUS_LIMIT = 10_000;

export function listAllSources(): Promise<SourceListResponse> {
  return get(`/api/sources?limit=${WHOLE_CORPUS_LIMIT}`);
}

export function readSource(id: string): Promise<SourceDetail> {
  return get(`/api/sources/${encodeURIComponent(id)}`);
}

export function readRawSource(id: string): Promise<RawSourceResponse> {
  return get(`/api/sources/${encodeURIComponent(id)}/raw`);
}

export function listSubjects(): Promise<{ items: SubjectSummary[] }> {
  return get(`/api/subjects`);
}

export function listEntries(subjectId: string): Promise<{ items: EntrySummary[] }> {
  return get(`/api/subjects/${encodeURIComponent(subjectId)}/entries`);
}

export function search(query: string): Promise<{ results: SearchResultOut[] }> {
  return get(`/api/search?q=${encodeURIComponent(query)}`);
}

export { ApiError };
