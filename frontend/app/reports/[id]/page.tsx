"use client";

/**
 * Report Detail - the "Magic View" (`PRD.md` § Frontend pages item 3).
 *
 * The verdict, confidence, IOGP chips and highlighted text all come from `ReportResult`, the same
 * renderer the Intake page's inline result uses. This file adds only what is specific to the detail
 * view: loading the report by id, and the officer's Confirm / Override decision.
 *
 * A CLIENT COMPONENT, DELIBERATELY. `reviewed_by` must be the signed-in user's id, which is read
 * from the browser session, and the decision has to re-render the verdict in place. Nothing here is
 * secret: `middleware.ts` has already refused unauthenticated visitors before this page is sent.
 *
 * WHAT CONFIRM AND OVERRIDE ACTUALLY SEND. Confirm keeps the model's `sif_potential`; Override
 * inverts it. Both send it explicitly, because `ReviewDecision` requires the field on both paths -
 * a confirmation that does not restate what it confirms is unauditable (`backend/schemas.py`).
 */

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  CONFIDENCE_THRESHOLD, getReport, reviewReport,
  type ApiError, type ReportDetail,
} from "@/lib/api_client";
import { supabase } from "@/lib/supabase_client";
import { ReportResult } from "../../report_result";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900";

type Load =
  | { name: "loading" }
  | { name: "loaded"; report: ReportDetail }
  | { name: "failed"; error: ApiError };

export default function ReportDetailPage() {
  const reportId = String(useParams().id);
  const [load, setLoad] = useState<Load>({ name: "loading" });
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => {
    getReport(reportId).then((result) =>
      setLoad(result.ok ? { name: "loaded", report: result.data } : { name: "failed", error: result.error }),
    );
  }, [reportId]);

  async function decide(reviewStatus: "confirmed" | "overridden") {
    if (load.name !== "loaded" || !load.report.classification) return;
    setReviewing(true);
    setReviewError(null);

    const { data } = await supabase.auth.getUser();
    if (!data.user) {
      setReviewError("Your session has expired. Sign in again to record a decision.");
      setReviewing(false);
      return;
    }

    const modelVerdict = load.report.classification.sif_potential;
    const result = await reviewReport(reportId, {
      review_status: reviewStatus,
      // Confirm restates the model's verdict; Override records the opposite one.
      sif_potential: reviewStatus === "confirmed" ? modelVerdict : !modelVerdict,
      reviewed_by: data.user.id,
    });

    if (result.ok) {
      // The endpoint returns the updated classification, so the page re-renders from what was
      // actually written rather than from what this component assumed it wrote.
      setLoad({ name: "loaded", report: { ...load.report, classification: result.data, status: "processed" } });
    } else {
      // A 422 here is the expected answer while the `users` table is empty: `reviewed_by` is a
      // foreign key, so an auth account with no `users` row is not a known reviewer (`DIY.md`).
      // The API's own message is shown, because "not a known user" is the actionable sentence.
      setReviewError(result.error.message);
    }
    setReviewing(false);
  }

  if (load.name === "loading") {
    return <p className="text-sm text-slate-600">Loading report…</p>;
  }

  if (load.name === "failed") {
    return (
      <div role="alert" className="space-y-2 rounded border border-rose-300 bg-rose-50 p-4">
        <h1 className="font-semibold text-rose-900">
          {load.error.kind === "not_found" ? "Report not found" : "Could not load this report"}
        </h1>
        <p className="text-sm text-rose-900">{load.error.message}</p>
      </div>
    );
  }

  const report = load.report;
  const classification = report.classification;
  // Both conditions, as `routes/analytics.py` defines the queue: below threshold is what put it
  // here, `auto` is what keeps it here. A report already decided shows its outcome, not the buttons.
  const awaitingDecision =
    classification !== null &&
    classification.confidence < CONFIDENCE_THRESHOLD &&
    classification.review_status === "auto";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Report detail</h1>
        <p className="mt-1 text-sm text-slate-600">
          {report.site ? `${report.site.name} — ${report.site.region}` : "No site recorded"}
          {" · "}
          {new Date(report.submitted_at).toLocaleString()}
          {" · "}filed by {report.reporter_role}
          {" · "}language {report.language_detected}
        </p>
      </div>

      <ReportResult report={report} />

      {awaitingDecision && (
        <section aria-labelledby="review-heading" className="space-y-3 rounded border border-amber-300 bg-amber-50 p-4">
          <h2 id="review-heading" className="font-semibold text-amber-900">
            Awaiting your decision
          </h2>
          <p className="text-sm text-amber-900">
            The classifier reported {(classification.confidence * 100).toFixed(1)}% confidence,
            below the {(CONFIDENCE_THRESHOLD * 100).toFixed(0)}% threshold. Confirm the verdict of{" "}
            <strong>{classification.sif_potential ? "SIF potential" : "no SIF potential"}</strong>,
            or override it.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => decide("confirmed")}
              disabled={reviewing}
              className={`rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60 ${FOCUS}`}
            >
              {reviewing ? "Saving…" : "Confirm verdict"}
            </button>
            <button
              type="button"
              onClick={() => decide("overridden")}
              disabled={reviewing}
              className={`rounded border border-slate-400 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-60 ${FOCUS}`}
            >
              {reviewing
                ? "Saving…"
                : `Override to ${classification.sif_potential ? "no SIF potential" : "SIF potential"}`}
            </button>
          </div>
          {reviewError && (
            <p role="alert" className="text-sm font-medium text-rose-900">
              Decision not saved: {reviewError}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
