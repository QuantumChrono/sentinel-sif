/**
 * Renders one `ReportDetail`: verdict, confidence, IOGP chips, and the highlighted report text.
 *
 * ONE RENDERER, TWO PAGES - the Intake page's inline result and the Report Detail "Magic View".
 * `backend/schemas.py` returns the same `ReportDetail` shape from `POST /api/v1/reports` and
 * `GET /api/v1/reports/{id}` specifically so this file can exist once. It is a server-safe
 * presentational component: no state, no fetching, no `"use client"`.
 *
 * IT RENDERS `cleaned_text`, NOT `raw_text`. The spans index the cleaned string and only the
 * cleaned string (`backend/schemas.py` module docstring). When preprocessing degrades, the backend
 * puts the original text in `cleaned_text`, so this stays correct on that path too.
 *
 * COLOUR IS NEVER THE ONLY CHANNEL. Each entity type carries its own underline style as well as
 * its own colour, the legend names all four in words, and the precursor list below names every
 * extracted entity next to its type. A colourblind reader distinguishes types by line style and by
 * the list; a screen reader reads the list.
 *
 * NOTHING IS INJECTED INTO THE HIGHLIGHTED TEXT. No screen-reader-only labels sit inside the
 * `<mark>` elements, because that text would land in the DOM and in anything a judge copies out of
 * the page - the rendered report has to be the report, character for character. The type mapping
 * is carried by the legend and the list instead, which is why both are always present.
 */

import { CONFIDENCE_THRESHOLD, type ReportDetail } from "@/lib/api_client";
import { buildReportSegments, ENTITY_STYLES, ENTITY_TYPES } from "@/lib/precursor_spans";

export function ReportResult({ report }: { report: ReportDetail }) {
  const segments = buildReportSegments(report.cleaned_text, report.precursors);
  const classification = report.classification;

  return (
    <article className="space-y-6">
      <section aria-labelledby="verdict-heading" className="space-y-3">
        <h2 id="verdict-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Verdict
        </h2>

        {classification ? (
          <div className="flex flex-wrap items-center gap-3">
            {/* The word carries the verdict; the colour only reinforces it. */}
            <span
              className={`rounded px-3 py-1 text-sm font-semibold ${
                classification.sif_potential
                  ? "bg-rose-100 text-rose-900 ring-1 ring-rose-300"
                  : "bg-emerald-100 text-emerald-900 ring-1 ring-emerald-300"
              }`}
            >
              {classification.sif_potential ? "SIF potential" : "No SIF potential"}
            </span>
            <span className="text-sm text-slate-700">
              Confidence{" "}
              <strong className="font-semibold">{(classification.confidence * 100).toFixed(1)}%</strong>
            </span>
            <span className="text-xs text-slate-500">model {classification.model_version}</span>
            {classification.review_status !== "auto" && (
              <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-800">
                {classification.review_status === "confirmed" ? "Confirmed by reviewer" : "Overridden by reviewer"}
              </span>
            )}
          </div>
        ) : (
          // `classification` is null exactly when status is `processing_failed`. A zero-confidence
          // placeholder here would be a fabricated verdict, so the absence is stated instead.
          <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            No verdict was produced for this report — analysis did not complete.
          </p>
        )}

        {classification && classification.confidence < CONFIDENCE_THRESHOLD && (
          <p className="text-sm text-slate-700">
            Below the {(CONFIDENCE_THRESHOLD * 100).toFixed(0)}% confidence threshold, so this
            report is routed to a human reviewer rather than auto-published.
          </p>
        )}
      </section>

      <section aria-labelledby="rules-heading" className="space-y-3">
        <h2 id="rules-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          IOGP Life-Saving Rules
        </h2>
        {report.iogp_tags.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {report.iogp_tags.map((tag) => (
              <li
                key={tag.rule_name}
                className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white"
              >
                {tag.rule_name}
                <span className="ml-1.5 font-normal text-slate-300">
                  {(tag.confidence * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        ) : (
          // The tagger is multi-label, so zero rules is a real answer, not a missing one.
          <p className="text-sm text-slate-600">No Life-Saving Rule was tagged for this report.</p>
        )}
      </section>

      <section aria-labelledby="text-heading" className="space-y-3">
        <h2 id="text-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Report text with precursors
        </h2>

        <p className="whitespace-pre-wrap rounded border border-slate-200 bg-white p-4 leading-8">
          {segments.map((segment, index) =>
            segment.entity ? (
              <mark
                key={index}
                title={ENTITY_STYLES[segment.entity.entity_type].label}
                className={`rounded px-0.5 underline underline-offset-4 ${
                  ENTITY_STYLES[segment.entity.entity_type].mark
                }`}
              >
                {segment.text}
              </mark>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </p>

        {/* All four types, always, including the ones absent from this report. `barrier_failure`
            spans are deliberately sparse in our data (`DECISIONS.md`), so three of four types is
            the normal case - a legend that changed shape per report would read as a broken one. */}
        <dl className="grid gap-2 sm:grid-cols-2">
          {ENTITY_TYPES.map((entityType) => {
            const found = report.precursors.filter((span) => span.entity_type === entityType);
            return (
              <div key={entityType} className="flex gap-2 text-sm">
                <dt className="flex shrink-0 items-center gap-2 font-medium">
                  <span
                    aria-hidden="true"
                    className={`inline-block h-4 w-6 rounded-sm ${ENTITY_STYLES[entityType].swatch}`}
                  />
                  {ENTITY_STYLES[entityType].label}
                </dt>
                <dd className="text-slate-700">
                  {found.length > 0
                    ? found.map((span) => span.entity_text).join(", ")
                    : <span className="text-slate-500">none in this report</span>}
                </dd>
              </div>
            );
          })}
        </dl>

        {report.precursors.length === 0 && (
          <p className="text-sm text-slate-600">
            No precursor entities were extracted, so the text above is shown unhighlighted.
          </p>
        )}
      </section>
    </article>
  );
}
