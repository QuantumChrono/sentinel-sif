/**
 * The ONLY place in `frontend/` that makes an HTTP call to the FastAPI backend.
 *
 * FROZEN (`STAGES.md` § FROZEN files). Four lanes build against this file for three days.
 *
 * NO COMPONENT MAY CALL `fetch()` DIRECTLY. That is not a style preference: four pages written
 * by four people against a raw `fetch` grow four different error-handling conventions, and the
 * one a judge sees is whichever page throws an unhandled promise rejection on stage. Every
 * function below returns `ApiResult` - data or a structured error - and none of them ever throw,
 * so a component's failure path is a branch, never a try/catch it forgot to write.
 *
 * THE TYPES BELOW MIRROR `backend/schemas.py` FIELD FOR FIELD, INCLUDING THE NAMES. `report_id`
 * is never `reportId` and `span_start` is never `start`. The boundary renames nothing, so any
 * field here traces to a Pydantic field there - and to a column in `schema.sql` - by eye.
 * Python `UUID` and `datetime` both arrive as JSON strings; that is the only mapping.
 */

// --- literal unions (Python `Literal` aliases) -----------------------------------------

export type ReportStatus = "processed" | "processing_failed" | "needs_review";
export type ReviewStatus = "auto" | "confirmed" | "overridden";
export type EntityType = "activity" | "location" | "equipment" | "barrier_failure";
export type ReporterRole = "hse_manager" | "site_supervisor" | "admin";

/** Below this classifier confidence a report routes to the review queue. Mirrors the frozen
 * `CONFIDENCE_THRESHOLD` in `backend/schemas.py`; the backend applies it, the UI only explains
 * it, so this copy is read-only and must never become a second place the rule is decided. */
export const CONFIDENCE_THRESHOLD = 0.65;

export const MAX_REPORT_CHARS = 20_000;

/** The canonical 9 IOGP Life-Saving Rules in `PRD.md` § Glossary order, which is the display
 * order. Mirrors `IOGP_RULE_NAMES` in `backend/schemas.py`. */
export const IOGP_RULE_NAMES = [
  "Bypassing Safety Controls", "Confined Space", "Driving", "Energy Isolation", "Hot Work",
  "Line of Fire", "Safe Mechanical Lifting", "Work Authorisation", "Working at Height",
] as const;

// --- response pieces ------------------------------------------------------------------

export interface SiteOut {
  id: string;
  name: string;
  region: string;
  latitude: number;
  longitude: number;
}

export interface ClassificationOut {
  sif_potential: boolean;
  confidence: number;
  model_version: string;
  review_status: ReviewStatus;
  reviewed_by: string | null;
}

export interface IogpTagOut {
  rule_name: string;
  confidence: number;
}

/** Offsets index `cleaned_text`, NEVER `raw_text` (`backend/schemas.py` module docstring). */
export interface PrecursorOut {
  entity_type: EntityType;
  entity_text: string;
  span_start: number;
  span_end: number;
}

// --- report responses -----------------------------------------------------------------

export interface ReportSummary {
  id: string;
  site: SiteOut | null;
  raw_text: string;
  language_detected: string;
  reporter_role: string;
  submitted_at: string;
  status: ReportStatus;
  classification: ClassificationOut | null;
  iogp_tags: IogpTagOut[];
}

/** `GET /api/v1/reports/{id}` AND the `POST /api/v1/reports` response - one shape on purpose.
 * `classification` is null when `status` is `processing_failed`: no verdict was produced. */
export interface ReportDetail extends ReportSummary {
  cleaned_text: string;
  precursors: PrecursorOut[];
}

/** Body of the 502 from `POST /api/v1/reports`. Carries the id of the row already written as
 * `processing_failed`, which is what a retry action needs. `detail` names the failing stage. */
export interface ProcessingFailure {
  report_id: string;
  status: ReportStatus;
  detail: string;
}

// --- analytics responses --------------------------------------------------------------

export interface DensityRow {
  group_type: "site" | "activity";
  group_name: string;
  group_id: string | null;
  region: string | null;
  total_reports: number;
  sif_reports: number;
  sif_rate: number;
  rank_score: number;
}

export interface DensityResponse {
  by_site: DensityRow[];
  by_activity: DensityRow[];
}

export interface RuleCount {
  rule_name: string;
  report_count: number;
}

export interface ReviewQueueRow {
  id: string;
  site_name: string | null;
  raw_text: string;
  submitted_at: string;
  sif_potential: boolean;
  confidence: number;
}

// --- requests -------------------------------------------------------------------------

export interface ReportCreate {
  site_id: string;
  raw_text: string;
  reporter_role: ReporterRole;
}

export interface ReviewDecision {
  review_status: "confirmed" | "overridden";
  sif_potential: boolean;
  reviewed_by: string;
}

// --- the result contract --------------------------------------------------------------

/** Why the call failed, as a value a component can branch on.
 *
 * `kind` exists so a page never parses a message string to decide what to render. The three the
 * Intake page needs are distinct on purpose: `validation` is the user's text to fix,
 * `processing_failed` is a retry, and `network` is neither. */
export type ApiErrorKind =
  | "validation"          // 422 - the request was rejected, `message` names what to fix
  | "not_found"           // 404
  | "processing_failed"   // 502 from ingest - inference failed, `failure` carries the retry id
  | "network"             // never reached the server, or timed out
  | "server";             // reached it and it broke - a 500 becomes this, never a raw throw

export interface ApiError {
  kind: ApiErrorKind;
  /** Safe to show a user. Never a traceback: a 500 body is discarded in favour of a fixed
   * sentence, because `PRD.md` § Edge cases forbids a stack trace reaching the screen. */
  message: string;
  status: number | null;
  /** Present only when `kind` is `processing_failed` - the `processing_failed` report row to
   * retry against. */
  failure?: ProcessingFailure;
}

/** Data or an error, never both, never a throw. Check `ok` before reading `data`; TypeScript
 * will not let a component skip that check. */
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

/** Ingest runs all three model heads synchronously, so it is the slowest call by design.
 * `PRD.md` § Non-functional requirements targets under 3s end to end; 20s is a hang, and a
 * hang with no timeout leaves the submit button spinning with nothing to report. */
const TIMEOUT_MS = 20_000;

/** FastAPI's 422 `detail` is a list of `{loc, msg}`; `HTTPException` raises it as a plain string,
 * and the 502 raises it as a `ProcessingFailure` object. All three shapes arrive on the same key,
 * so this reads whichever one came back rather than assuming the list. */
function validationMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
      .filter(Boolean);
    if (parts.length > 0) return parts.join("; ");
  }
  return "The report was rejected as invalid.";
}

/** Every call in this file goes through here. One place decides what an HTTP status means, so
 * eight endpoints cannot disagree about it. */
async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  if (!BASE_URL) {
    return { ok: false, error: { kind: "network", status: null,
      message: "The API address is not configured. Set NEXT_PUBLIC_API_BASE_URL." } };
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
  } catch {
    // A DNS failure, a refused connection and the timeout above all land here. The user cannot
    // act on the difference, so they get one honest sentence instead of three.
    return { ok: false, error: { kind: "network", status: null,
      message: "Could not reach the server. Check your connection and try again." } };
  }

  // A 204 or an empty body would make `json()` throw; parsing is guarded so it cannot.
  const body: unknown = await response.json().catch(() => null);

  if (response.ok) return { ok: true, data: body as T };

  const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;

  if (response.status === 422) {
    return { ok: false, error: { kind: "validation", status: 422,
      message: validationMessage(detail) } };
  }
  if (response.status === 404) {
    return { ok: false, error: { kind: "not_found", status: 404,
      message: typeof detail === "string" ? detail : "Not found." } };
  }
  if (response.status === 502 && detail && typeof detail === "object" && "report_id" in detail) {
    const failure = detail as ProcessingFailure;
    return { ok: false, error: { kind: "processing_failed", status: 502, failure,
      message: "Analysis could not be completed for this report." } };
  }
  return { ok: false, error: { kind: "server", status: response.status,
    message: "The server could not complete that request." } };
}

// --- one function per endpoint --------------------------------------------------------

/** `GET /api/v1/sites` - populates the Intake site selector. Empty list on an empty database. */
export function listSites(): Promise<ApiResult<SiteOut[]>> {
  return request<SiteOut[]>("/api/v1/sites");
}

/** `POST /api/v1/reports` - ingest one report and get the full result back in the same response.
 * On inference failure the error is `kind: "processing_failed"` carrying the report id to retry. */
export function createReport(payload: ReportCreate): Promise<ApiResult<ReportDetail>> {
  return request<ReportDetail>("/api/v1/reports", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface ReportFilters {
  site_id?: string;
  activity?: string;
  sif_potential?: boolean;
  iogp_rule?: string;
  review_status?: ReviewStatus;
  submitted_from?: string;
  submitted_to?: string;
  limit?: number;
}

/** `GET /api/v1/reports` - list and filter, newest first. Carries no precursor spans. */
export function listReports(filters: ReportFilters = {}): Promise<ApiResult<ReportDetail[]>> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const suffix = query.toString();
  return request<ReportDetail[]>(`/api/v1/reports${suffix ? `?${suffix}` : ""}`);
}

/** `GET /api/v1/reports/{id}` - what the Magic View renders. Spans index `cleaned_text`. */
export function getReport(reportId: string): Promise<ApiResult<ReportDetail>> {
  return request<ReportDetail>(`/api/v1/reports/${encodeURIComponent(reportId)}`);
}

/** `POST /api/v1/reports/{id}/review` - an officer confirms or overrides the verdict.
 *
 * `reviewed_by` must be a row in the `users` table, not merely a signed-in Supabase auth uid:
 * the column is a foreign key, so an auth user with no `users` row comes back as a 422 reading
 * "reviewed_by is not a known user" (`backend/routes/review.py`). Callers must render that
 * validation message rather than treating a failed review as a saved one. */
export function reviewReport(
  reportId: string,
  decision: ReviewDecision,
): Promise<ApiResult<ClassificationOut>> {
  return request<ClassificationOut>(
    `/api/v1/reports/${encodeURIComponent(reportId)}/review`,
    { method: "POST", body: JSON.stringify(decision) },
  );
}

/** `GET /api/v1/analytics/density` - the site and activity rankings, side by side. */
export function getDensity(): Promise<ApiResult<DensityResponse>> {
  return request<DensityResponse>("/api/v1/analytics/density");
}

/** `GET /api/v1/analytics/rules` - all 9 rules always, zeros included. */
export function getRuleDistribution(): Promise<ApiResult<RuleCount[]>> {
  return request<RuleCount[]>("/api/v1/analytics/rules");
}

/** `GET /api/v1/analytics/review-queue` - below threshold and undecided, least confident first. */
export function getReviewQueue(limit?: number): Promise<ApiResult<ReviewQueueRow[]>> {
  return request<ReviewQueueRow[]>(
    `/api/v1/analytics/review-queue${limit ? `?limit=${limit}` : ""}`,
  );
}
