"use client";

/**
 * One row of the Manual Review Queue: the report, the model's verdict, and the two decision buttons.
 *
 * PRESENTATION ONLY. It owns no state and performs no write - `page.tsx` holds the queue, calls the
 * API and decides whether this row survives. Splitting it that way keeps the write path in exactly
 * one file, so "what happens when an officer clicks Confirm" is answered without reading two.
 *
 * `busy` AND `error` ARE PER-ROW, PASSED IN. A single shared flag would disable every row's buttons
 * while one row saved, and a single shared message would attach one row's failure to all of them.
 */

import Link from "next/link";

import type { ReviewQueueRow } from "@/lib/api_client";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900";

export function QueueRow({
  row,
  busy,
  error,
  onDecide,
}: {
  row: ReviewQueueRow;
  busy: boolean;
  error?: string;
  onDecide: (row: ReviewQueueRow, reviewStatus: "confirmed" | "overridden") => void;
}) {
  return (
    <li className="space-y-3 rounded border border-amber-300 bg-amber-50 p-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm font-medium">{row.site_name ?? "No site recorded"}</span>
        <span className="text-xs text-slate-600">{new Date(row.submitted_at).toLocaleString()}</span>
        <span className="rounded bg-white px-2 py-0.5 text-xs font-semibold text-amber-900 ring-1 ring-amber-300 tabular-nums">
          {(row.confidence * 100).toFixed(1)}% confidence
        </span>
        <Link
          href={`/reports/${row.id}`}
          className={`ml-auto rounded text-sm underline underline-offset-4 ${FOCUS}`}
        >
          Open full report
        </Link>
      </div>

      {/* Capped in height so one very long submission cannot push the rest of the queue off the
          screen. The full text is on the detail page, one click away. */}
      <p className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded border border-amber-200 bg-white p-3 text-sm text-slate-800">
        {row.raw_text}
      </p>

      <p className="text-sm text-amber-900">
        The model&apos;s verdict is{" "}
        <strong>{row.sif_potential ? "SIF potential" : "no SIF potential"}</strong>. Confirm it, or
        override it to the opposite.
      </p>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => onDecide(row, "confirmed")}
          disabled={busy}
          className={`rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60 ${FOCUS}`}
        >
          {busy ? "Saving…" : "Confirm verdict"}
        </button>
        <button
          type="button"
          onClick={() => onDecide(row, "overridden")}
          disabled={busy}
          className={`rounded border border-slate-400 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-60 ${FOCUS}`}
        >
          {busy ? "Saving…" : `Override to ${row.sif_potential ? "no SIF potential" : "SIF potential"}`}
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm font-medium text-rose-900">
          Decision not saved: {error}
        </p>
      )}
    </li>
  );
}
