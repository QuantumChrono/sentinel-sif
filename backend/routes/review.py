"""The human decision path: `POST /api/v1/reports/{id}/review`.

An HSE officer confirms or overrides a classification. This is the endpoint that makes the
confidence threshold meaningful - without it, a low-confidence verdict would sit in the queue
forever and `needs_review` would be a label rather than a workflow.

WHAT A REVIEW WRITES. The `classifications` row is updated in place: `review_status` becomes
`confirmed` or `overridden`, `reviewed_by` records who decided, and `sif_potential` takes the
officer's verdict. The model's `confidence` is deliberately left untouched - it is a record of
what the model said, and rewriting it would destroy the evidence needed to tune the threshold
on real reviewed data (Lane A, Day 3).
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from postgrest.exceptions import APIError

from database import supabase
from schemas import ClassificationOut, ReviewDecision

router = APIRouter(prefix="/api/v1/reports", tags=["review"])


@router.post("/{report_id}/review", response_model=ClassificationOut)
def review_report(report_id: UUID, decision: ReviewDecision) -> ClassificationOut:
    """Record an officer's confirm or override, and take the report out of the review queue."""
    existing = supabase.table("classifications").select("id").eq(
        "report_id", str(report_id)).execute().data
    if not existing:
        # Either the report does not exist, or it is `processing_failed` and never produced a
        # verdict. Both are 404 on this route: there is no classification here to review, and
        # inventing one so the request can succeed would fabricate a verdict.
        raise HTTPException(status_code=404, detail="no classification to review for this report")

    try:
        updated = supabase.table("classifications").update({
            "sif_potential": decision.sif_potential,
            "review_status": decision.review_status,
            "reviewed_by": str(decision.reviewed_by),
        }).eq("report_id", str(report_id)).execute().data[0]
    except APIError as error:
        # 23503 is Postgres foreign_key_violation: `reviewed_by` is not a real user.
        if error.code == "23503":
            raise HTTPException(status_code=422, detail="reviewed_by is not a known user") from error
        raise

    # A human has now decided, so the report is no longer awaiting review. Written explicitly
    # rather than derived on read: `GET /reports?review_status=...` and the dashboard KPI cards
    # both read `reports.status`, and a status that still says `needs_review` after a decision
    # would keep the report visible in the queue.
    supabase.table("reports").update({"status": "processed"}).eq(
        "id", str(report_id)).execute()

    return ClassificationOut(**updated)
