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
export type SearchResultOut = components["schemas"]["SearchResultOut"];
export type SubjectListResponse = components["schemas"]["SubjectListResponse"];
export type EntryListResponse = components["schemas"]["EntryListResponse"];
export type SearchResponse = components["schemas"]["SearchResponse"];
export type EditorialRecordOut = components["schemas"]["EditorialRecordOut"];
export type ReadOverlayOut = components["schemas"]["ReadOverlayOut"];
export type CitationOut = components["schemas"]["CitationOut"];
export type StatementOut = components["schemas"]["StatementOut"];
export type OverlayActOut = components["schemas"]["OverlayActOut"];
export type EntryDetail = components["schemas"]["EntryDetail"];
export type GatheredSourceOut = components["schemas"]["GatheredSourceOut"];
export type GatheredSetResponse = components["schemas"]["GatheredSetResponse"];
export type AppearanceOut = components["schemas"]["AppearanceOut"];
export type AppearancesResponse = components["schemas"]["AppearancesResponse"];
export type MatchTermsResponse = components["schemas"]["MatchTermsResponse"];
export type ManuscriptOutline = components["schemas"]["ManuscriptOutline"];
export type OutlineChapterOut = components["schemas"]["OutlineChapterOut"];
export type OutlineSectionOut = components["schemas"]["OutlineSectionOut"];
export type SectionView = components["schemas"]["SectionView"];
export type SectionParagraphOut = components["schemas"]["SectionParagraphOut"];
export type NotCurrentOut = components["schemas"]["NotCurrentOut"];
export type ScopeEntryOut = components["schemas"]["ScopeEntryOut"];
export type DecisionOut = components["schemas"]["DecisionOut"];
export type QuestionOut = components["schemas"]["QuestionOut"];
export type ReviewOut = components["schemas"]["ReviewOut"];
export type FindingOut = components["schemas"]["FindingOut"];
export type DisagreementMemberOut = components["schemas"]["DisagreementMemberOut"];
export type RewriteResponse = components["schemas"]["RewriteResponse"];
export type SettleRequest = components["schemas"]["SettleRequest"];
export type SettlementOut = components["schemas"]["SettlementOut"];
export type SuppliedContextOut = components["schemas"]["SuppliedContextOut"];
export type SessionSuppliedContextOut = components["schemas"]["SessionSuppliedContextOut"];
export type AssembledEntryOut = components["schemas"]["AssembledEntryOut"];
export type FallbackOut = components["schemas"]["FallbackOut"];
export type ServedSinceOut = components["schemas"]["ServedSinceOut"];
export type IngestionStatusOut = components["schemas"]["IngestionStatusOut"];
export type UnitStatusOut = components["schemas"]["UnitStatusOut"];
export type IngestionRunOut = components["schemas"]["IngestionRunOut"];

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

async function post<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    path,
    body === undefined
      ? { method: "POST" }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}

// The first request in this client that carries a body: #26's match-term
// write. `ApiError.status` matters more here than anywhere else - 409 is
// the staleness rejection (ADR-0003), and the editor tells it apart from a
// failure by that number.
async function put<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new ApiError(response.status, failure?.detail ?? response.statusText);
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

// The entry view's three reads (#26). `readEntry` is the parsed read - the
// statements and match terms the entry view wants - and not the raw file
// `readRef` serves for the citation panel's SUB-x/y backlinks (#148). Three
// rather than one: the entry is a
// read of its *file*, while the gathered set and appearances are index reads
// with their own build signal - and part 06 §8.11 keeps the last two apart
// on purpose, since one is evidence to write from and the other is prose
// already written.
function entryPath(subjectId: string, entrySlug: string): string {
  return `/api/subjects/${encodeURIComponent(subjectId)}/entries/${encodeURIComponent(entrySlug)}`;
}

export function readEntry(subjectId: string, entrySlug: string): Promise<EntryDetail> {
  return get(entryPath(subjectId, entrySlug));
}

export function readGatheredSet(
  subjectId: string,
  entrySlug: string,
): Promise<GatheredSetResponse> {
  return get(`${entryPath(subjectId, entrySlug)}/gathered`);
}

export function readAppearances(
  subjectId: string,
  entrySlug: string,
): Promise<AppearancesResponse> {
  return get(`${entryPath(subjectId, entrySlug)}/appearances`);
}

// The author editing match terms - the one write this surface makes (#26).
// `token` is whatever `readEntry` served, passed back unread: it is the
// staleness check's whole client-side half (ADR-0003).
export function updateMatchTerms(
  subjectId: string,
  entrySlug: string,
  token: string,
  matchTerms: string[],
): Promise<MatchTermsResponse> {
  return put(`${entryPath(subjectId, entrySlug)}/match-terms`, {
    token,
    match_terms: matchTerms,
  });
}

// The manuscript (#43): the outline for the MANUSCRIPT tree, the Section
// view, and the Review surface - three reads - plus the surface's one
// write, the author applying a proposed rewrite to one paragraph. Nothing
// here can run an audit: Review is a read over the verdicts a session
// already recorded, and there is no request in this client that records
// one. `token` on the rewrite is what `readReview` served, passed back
// unread (ADR-0003), the same staleness check `updateMatchTerms` makes.
export function readManuscript(): Promise<ManuscriptOutline> {
  return get(`/api/manuscript`);
}

export function readSection(sectionId: string): Promise<SectionView> {
  return get(`/api/sections/${encodeURIComponent(sectionId)}`);
}

export function readReview(sectionId: string): Promise<ReviewOut> {
  return get(`/api/sections/${encodeURIComponent(sectionId)}/review`);
}

// The supplied-context surface (#61, ADR-0001): what Memoria supplied to
// each session that assembled this section - the working context assembly
// produced, and every read served since - in countable domain units. The
// page re-reads this while it is open and never while it is closed; there
// is no count on the opener and no figure in the response to put on one.
export function readSuppliedContext(sectionId: string): Promise<SuppliedContextOut> {
  return get(`/api/sections/${encodeURIComponent(sectionId)}/supplied-context`);
}

export function applyRewrite(
  sectionId: string,
  paragraphIndex: number,
  token: string,
  text: string,
): Promise<RewriteResponse> {
  return put(
    `/api/sections/${encodeURIComponent(sectionId)}/paragraphs/${paragraphIndex}`,
    { token, text },
  );
}

// Settling a finding from Review (#33, walked by #45): the author's other
// explicit act on that surface. It lands on the entry the finding names,
// so the token presented back is the entry's - `FindingOut.entry_token`,
// served with the review - and a 409 means the entry moved underneath.
export function settleFinding(sectionId: string, request: SettleRequest): Promise<SettlementOut> {
  return post(`/api/sections/${encodeURIComponent(sectionId)}/settlements`, request);
}

// The ingestion status: every raw unit in the ledger with its conversion,
// index and extraction state, derived on the server from the ledger, the
// records and the index (part 05 §5.4: "the record is the state"). Read by
// the `/ingestion` page, the SOURCES tree's glyphs and the source viewer's
// badge - one query, joined by id on the client.
export function readIngestionStatus(): Promise<IngestionStatusOut> {
  return get(`/api/ingestion`);
}

// The two model-free passes the author may launch from the page
// (ADR-0009). Only ever called when `checkLocality` has said `is_local` -
// the server refuses either way, and the buttons that reach these are
// absent, not disabled, otherwise. A 409 is another pass still running.
export function runNormalize(): Promise<IngestionRunOut> {
  return post(`/api/ingestion/normalize`);
}

export function runRebuild(): Promise<IngestionRunOut> {
  return post(`/api/ingestion/rebuild`);
}

export function search(query: string): Promise<SearchResponse> {
  return get(`/api/search?q=${encodeURIComponent(query)}`);
}

export { ApiError };
