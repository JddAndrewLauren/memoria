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
export type LocalityOut = components["schemas"]["LocalityOut"];
export type RevealSourceResponse = components["schemas"]["RevealSourceResponse"];
export type SubjectSummary = components["schemas"]["SubjectSummary"];
export type EntrySummary = components["schemas"]["EntrySummary"];
export type EntryDetail = components["schemas"]["EntryDetail"];
export type StatementOut = components["schemas"]["StatementOut"];
export type SearchResultOut = components["schemas"]["SearchResultOut"];
export type SubjectListResponse = components["schemas"]["SubjectListResponse"];
export type EntryListResponse = components["schemas"]["EntryListResponse"];
export type SearchResponse = components["schemas"]["SearchResponse"];
export type EditorialRecordOut = components["schemas"]["EditorialRecordOut"];
export type ReadOverlayOut = components["schemas"]["ReadOverlayOut"];
export type CitationOut = components["schemas"]["CitationOut"];

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

async function post<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: "POST" });
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

// Whether this browser and the API server are on the same machine - the
// one fact "Reveal in editor" (#65) needs to decide whether to render its
// button at all. General on purpose (docs/adr/0002-ui-is-a-react-client.md:
// "no other surface may acquire a client-locality condition" of its own).
export function checkLocality(): Promise<LocalityOut> {
  return get(`/api/locality`);
}

// "Reveal in editor" (#65): ask the server to launch the raw evidence file
// in the host's editor or file manager. Only ever called when
// `checkLocality` has said `is_local` - the server refuses it either way,
// but the button that reaches this is absent, not disabled, otherwise.
export function revealSource(id: string): Promise<RevealSourceResponse> {
  return post(`/api/sources/${encodeURIComponent(id)}/reveal`);
}

// The slide-over citation panel's one read, in both directions (#25,
// §19.9): a SRC- paragraph anchor or a SUB-x/y entry reference, either way
// through the same generic `/api/read`.
export function readRef(ref: string): Promise<CitationOut> {
  return get(`/api/read?ref=${encodeURIComponent(ref)}`);
}

export function listSubjects(): Promise<SubjectListResponse> {
  return get(`/api/subjects`);
}

export function listEntries(subjectId: string): Promise<EntryListResponse> {
  return get(`/api/subjects/${encodeURIComponent(subjectId)}/entries`);
}

// The `SUBJECTS` tree's own entry read (#148) - parsed statements, not the
// raw file `readRef` serves for the citation panel's SUB-x/y backlinks.
export function readEntry(subjectId: string, entrySlug: string): Promise<EntryDetail> {
  return get(
    `/api/subjects/${encodeURIComponent(subjectId)}/entries/${encodeURIComponent(entrySlug)}`,
  );
}

export function search(query: string): Promise<SearchResponse> {
  return get(`/api/search?q=${encodeURIComponent(query)}`);
}

export { ApiError };
