"use client";

/**
 * Report Intake - the demo's hero interaction. Submit renders the result INLINE, no navigation
 * (`PRD.md` § Frontend pages item 2).
 *
 * EVERY STATE IS EXPLICIT, because this is the screen a judge watches. `phase` is one union rather
 * than several booleans, so "submitting and also showing a stale result" is not a state this
 * component can reach. The button is disabled and relabelled while in flight, so there is never a
 * moment where the user cannot tell whether their submission registered.
 *
 * Empty input is blocked BEFORE the request leaves the browser. `ReportCreate` rejects it too and
 * that validator is the real boundary, but a round trip to be told the box is empty is a round trip
 * the user watches for nothing.
 *
 * An inference failure offers a retry, because the backend has already written a
 * `processing_failed` row and `PRD.md` § Edge cases requires a retry action rather than a stack
 * trace. A raw 500 cannot reach this page: `api_client.ts` turns every non-2xx into a typed
 * `ApiError` and never throws.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  createReport, listSites, MAX_REPORT_CHARS,
  type ApiError, type ReportDetail, type ReporterRole, type SiteOut,
} from "@/lib/api_client";
import { supabase } from "@/lib/supabase_client";
import { roleFromAppMetadata } from "@/lib/user_role";
import { ReportResult } from "../report_result";

type Phase =
  | { name: "idle" }
  | { name: "submitting" }
  | { name: "done"; report: ReportDetail }
  | { name: "failed"; error: ApiError };

const ROLE_LABELS: Record<ReporterRole, string> = {
  hse_manager: "HSE manager",
  site_supervisor: "site supervisor",
  admin: "administrator",
};

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900";

export default function IntakePage() {
  const [sites, setSites] = useState<SiteOut[] | null>(null);
  const [sitesError, setSitesError] = useState<string | null>(null);
  const [siteId, setSiteId] = useState("");
  const [text, setText] = useState("");
  const [emptyWarning, setEmptyWarning] = useState(false);
  const [phase, setPhase] = useState<Phase>({ name: "idle" });

  // `reporter_role` is required by `ReportCreate`, and the account's own claim is the only honest
  // source for it. Until the demo accounts exist with `app_metadata.role` set (`DIY.md`, Day 1)
  // every session carries no claim, so this falls back to the role that files reports - and the
  // value being sent is shown next to the button rather than chosen invisibly.
  const [reporterRole, setReporterRole] = useState<ReporterRole>("site_supervisor");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      const role = roleFromAppMetadata(data.session?.user.app_metadata);
      if (role === "hse_manager" || role === "admin") setReporterRole(role);
    });
  }, []);

  useEffect(() => {
    listSites().then((result) => {
      if (result.ok) setSites(result.data);
      else setSitesError(result.error.message);
    });
  }, []);

  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    if (!text.trim()) {
      setEmptyWarning(true);
      return;
    }
    setEmptyWarning(false);
    setPhase({ name: "submitting" });
    const result = await createReport({ site_id: siteId, raw_text: text, reporter_role: reporterRole });
    setPhase(result.ok ? { name: "done", report: result.data } : { name: "failed", error: result.error });
  }

  const submitting = phase.name === "submitting";
  // An empty `sites` table is today's normal state, not a bug - but `site_id` is required, so
  // submission is blocked with a reason instead of failing as a 422 the user cannot act on.
  const noSites = sites !== null && sites.length === 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Submit a safety report</h1>
        <p className="mt-1 text-sm text-slate-600">
          Write what you saw in your own words. Analysis runs immediately and appears below.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor="site" className="block text-sm font-medium">Site</label>
          <select
            id="site"
            required
            value={siteId}
            onChange={(event) => setSiteId(event.target.value)}
            disabled={sites === null || noSites || submitting}
            className={`mt-1 w-full max-w-sm rounded border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100 ${FOCUS}`}
          >
            <option value="">
              {sites === null ? "Loading sites…" : noSites ? "No sites configured" : "Select a site"}
            </option>
            {(sites ?? []).map((site) => (
              <option key={site.id} value={site.id}>{site.name} — {site.region}</option>
            ))}
          </select>
          {sitesError && (
            <p role="alert" className="mt-2 text-sm text-rose-900">Could not load sites: {sitesError}</p>
          )}
          {noSites && (
            <p className="mt-2 text-sm text-amber-900">
              No sites exist in the database yet, so a report cannot be filed against one.
            </p>
          )}
        </div>

        <div>
          <label htmlFor="report-text" className="block text-sm font-medium">What happened</label>
          <textarea
            id="report-text"
            required
            rows={8}
            maxLength={MAX_REPORT_CHARS}
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={submitting}
            aria-describedby="report-text-hint"
            className={`mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 font-mono text-sm disabled:bg-slate-100 ${FOCUS}`}
          />
          <p id="report-text-hint" className="mt-1 text-xs text-slate-500">
            {text.length.toLocaleString()} of {MAX_REPORT_CHARS.toLocaleString()} characters.
            Abbreviations, Hindi and Hinglish are expected and handled.
          </p>
          {emptyWarning && (
            <p role="alert" className="mt-2 text-sm text-rose-900">
              Enter the report text before submitting.
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={submitting || noSites || !siteId}
            className={`rounded bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-60 ${FOCUS}`}
          >
            {submitting ? "Analysing…" : "Submit and analyse"}
          </button>
          <span className="text-xs text-slate-500">Filing as {ROLE_LABELS[reporterRole]}</span>
        </div>
      </form>

      {/* `aria-live` so the outcome is announced when it lands, not only painted; `aria-busy`
          carries the in-flight state the way the button label carries it visually. */}
      <section aria-live="polite" aria-busy={submitting} className="space-y-4">
        {submitting && (
          <p className="rounded border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
            Running preprocessing, classifier, rule tagger and precursor extraction…
          </p>
        )}

        {phase.name === "failed" && (
          <div role="alert" className="space-y-3 rounded border border-rose-300 bg-rose-50 p-4">
            <p className="font-medium text-rose-900">
              {phase.error.kind === "validation" ? "This report was not accepted" : "Analysis did not complete"}
            </p>
            <p className="text-sm text-rose-900">{phase.error.message}</p>
            {phase.error.kind === "processing_failed" && phase.error.failure && (
              <p className="text-sm text-rose-900">
                The submission was saved and marked <code>processing_failed</code>. Stage:{" "}
                <code>{phase.error.failure.detail}</code>
              </p>
            )}
            {/* A retry only appears where retrying the same text can succeed. A 422 needs the text
                changed first, so offering a retry there would be a button that cannot work. */}
            {phase.error.kind !== "validation" && (
              <button
                type="button"
                onClick={() => submit()}
                className="rounded bg-rose-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-900"
              >
                Retry analysis
              </button>
            )}
          </div>
        )}

        {phase.name === "done" && (
          <div className="space-y-4 rounded border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-semibold">Analysis complete</h2>
              <Link href={`/reports/${phase.report.id}`} className={`rounded text-sm underline underline-offset-4 ${FOCUS}`}>
                Open full report
              </Link>
            </div>
            <ReportResult report={phase.report} />
          </div>
        )}
      </section>
    </div>
  );
}
