"use client";

/**
 * The recent high-risk feed (`PRD.md` § Frontend pages item 4): the newest SIF-potential reports.
 *
 * WHAT MAKES A ROW "HIGH RISK" IS THE CLASSIFIER'S VERDICT, NOT A SCORE THIS FILE INVENTS. The list
 * comes from `GET /api/v1/reports?sif_potential=true`, newest first - so the filter is applied by
 * the database against the `classifications` row, not by re-ranking something in the browser.
 *
 * A REVIEWED VERDICT IS MARKED AS SUCH. `review_status` is shown whenever a human has acted, so a
 * row that reads "SIF potential" because an officer overrode the model is not presented as the
 * model's own call.
 */

import Link from "next/link";

import type { ReportSummary } from "@/lib/api_client";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900";

/** Long enough to recognise the incident, short enough that ten rows stay scannable. */
const EXCERPT_CHARS = 180;

function excerpt(text: string): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  return collapsed.length > EXCERPT_CHARS ? `${collapsed.slice(0, EXCERPT_CHARS)}…` : collapsed;
}

export function HighRiskFeed({ reports }: { reports: ReportSummary[] }) {
  if (reports.length === 0) {
    return (
      <p className="rounded border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
        No report has been classified as SIF-potential yet. This feed fills as reports are processed.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {reports.map((report) => (
        <li key={report.id} className="rounded border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="rounded bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-900 ring-1 ring-rose-300">
              SIF potential
            </span>
            <span className="text-sm font-medium">
              {report.site ? `${report.site.name} — ${report.site.region}` : "No site recorded"}
            </span>
            <span className="text-xs text-slate-500">
              {new Date(report.submitted_at).toLocaleString()}
            </span>
            {report.classification && (
              <span className="text-xs text-slate-500 tabular-nums">
                {(report.classification.confidence * 100).toFixed(1)}% confidence
              </span>
            )}
            {report.classification && report.classification.review_status !== "auto" && (
              <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-800">
                {report.classification.review_status === "confirmed" ? "Confirmed by reviewer" : "Overridden by reviewer"}
              </span>
            )}
            <Link
              href={`/reports/${report.id}`}
              className={`ml-auto rounded text-sm underline underline-offset-4 ${FOCUS}`}
            >
              Open report
            </Link>
          </div>

          <p className="mt-2 text-sm text-slate-700">{excerpt(report.raw_text)}</p>

          {report.iogp_tags.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {report.iogp_tags.map((tag) => (
                <li key={tag.rule_name} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                  {tag.rule_name}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}
