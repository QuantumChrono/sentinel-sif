"""FROZEN request/response contract for all 7 endpoints in `PRD.md` § Backend API.

READ THIS BEFORE CHANGING ANYTHING HERE. Four people build against this file in parallel for
three days. Every field name, type and nullability below is permanent; changing one silently
breaks the frontend, the analytics lane and the review lane at once. It requires the
integrator's sign-off plus a `DECISIONS.md` entry (`STAGES.md` § FROZEN files).

FIELD NAMES ARE THE DATABASE COLUMN NAMES, EXACTLY. `report_id` is never `reportId`,
`span_start` is never `start`. The boundary renames nothing, so any field in a JSON response
traces to a column in `schema.sql` by eye, with no mapping table in between.

WHAT THE SPANS INDEX. `span_start` / `span_end` are offsets into `cleaned_text`, never into
`raw_text`. Inference runs on the cleaned string, so that is the only string the offsets are
valid against, and it is the string the Report Detail view highlights. When preprocessing
degrades, `cleaned_text` holds the original text, so the offsets stay valid on that path too.

WHY `rule_name` IS `str` AND NOT A 9-VALUE `Literal`. A `Literal` would reject an unknown rule
at serialization time - i.e. as an HTTP 500 mid-demo, which `PRD.md` § Edge cases forbids. The
canonical 9 are enforced where they are produced (`inference/iogp_tagger.py`) and listed here
as data so `/analytics/rules` can return all 9 even against an empty database.
"""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# The canonical 9 IOGP Life-Saving Rules, verbatim from `PRD.md` § Glossary, which says do not
# rename or merge them. Order is PRD order, and is the display order of the dashboard chart.
IOGP_RULE_NAMES = (
    "Bypassing Safety Controls", "Confined Space", "Driving", "Energy Isolation", "Hot Work",
    "Line of Fire", "Safe Mechanical Lifting", "Work Authorisation", "Working at Height",
)

# Below this classifier confidence a report routes to the Manual Review Queue instead of being
# auto-published (`PRD.md` § ML pipeline detail). It lives in this frozen file because two
# lanes read it - `routes/reports.py` applies it on write, `routes/analytics.py` selects the
# queue by it - and two hardcoded copies would drift apart the day it is tuned.
CONFIDENCE_THRESHOLD = 0.65

MAX_REPORT_CHARS = 20_000

# U+0000, which a Postgres `text` column cannot store: it fails the insert as `22P05`
# ("unsupported Unicode escape sequence, U+0000 cannot be converted to text"), and nothing
# in `routes/reports.py` catches that, so it surfaced as a raw HTTP 500. It reaches us only as
# a JSON escape, which the server's own parser turns into a character no client could encode.
# See `ReportCreate.strip_nul_bytes` and `AUDIT.md` 2026-08-26.
#
# THE OTHER UNSTORABLE CLASS IS DELIBERATELY NOT HANDLED HERE. A lone surrogate never reaches
# a field validator at all - Pydantic rejects it while parsing the JSON string - so stripping
# it here would be dead code. It crashed one layer further out, in FastAPI's own 422 handler,
# and is fixed there (`main.py`, `validation_error_handler`).
NUL_BYTE = re.compile("\x00")

ReportStatus = Literal["processed", "processing_failed", "needs_review"]
ReviewStatus = Literal["auto", "confirmed", "overridden"]
EntityType = Literal["activity", "location", "equipment", "barrier_failure"]
ReporterRole = Literal["hse_manager", "site_supervisor", "admin"]


# --- requests --------------------------------------------------------------------------

class ReportCreate(BaseModel):
    """POST /api/v1/reports. `submitted_at` and `status` are server-set, never client-set."""

    site_id: UUID
    raw_text: str = Field(min_length=1, max_length=MAX_REPORT_CHARS)
    reporter_role: ReporterRole

    @field_validator("raw_text")
    @classmethod
    def strip_nul_bytes(cls, value: str) -> str:
        """Remove U+0000, which a Postgres `text` column cannot store.

        NOT hypothetical and not a style rule: before this existed, a report containing
        U+0000 returned a raw `HTTP 500 Internal Server Error` with a `text/plain` body from
        the running API. `PRD.md` § Edge cases forbids that twice over - adversarial input
        must not crash the pipeline, and a live demo must never see a raw 500. Found by
        `scripts/check_edge_cases.py` against the real system, not reasoned about
        (`AUDIT.md` 2026-08-26).

        The character survives preprocessing and all three inference heads untouched;
        Postgres is what rejects it, as `22P05`. `routes/reports.py` catches only `APIError`
        code `23503`, so it escaped as a bare 500.

        STRIPPED RATHER THAN REJECTED because § Edge cases says adversarial input earns a low
        confidence, not a refusal, and U+0000 is invisible to whoever typed the report - a 422
        would reject a genuine hazard report over a character its author cannot see. Every
        text column derives from this one field (`cleaned_text` from it, `entity_text` sliced
        out of that), so this single guard is what keeps all three storable.

        Runs BEFORE `reject_blank_text` - validators fire in definition order - so text made
        only of these collapses to empty here and is rejected as blank below, rather than
        passing `min_length` on characters that cannot be stored.
        """
        return NUL_BYTE.sub("", value)

    @field_validator("raw_text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """`PRD.md` § Edge cases requires empty input to be rejected at the API layer with a
        validation message. Doing it here means a whitespace-only submission returns a 422
        naming the field, instead of reaching the models and looking like a low-confidence
        verdict on nothing.
        """
        if not value.strip():
            raise ValueError("report text is empty or whitespace only")
        return value


class ReviewDecision(BaseModel):
    """POST /api/v1/reports/{id}/review - an HSE officer confirming or overriding a verdict.

    `sif_potential` is required on both paths, not only on an override: a confirmation that
    does not restate what is being confirmed is unauditable, and the endpoint would otherwise
    silently accept a stale verdict the officer never actually saw.
    """

    review_status: Literal["confirmed", "overridden"]
    sif_potential: bool
    reviewed_by: UUID


# --- response pieces -------------------------------------------------------------------

class ClassificationOut(BaseModel):
    """One row of `classifications`. `reviewed_by` stays null until a human acts on it."""

    sif_potential: bool
    confidence: float
    model_version: str
    review_status: ReviewStatus
    reviewed_by: UUID | None


class IogpTagOut(BaseModel):
    """One row of `iogp_tags`. Zero or several per report - the tagger is multi-label."""

    rule_name: str
    confidence: float


class PrecursorOut(BaseModel):
    """One row of `precursors`. Offsets index `cleaned_text` (see the module docstring)."""

    entity_type: EntityType
    entity_text: str
    span_start: int
    span_end: int


class SiteOut(BaseModel):
    """One row of `sites`, embedded so the UI never needs a second call to name a report."""

    id: UUID
    name: str
    region: str
    latitude: float
    longitude: float


# --- report responses ------------------------------------------------------------------

class ReportSummary(BaseModel):
    """A row of GET /api/v1/reports. Carries no precursor spans: the list view highlights
    nothing, and shipping every span for every row would dominate the payload.
    """

    id: UUID
    site: SiteOut | None
    raw_text: str
    language_detected: str
    reporter_role: str
    submitted_at: datetime
    status: ReportStatus
    classification: ClassificationOut | None
    iogp_tags: list[IogpTagOut]


class ReportDetail(BaseModel):
    """GET /api/v1/reports/{id} AND the POST /api/v1/reports response - deliberately one shape,
    so the Intake page's inline result and the Detail page share a single renderer.

    `classification` is null when `status` is `processing_failed`: inference produced no
    verdict, and a zero-confidence placeholder row would be a fabricated one.
    """

    id: UUID
    site: SiteOut | None
    raw_text: str
    cleaned_text: str
    language_detected: str
    reporter_role: str
    submitted_at: datetime
    status: ReportStatus
    classification: ClassificationOut | None
    iogp_tags: list[IogpTagOut]
    precursors: list[PrecursorOut]


class ProcessingFailure(BaseModel):
    """Body of the 502 from POST /api/v1/reports when inference fails.

    Structured on purpose: `PRD.md` § Edge cases requires a retry action in the UI rather than
    a stack trace, and retrying needs the id of the row already written as `processing_failed`.
    `detail` names the failing stage; it never carries a traceback.
    """

    report_id: UUID
    status: ReportStatus
    detail: str


# --- analytics responses ---------------------------------------------------------------

class DensityRow(BaseModel):
    """One ranked row of GET /api/v1/analytics/density.

    A RATE, not a count: `sif_rate` is SIF-potential reports over total reports for the group.
    `rank_score` is the Wilson lower bound the ordering actually uses, so a 1-of-1 group cannot
    outrank 24-of-40. Both are returned because the table must show the honest fraction while
    sorting on the defensible number. See `analytics/density.py` for the arithmetic.
    """

    group_type: Literal["site", "activity"]
    group_name: str
    region: str | None
    total_reports: int
    sif_reports: int
    sif_rate: float
    rank_score: float


class DensityResponse(BaseModel):
    """Both rankings in one payload - the density table renders them side by side."""

    by_site: list[DensityRow]
    by_activity: list[DensityRow]


class RuleCount(BaseModel):
    """One bar of GET /api/v1/analytics/rules. All 9 are always present, zeros included."""

    rule_name: str
    report_count: int


class ReviewQueueRow(BaseModel):
    """One row of GET /api/v1/analytics/review-queue: below threshold, awaiting a human call."""

    id: UUID
    site_name: str | None
    raw_text: str
    submitted_at: datetime
    sif_potential: bool
    confidence: float
