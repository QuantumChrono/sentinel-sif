"""The three dashboard endpoints: `/api/v1/analytics/density`, `/rules`, `/review-queue`.

EVERY ENDPOINT HERE RETURNS CORRECTLY ON AN EMPTY DATABASE. The dataset is still generating, so
an empty or near-empty table is today's normal state, not an exceptional one - and a dashboard
that throws on zero rows cannot be built a frontend against. Each function below returns an
empty list (or all-zero counts) rather than raising, and the density self-check in
`analytics/density.py` asserts the zero case directly.

WHY THE AGGREGATION HAPPENS IN PYTHON. Supabase's REST interface has no GROUP BY, so a rate per
site needs either a Postgres view or the rows themselves. At `PRD.md`'s stated scale - 2,000 to
3,000 reports - fetching the group-by columns and tallying them in a dict is a few milliseconds
and stays inspectable in one file. A materialized view is the right answer at 100x this size and
the wrong answer today: it moves the ranking logic into a migration nobody reviews.
"""

from fastapi import APIRouter, Query

from analytics.density import activity_bucket, rank_groups
from database import supabase
from schemas import (CONFIDENCE_THRESHOLD, IOGP_RULE_NAMES, DensityResponse, DensityRow,
                     ReviewQueueRow, RuleCount)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/density", response_model=DensityResponse)
def get_density() -> DensityResponse:
    """SIF-precursor density ranked by site and by activity.

    A RATE, not a count - SIF-potential reports as a proportion of that group's total - ordered
    by the Wilson lower bound so a 1-of-1 group cannot outrank a 24-of-40 one. The arithmetic and
    the reasoning behind it are in `analytics/density.py`.

    Reports with no classification (`processing_failed`) are excluded from BOTH the numerator and
    the denominator. They were never successfully analyzed, so counting them in the denominator
    would silently deflate a site's rate in proportion to how often its submissions crashed.
    """
    rows = supabase.table("reports").select(
        "id, site_id, sites(name, region), classifications!inner(sif_potential), "
        "precursors(entity_type, entity_text)"
    ).execute().data or []

    by_site: dict[str, dict] = {}
    by_activity: dict[str, dict] = {}

    for row in rows:
        classifications = row.get("classifications") or []
        if not classifications:
            continue
        is_sif = bool(classifications[0]["sif_potential"])

        site = row.get("sites")
        if site:
            site_id = row.get("site_id")
            tally = by_site.setdefault(site["name"], {"total": 0, "sif": 0, "region": site["region"], "site_id": site_id})
            tally["total"] += 1
            tally["sif"] += is_sif

        # One report can carry several activity spans; each is counted once for its bucket, and
        # a bucket is counted at most once per report so a report naming "welding" twice does not
        # give that activity a denominator of 2.
        buckets = {
            activity_bucket(span["entity_text"])
            for span in row.get("precursors") or []
            if span["entity_type"] == "activity"
        }
        for bucket in buckets:
            tally = by_activity.setdefault(bucket, {"total": 0, "sif": 0, "region": None})
            tally["total"] += 1
            tally["sif"] += is_sif

    return DensityResponse(
        by_site=[
            DensityRow(
                group_type="site",
                group_id=row.get("site_id"),
                group_name=row["group_name"],
                region=row["region"],
                total_reports=row["total_reports"],
                sif_reports=row["sif_reports"],
                sif_rate=row["sif_rate"],
                rank_score=row["rank_score"],
            )
            for row in rank_groups(by_site)
        ],
        by_activity=[
            DensityRow(
                group_type="activity",
                group_id=None,
                group_name=row["group_name"],
                region=row["region"],
                total_reports=row["total_reports"],
                sif_reports=row["sif_reports"],
                sif_rate=row["sif_rate"],
                rank_score=row["rank_score"],
            )
            for row in rank_groups(by_activity)
        ],
    )


@router.get("/rules", response_model=list[RuleCount])
def get_rule_distribution() -> list[RuleCount]:
    """Report count across the 9 IOGP rules, in `PRD.md` § Glossary order.

    ALL NINE ARE ALWAYS RETURNED, zeros included, so the dashboard chart has a stable set of nine
    bars from the first report onward instead of growing an axis as rules first appear. Order is
    the canonical PRD order rather than count-descending, for the same reason: bars that reorder
    on every refresh are unreadable.

    A rule is counted once per report even if the tagger emitted it twice, so the number is
    "reports naming this rule" - which is what a distribution chart claims to show.
    """
    rows = supabase.table("iogp_tags").select("report_id, rule_name").execute().data or []

    seen: dict[str, set] = {name: set() for name in IOGP_RULE_NAMES}
    for row in rows:
        # An unknown rule name is ignored rather than added: the canonical 9 do not grow at
        # runtime, and a typo from a future model must not invent a tenth bar on the chart.
        if row["rule_name"] in seen:
            seen[row["rule_name"]].add(row["report_id"])

    return [RuleCount(rule_name=name, report_count=len(seen[name])) for name in IOGP_RULE_NAMES]


@router.get("/review-queue", response_model=list[ReviewQueueRow])
def get_review_queue(limit: int = Query(default=50, ge=1, le=200)) -> list[ReviewQueueRow]:
    """Reports whose classifier confidence fell below the threshold and that no human has decided.

    Two conditions, both required. Confidence below `CONFIDENCE_THRESHOLD` is what put the report
    here; `review_status = 'auto'` is what keeps it here. Filtering on confidence alone would
    leave every reviewed report in the queue forever, since a review deliberately does not
    rewrite the model's confidence (see `routes/review.py`).

    Lowest confidence first: the most uncertain verdict is the one most worth a human's next
    minute.
    """
    rows = supabase.table("classifications").select(
        "confidence, sif_potential, reports!inner(id, raw_text, submitted_at, sites(name))"
    ).lt("confidence", CONFIDENCE_THRESHOLD).eq("review_status", "auto").order(
        "confidence").limit(limit).execute().data or []

    queue = []
    for row in rows:
        report = row["reports"]
        site = report.get("sites")
        queue.append(ReviewQueueRow(
            id=report["id"],
            site_name=site["name"] if site else None,
            raw_text=report["raw_text"],
            submitted_at=report["submitted_at"],
            sif_potential=row["sif_potential"],
            confidence=row["confidence"],
        ))
    return queue
