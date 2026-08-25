"use client";

/**
 * The HSE Dashboard (`PRD.md` § Frontend pages item 4). Four parts: the Site/Activity Density
 * Ranking table, KPI cards, the IOGP rule distribution chart, and the recent high-risk feed.
 *
 * THE DENSITY RANKING COMES FIRST ON THE PAGE BECAUSE IT IS THE PRODUCT. `PRD.md` calls it the
 * literal expected-outcome line of the problem statement and warns against letting it become an
 * afterthought, so it sits above the KPI cards rather than below them.
 *
 * EVERY NUMBER ON THIS SCREEN COMES OUT OF A QUERY RESULT. There is no sample data and no
 * placeholder anywhere in this file. The KPI totals are summed from the density payload's own
 * per-site integers rather than from a separate count query, so a card and the table cannot
 * disagree - they are the same rows added up two ways.
 *
 * WHAT "REPORTS WITH A VERDICT" COUNTS, AND WHY THE CARD SAYS IT. `/analytics/density` excludes
 * reports that produced no classification - the `processing_failed` ones - from both the numerator
 * and the denominator (`backend/routes/analytics.py`), and groups by site. So these totals are
 * analysed reports that carry a site, not every row in the table. Labelling the card "Total
 * reports" would quietly overstate it by however many submissions crashed.
 *
 * AN EMPTY DATABASE IS A FIRST-CLASS STATE, NOT AN ERROR. The dataset is still generating, so zero
 * rows is today's normal condition rather than an exceptional one. Each section renders its own
 * empty sentence, and the page leads with an explicit banner when nothing has been processed.
 */

import { useEffect, useState } from "react";

import {
  getDensity, getReviewQueue, getRuleDistribution, listReports,
  type ApiError, type DensityResponse, type ReportSummary, type ReviewQueueRow, type RuleCount,
} from "@/lib/api_client";
import { DensityTable } from "./density_table";
import { HighRiskFeed } from "./high_risk_feed";
import { KpiCards } from "./kpi_cards";
import { RuleDistributionChart } from "./rule_distribution_chart";

/** The endpoint maximum, so the queue KPI is an exact count rather than a page size. At exactly
 * this many the card says "at least", because the real number could be higher. */
const QUEUE_LIMIT = 200;
const FEED_LIMIT = 10;

interface DashboardData {
  density: DensityResponse;
  rules: RuleCount[];
  queue: ReviewQueueRow[];
  highRisk: ReportSummary[];
}

type Load =
  | { name: "loading" }
  | { name: "loaded"; data: DashboardData }
  | { name: "failed"; error: ApiError };

export default function DashboardPage() {
  const [load, setLoad] = useState<Load>({ name: "loading" });

  useEffect(() => {
    // Four independent reads, in parallel: run serially they would add their latencies together for
    // no reason, and `PRD.md` § Non-functional requirements targets this page under 2s.
    Promise.all([
      getDensity(),
      getRuleDistribution(),
      getReviewQueue(QUEUE_LIMIT),
      listReports({ sif_potential: true, limit: FEED_LIMIT }),
    ]).then(([density, rules, queue, highRisk]) => {
      // The page fails as a whole rather than rendering three panels and a silent hole: a dashboard
      // that hides one broken query is a dashboard nobody can trust the rest of.
      if (!density.ok) return setLoad({ name: "failed", error: density.error });
      if (!rules.ok) return setLoad({ name: "failed", error: rules.error });
      if (!queue.ok) return setLoad({ name: "failed", error: queue.error });
      if (!highRisk.ok) return setLoad({ name: "failed", error: highRisk.error });
      setLoad({
        name: "loaded",
        data: { density: density.data, rules: rules.data, queue: queue.data, highRisk: highRisk.data },
      });
    });
  }, []);

  if (load.name === "loading") return <p className="text-sm text-slate-600">Loading dashboard…</p>;

  if (load.name === "failed") {
    return (
      <div role="alert" className="space-y-2 rounded border border-rose-300 bg-rose-50 p-4">
        <h1 className="font-semibold text-rose-900">Could not load the dashboard</h1>
        <p className="text-sm text-rose-900">{load.error.message}</p>
      </div>
    );
  }

  const { density, rules, queue, highRisk } = load.data;

  // Summed from the same per-site rows the table renders, so the cards and the table are two views
  // of one set of numbers rather than two queries that can drift apart.
  const rulesSeen = rules.filter((rule) => rule.report_count > 0).length;
  const analysedReports = density.by_site.reduce((sum, row) => sum + row.total_reports, 0);
  const nothingProcessed = analysedReports === 0 && queue.length === 0 && highRisk.length === 0;

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">HSE dashboard</h1>
        <p className="mt-1 text-sm text-slate-600">
          SIF-precursor density by site and activity, across every report that has been analysed.
        </p>
      </div>

      {nothingProcessed && (
        <div className="rounded border border-amber-300 bg-amber-50 p-4">
          <h2 className="font-semibold text-amber-900">No reports have been processed yet</h2>
          <p className="mt-1 text-sm text-amber-900">
            Every figure below is empty because the database holds no analysed report — not because
            anything failed. Submit a report from the intake page and this dashboard fills in.
          </p>
        </div>
      )}

      {/* The priority screen, first on the page. */}
      <section aria-labelledby="density-heading" className="space-y-6">
        <div>
          <h2 id="density-heading" className="text-lg font-semibold">SIF-precursor density ranking</h2>
          <p className="mt-1 text-sm text-slate-600">
            Density is a <strong>rate</strong> — SIF-potential reports as a share of that
            group&apos;s total reports — so a site is not ranked worse simply for reporting more.
            Both underlying counts sit beside every percentage. Rows open in the backend&apos;s own
            order, which sorts on the Wilson 95% lower bound so a single report at 100% cannot
            outrank 24 of 40. Click any column heading to re-sort.
          </p>
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">By site</h3>
          <DensityTable
            rows={density.by_site}
            groupLabel="Site"
            showRegion
            emptyMessage="No site has an analysed report yet, so there is nothing to rank."
          />
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">By activity</h3>
          <DensityTable
            rows={density.by_activity}
            groupLabel="Activity"
            showRegion={false}
            emptyMessage="No activity precursor has been extracted yet, so there is nothing to rank."
          />
        </div>
      </section>

      <section aria-labelledby="kpi-heading">
        <h2 id="kpi-heading" className="sr-only">Key figures</h2>
        <KpiCards density={density} queue={queue} queueTruncated={queue.length === QUEUE_LIMIT} />
      </section>

      <section aria-labelledby="rules-heading" className="space-y-3">
        <h2 id="rules-heading" className="text-lg font-semibold">IOGP Life-Saving Rule distribution</h2>
        <p className="text-sm text-slate-600">
          Reports tagged against each of the 9 canonical rules. All nine are always listed:{" "}
          {rulesSeen} of 9 currently have at least one report, and a rule at zero is drawn at zero
          rather than dropped from the chart.
        </p>
        <RuleDistributionChart rules={rules} />
      </section>

      <section aria-labelledby="feed-heading" className="space-y-3">
        <h2 id="feed-heading" className="text-lg font-semibold">Recent high-risk reports</h2>
        <p className="text-sm text-slate-600">
          The {FEED_LIMIT} most recent reports classified as SIF-potential, newest first.
        </p>
        <HighRiskFeed reports={highRisk} />
      </section>
    </div>
  );
}
