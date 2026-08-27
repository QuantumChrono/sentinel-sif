"""Report ingest, list and detail: `POST/GET /api/v1/reports` and `GET /api/v1/reports/{id}`.

THE INGEST ORDER MATTERS AND IS NOT ARBITRARY. Preprocessing runs first, then all three
inference heads on the CLEANED text, then every row is written, then the full result comes back
in the same response. `PRD.md` § Backend API fixes ingest as synchronous - submit and result in
one request, no job queue - because the Intake page renders the verdict inline and that is the
demo's hero interaction.

WHY INFERENCE RUNS BEFORE THE FIRST INSERT. A failure has to produce a `processing_failed`
report row (`PRD.md` § Edge cases) and the client needs that row's id to offer a retry. Running
inference first means the report is written exactly once, with its final status already known -
no insert-then-update, and no window where a row's status is a lie.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from postgrest.exceptions import APIError

from database import supabase
from inference.iogp_tagger import tag_iogp_rules
from inference.precursor_ner import extract_precursors
from inference.sif_classifier import MODEL_VERSION, classify_sif
from preprocessing import clean_report
from schemas import (CONFIDENCE_THRESHOLD, ClassificationOut, IogpTagOut, PrecursorOut,
                     ProcessingFailure, ReportCreate, ReportDetail, ReportSummary, SiteOut)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

# One embedded select, reused by every read below, so the three endpoints cannot drift into
# returning different shapes for the same report. Supabase resolves the embeds by foreign key.
REPORT_SELECT = (
    "id, site_id, raw_text, cleaned_text, language_detected, reporter_role, submitted_at, "
    "status, sites(id, name, region, latitude, longitude), "
    "classifications(sif_potential, confidence, model_version, review_status, reviewed_by), "
    "iogp_tags(rule_name, confidence), "
    "precursors(entity_type, entity_text, span_start, span_end)"
)


def _site_out(row: dict) -> SiteOut | None:
    """`sites` embeds as a dict, or as None when the report has no site_id."""
    site = row.get("sites")
    return SiteOut(**site) if site else None


def _classification_out(row: dict) -> ClassificationOut | None:
    """`classifications` embeds as a list. Empty on a `processing_failed` report, by design:
    no verdict was produced, and a zero-confidence placeholder would be a fabricated one.
    """
    rows = row.get("classifications") or []
    return ClassificationOut(**rows[0]) if rows else None


def _detail(row: dict) -> ReportDetail:
    return ReportDetail(
        id=row["id"],
        site=_site_out(row),
        raw_text=row["raw_text"],
        cleaned_text=row["cleaned_text"] or "",
        language_detected=row["language_detected"],
        reporter_role=row["reporter_role"],
        submitted_at=row["submitted_at"],
        status=row["status"],
        classification=_classification_out(row),
        iogp_tags=[IogpTagOut(**tag) for tag in row.get("iogp_tags") or []],
        precursors=[PrecursorOut(**span) for span in row.get("precursors") or []],
    )


@router.post("", response_model=ReportDetail, responses={502: {"model": ProcessingFailure}})
def create_report(payload: ReportCreate) -> ReportDetail:
    """Ingest one report: preprocess, run all three heads, write every row, return the result.

    Empty and whitespace-only text never reaches here - `ReportCreate` rejects it as a 422
    naming the field, which is where `PRD.md` § Edge cases requires the rejection to happen.
    """
    cleaned = clean_report(payload.raw_text)
    cleaned_text = cleaned["cleaned_text"]

    report_row = {
        "site_id": str(payload.site_id),
        "raw_text": payload.raw_text,
        "cleaned_text": cleaned_text,
        "language_detected": cleaned["language_detected"],
        "reporter_role": payload.reporter_role,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    # Every inference failure is caught here, at the API layer. A raw 500 with a traceback on a
    # projector is a lost demo, so the report is still written - as `processing_failed`, with a
    # structured body the UI can offer a retry from.
    try:
        sif_potential, confidence = classify_sif(cleaned_text)
        tags = tag_iogp_rules(cleaned_text)
        precursors = extract_precursors(cleaned_text)
    except Exception as error:
        failed = _insert_report({**report_row, "status": "processing_failed"})
        raise HTTPException(status_code=502, detail=ProcessingFailure(
            report_id=failed["id"],
            status="processing_failed",
            detail=f"inference failed: {type(error).__name__}",
        ).model_dump(mode="json")) from error

    # Below the threshold a human decides instead of the model auto-publishing
    # (`PRD.md` § ML pipeline detail).
    status = "processed" if confidence >= CONFIDENCE_THRESHOLD else "needs_review"
    report = _insert_report({**report_row, "status": status})
    report_id = report["id"]

    supabase.table("classifications").insert({
        "report_id": report_id,
        "sif_potential": sif_potential,
        "confidence": confidence,
        "model_version": MODEL_VERSION,
        "review_status": "auto",
        "reviewed_by": None,
    }).execute()

    if tags:
        supabase.table("iogp_tags").insert([
            {"report_id": report_id, "rule_name": name, "confidence": score}
            for name, score in tags
        ]).execute()

    if precursors:
        supabase.table("precursors").insert([
            {"report_id": report_id, "entity_type": entity_type, "entity_text": entity_text,
             "span_start": span_start, "span_end": span_end}
            for entity_type, entity_text, span_start, span_end in precursors
        ]).execute()

    return get_report(UUID(report_id))


def _insert_report(row: dict) -> dict:
    """Insert one `reports` row and return it. A bad `site_id` is the client's error, not a 500."""
    try:
        return supabase.table("reports").insert(row).execute().data[0]
    except APIError as error:
        # 23503 is Postgres foreign_key_violation: the site_id does not exist.
        if error.code == "23503":
            raise HTTPException(status_code=422, detail="site_id does not exist") from error
        raise


@router.get("", response_model=list[ReportDetail])
def list_reports(
    site_id: UUID | None = None,
    activity: str | None = None,
    sif_potential: bool | None = None,
    iogp_rule: str | None = None,
    review_status: str | None = None,
    submitted_from: datetime | None = None,
    submitted_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ReportDetail]:
    """List and filter reports, newest first. The filters are `PRD.md` § Backend API's set.

    Returns full `ReportDetail` (including precursor spans and cleaned text) so the drill-down
    modal can show highlighted entities and precursor details, not just a summary.

    `sif_potential`, `iogp_rule` and `review_status` live on child tables, so they filter with
    `!inner` - which turns the embed into an inner join and drops reports whose child rows do
    not match, instead of returning the report with an empty child list.
    
    `activity` filters by the first word (verb) of activity precursor spans, matching the
    bucketing in `analytics/density.py`. This enables drill-down from the "By Activity" ranking.
    """
    select = REPORT_SELECT
    if sif_potential is not None or review_status:
        select = select.replace("classifications(", "classifications!inner(")
    if iogp_rule:
        select = select.replace("iogp_tags(", "iogp_tags!inner(")
    if activity:
        select = select.replace("precursors(", "precursors!inner(")

    query = supabase.table("reports").select(select)
    if site_id:
        query = query.eq("site_id", str(site_id))
    if activity:
        # Activity filter: match the first word (verb) of activity spans using ilike for case-insensitive
        # This must match the bucketing in analytics/density.py activity_bucket()
        query = query.eq("precursors.entity_type", "activity")
        # Supabase filter on text starts with: we need entity_text that starts with the activity verb
        # Use a simple approach: filter where entity_text starts with the activity (case-insensitive)
        query = query.ilike("precursors.entity_text", f"{activity}%")
    if sif_potential is not None:
        query = query.eq("classifications.sif_potential", sif_potential)
    if review_status:
        query = query.eq("classifications.review_status", review_status)
    if iogp_rule:
        query = query.eq("iogp_tags.rule_name", iogp_rule)
    if submitted_from:
        query = query.gte("submitted_at", submitted_from.isoformat())
    if submitted_to:
        query = query.lte("submitted_at", submitted_to.isoformat())

    rows = query.order("submitted_at", desc=True).limit(limit).execute().data or []
    return [_detail(row) for row in rows]


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: UUID) -> ReportDetail:
    """Full detail for one report: raw text, cleaned text, verdict, tags and precursor spans.

    This is what the Magic View renders. The spans index `cleaned_text`, never `raw_text`.
    """
    rows = supabase.table("reports").select(REPORT_SELECT).eq("id", str(report_id)).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="report not found")
    return _detail(rows[0])
