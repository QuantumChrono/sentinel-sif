"use client";

/**
 * The four KPI cards (`PRD.md` § Frontend pages item 4).
 *
 * EVERY FIGURE IS DERIVED FROM THE DENSITY PAYLOAD THE TABLE ALSO RENDERS, not from a separate
 * count query. Summing the per-site integers means a card and the ranking table are two views of
 * one set of numbers and cannot drift apart; two independent queries could disagree, and the card
 * would be the one nobody checks.
 *
 * WHAT "REPORTS WITH A VERDICT" COUNTS. `/analytics/density` excludes reports that produced no
 * classification - the `processing_failed` ones - from both numerator and denominator, and groups
 * by site (`backend/routes/analytics.py`). So the total is analysed reports carrying a site, not
 * every row in the table. Labelling it "Total reports" would overstate it by however many
 * submissions crashed, which is why the card names the narrower thing it actually measures.
 */

import type { DensityResponse, ReviewQueueRow } from "@/lib/api_client";

function KpiCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <dt className="text-sm text-slate-600">{label}</dt>
      {/* Proportional figures on purpose: `tabular-nums` makes a large standalone number read loose. */}
      <dd className="mt-1 text-3xl font-semibold tracking-tight">{value}</dd>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  );
}

export function KpiCards({
  density,
  queue,
  queueTruncated,
}: {
  density: DensityResponse;
  queue: ReviewQueueRow[];
  /** The queue came back at exactly the requested limit, so the real count may be higher and the
   * card says "at least" rather than presenting a page size as a total. */
  queueTruncated: boolean;
}) {
  const totalReports = density.by_site.reduce((sum, row) => sum + row.total_reports, 0);
  const sifReports = density.by_site.reduce((sum, row) => sum + row.sif_reports, 0);
  const overallRate = totalReports > 0 ? sifReports / totalReports : 0;
  // `by_site` arrives ordered by `rank_score`, so the first row IS the ranking's top site.
  const topSite = density.by_site[0] ?? null;

  return (
    <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        label="Reports with a verdict"
        value={totalReports.toLocaleString()}
        detail="Analysed and attributed to a site; excludes submissions whose analysis failed."
      />
      <KpiCard
        label="SIF potential"
        value={sifReports.toLocaleString()}
        detail={`${(overallRate * 100).toFixed(1)}% of those reports.`}
      />
      <KpiCard
        label="Awaiting human review"
        value={`${queueTruncated ? "≥" : ""}${queue.length.toLocaleString()}`}
        detail="Below the confidence threshold and not yet decided."
      />
      <KpiCard
        label="Highest density site"
        value={topSite ? `${(topSite.sif_rate * 100).toFixed(1)}%` : "—"}
        detail={topSite
          ? `${topSite.group_name} — ${topSite.sif_reports} of ${topSite.total_reports} reports.`
          : "No analysed report yet."}
      />
    </dl>
  );
}
