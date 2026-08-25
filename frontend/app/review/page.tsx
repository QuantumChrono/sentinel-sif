"use client";

/**
 * The Manual Review Queue (`PRD.md` § Frontend pages item 5): reports whose classifier confidence
 * fell below the threshold, awaiting a human call.
 *
 * WHAT PUTS A REPORT HERE AND WHAT TAKES IT OUT. `GET /api/v1/analytics/review-queue` returns rows
 * that are BOTH below `CONFIDENCE_THRESHOLD` and still `review_status = 'auto'`, least confident
 * first (`backend/routes/analytics.py`). A decision writes `confirmed` or `overridden`, which is
 * what removes the row - the model's `confidence` is deliberately never rewritten, so filtering on
 * confidence alone would leave every reviewed report here forever.
 *
 * A DECIDED ROW IS DROPPED FROM LOCAL STATE RATHER THAN REFETCHED. The endpoint would no longer
 * return it, so dropping it locally and refetching agree - and dropping it means the queue does not
 * flash or reorder the remaining rows under the officer's cursor mid-review. `verifiedGone` records
 * that the API confirmed the write, so the row leaves only after the server said so.
 *
 * CONFIRM KEEPS THE MODEL'S VERDICT; OVERRIDE INVERTS IT. Both send `sif_potential` explicitly,
 * because `ReviewDecision` requires it on both paths - a confirmation that does not restate what it
 * confirms is unauditable (`backend/schemas.py`).
 *
 * PER-ROW ACTION STATE, NOT ONE SHARED FLAG. A single `busy` boolean would disable every row's
 * buttons while one row saved, and a single `error` would attach one row's failure to all of them.
 */

import { useEffect, useState } from "react";

import {
  CONFIDENCE_THRESHOLD, getReviewQueue, reviewReport,
  type ApiError, type ReviewQueueRow,
} from "@/lib/api_client";
import { supabase } from "@/lib/supabase_client";
import { QueueRow } from "./queue_row";

type Load =
  | { name: "loading" }
  | { name: "loaded"; rows: ReviewQueueRow[] }
  | { name: "failed"; error: ApiError };

export default function ReviewQueuePage() {
  const [load, setLoad] = useState<Load>({ name: "loading" });
  /** Report ids currently saving, so only the acting row's buttons go disabled. */
  const [saving, setSaving] = useState<Set<string>>(new Set());
  /** Per-report failure messages, keyed by report id. */
  const [errors, setErrors] = useState<Record<string, string>>({});
  /** How many decisions this session has recorded — the queue emptying is otherwise
   * indistinguishable from a queue that was empty on arrival. */
  const [decided, setDecided] = useState(0);

  useEffect(() => {
    getReviewQueue().then((result) =>
      setLoad(result.ok ? { name: "loaded", rows: result.data } : { name: "failed", error: result.error }),
    );
  }, []);

  async function decide(row: ReviewQueueRow, reviewStatus: "confirmed" | "overridden") {
    setSaving((current) => new Set(current).add(row.id));
    setErrors((current) => {
      const next = { ...current };
      delete next[row.id];
      return next;
    });

    const { data } = await supabase.auth.getUser();
    if (!data.user) {
      setErrors((current) => ({
        ...current,
        [row.id]: "Your session has expired. Sign in again to record a decision.",
      }));
      setSaving((current) => {
        const next = new Set(current);
        next.delete(row.id);
        return next;
      });
      return;
    }

    const result = await reviewReport(row.id, {
      review_status: reviewStatus,
      sif_potential: reviewStatus === "confirmed" ? row.sif_potential : !row.sif_potential,
      reviewed_by: data.user.id,
    });

    if (result.ok) {
      // The API confirmed the write, so the row is genuinely out of the queue now.
      setLoad((current) =>
        current.name === "loaded"
          ? { name: "loaded", rows: current.rows.filter((queued) => queued.id !== row.id) }
          : current,
      );
      setDecided((count) => count + 1);
    } else {
      // A 422 reading "reviewed_by is not a known user" is the expected answer while the signed-in
      // account has no matching `users` row - `reviewed_by` is a foreign key (`DIY.md`). The API's
      // own message is shown verbatim, and the row STAYS in the queue, because nothing was written.
      setErrors((current) => ({ ...current, [row.id]: result.error.message }));
    }

    setSaving((current) => {
      const next = new Set(current);
      next.delete(row.id);
      return next;
    });
  }

  if (load.name === "loading") return <p className="text-sm text-slate-600">Loading review queue…</p>;

  if (load.name === "failed") {
    return (
      <div role="alert" className="space-y-2 rounded border border-rose-300 bg-rose-50 p-4">
        <h1 className="font-semibold text-rose-900">Could not load the review queue</h1>
        <p className="text-sm text-rose-900">{load.error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Manual review queue</h1>
        <p className="mt-1 text-sm text-slate-600">
          Reports the classifier was less than {(CONFIDENCE_THRESHOLD * 100).toFixed(0)}% confident
          about. They were not auto-published and are waiting on a human decision. Least confident
          first.
        </p>
      </div>

      {/* `aria-live` so a decision is announced, not only painted. */}
      <p aria-live="polite" className="text-sm text-slate-600">
        {load.rows.length === 0
          ? decided > 0
            ? `Queue clear — ${decided} report${decided === 1 ? "" : "s"} decided.`
            : "Nothing is awaiting review."
          : `${load.rows.length} report${load.rows.length === 1 ? "" : "s"} awaiting a decision${
              decided > 0 ? ` — ${decided} decided this session.` : "."
            }`}
      </p>

      {load.rows.length === 0 && decided === 0 && (
        <p className="rounded border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          No report is below the confidence threshold with an undecided verdict. A report appears
          here as soon as one is submitted that the classifier is not confident about.
        </p>
      )}

      <ul className="space-y-4">
        {load.rows.map((row) => (
          <QueueRow
            key={row.id}
            row={row}
            busy={saving.has(row.id)}
            error={errors[row.id]}
            onDecide={decide}
          />
        ))}
      </ul>
    </div>
  );
}
