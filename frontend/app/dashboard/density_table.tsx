"use client";

/**
 * The Site / Activity Density Ranking table - the single most important screen in the product
 * (`PRD.md` § Frontend pages item 4 calls it the literal expected-outcome line of the problem
 * statement). Rendered twice by the dashboard: once for `by_site`, once for `by_activity`.
 *
 * DENSITY IS A RATE, NOT A COUNT. `sif_rate` is SIF-potential reports over TOTAL reports for that
 * group, computed in `backend/analytics/density.py`. This table displays that rate AND the two
 * integers it came from, in the same cell, so every percentage on screen can be divided back out
 * by eye. A rate with its denominator hidden is a number nobody can audit.
 *
 * WHY THE DEFAULT ORDER IS NOT THE RATE COLUMN. The rows arrive ordered by `rank_score`, the
 * Wilson lower bound, and that is the order this table opens in. A raw rate makes 1-of-1 a perfect
 * 100% and floats a single report above a site with 24 of 40 - so the honest rate is what gets
 * DISPLAYED while the defensible score is what SORTS (`DECISIONS.md`, Block 5). The `rank_score`
 * column is shown rather than hidden precisely so "why is 100% below 60%?" is answered by the
 * table itself.
 *
 * SORTING IS PURELY LOCAL AND NEVER REFETCHES. It reorders the rows already on screen. Clicking
 * `Ranking score` returns to the backend's own ordering, so a reader can always get back to the
 * defensible view after exploring.
 */

import { useState } from "react";

import type { DensityRow } from "@/lib/api_client";

/** The sortable columns. Keys are `DensityRow` field names, so a header cannot name a column that
 * does not exist in the payload. `region` is absent for activities, which have no region. */
type SortKey = "group_name" | "region" | "total_reports" | "sif_reports" | "sif_rate" | "rank_score";

interface Sort {
  key: SortKey;
  /** `desc` first for every numeric column: the question this table answers is "which is worst",
   * so the first click on a number should put the largest at the top, not the smallest. */
  direction: "asc" | "desc";
}

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900";

function compare(a: DensityRow, b: DensityRow, key: SortKey): number {
  const left = a[key];
  const right = b[key];
  if (typeof left === "number" && typeof right === "number") return left - right;
  // `region` is `string | null`; a null sorts as an empty string rather than throwing.
  return String(left ?? "").localeCompare(String(right ?? ""));
}

/** Defined at module level, NOT inside `DensityTable`. A component declared inside the render body
 * is a new type on every render, so React remounts these `<th>` subtrees each time the sort changes
 * - which destroys focus on the very button the user just activated, and a keyboard user loses their
 * place in the table on every sort. */
function SortableHeader({
  column, label, hint, sort, onSort,
}: {
  column: SortKey;
  label: string;
  hint?: string;
  sort: Sort;
  onSort: (key: SortKey) => void;
}) {
  const active = sort.key === column;
  return (
    <th
      scope="col"
      // `aria-sort` is what tells a screen reader which column is ordering the table.
      aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
      className="border-b border-slate-200 px-3 py-2 text-left font-semibold"
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        title={hint}
        className={`flex items-center gap-1 rounded hover:underline ${FOCUS}`}
      >
        {label}
        {/* Decorative - `aria-sort` above already carries the state to assistive technology. */}
        <span aria-hidden="true" className={active ? "text-slate-900" : "text-slate-300"}>
          {active && sort.direction === "asc" ? "↑" : "↓"}
        </span>
      </button>
    </th>
  );
}

export function DensityTable({
  rows,
  groupLabel,
  showRegion,
  emptyMessage,
}: {
  rows: DensityRow[];
  /** Header for the name column - "Site" or "Activity". */
  groupLabel: string;
  /** Activities carry no region, so the column is dropped rather than filled with dashes. */
  showRegion: boolean;
  emptyMessage: string;
}) {
  const [sort, setSort] = useState<Sort>({ key: "rank_score", direction: "desc" });

  // A copy: mutating the prop array would reorder the caller's state in place.
  const sorted = [...rows].sort((a, b) => {
    const result = compare(a, b, sort.key);
    return sort.direction === "asc" ? result : -result;
  });

  function toggle(key: SortKey) {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        // Numbers open descending (worst first); the name column opens A-Z.
        : { key, direction: key === "group_name" || key === "region" ? "asc" : "desc" },
    );
  }

  if (rows.length === 0) {
    return <p className="rounded border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="w-full min-w-[40rem] border-collapse text-sm">
        <caption className="sr-only">
          {groupLabel} ranking by SIF-precursor density, sorted by {sort.key.replace(/_/g, " ")}
          {sort.direction === "asc" ? ", ascending" : ", descending"}
        </caption>
        <thead className="bg-slate-50 text-slate-700">
          <tr>
            <SortableHeader column="group_name" label={groupLabel} sort={sort} onSort={toggle} />
            {showRegion && <SortableHeader column="region" label="Region" sort={sort} onSort={toggle} />}
            <SortableHeader
              column="sif_rate"
              label="SIF density"
              hint="SIF-potential reports as a share of this group's total reports"
              sort={sort}
              onSort={toggle}
            />
            <SortableHeader column="sif_reports" label="SIF reports" sort={sort} onSort={toggle} />
            <SortableHeader column="total_reports" label="Total reports" sort={sort} onSort={toggle} />
            <SortableHeader
              column="rank_score"
              label="Ranking score"
              hint="Wilson 95% lower bound - the ordering the backend applies, so a 1-of-1 group cannot outrank 24-of-40"
              sort={sort}
              onSort={toggle}
            />
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={`${row.group_type}:${row.group_name}`} className="border-b border-slate-100 last:border-0">
              <th scope="row" className="px-3 py-2 text-left font-medium">{row.group_name}</th>
              {showRegion && <td className="px-3 py-2 text-slate-600">{row.region ?? "—"}</td>}
              <td className="px-3 py-2 tabular-nums">
                <span className="font-semibold">{(row.sif_rate * 100).toFixed(1)}%</span>
                {/* The fraction the percentage came from, so the number is checkable in place. */}
                <span className="ml-2 text-xs text-slate-500">
                  {row.sif_reports} of {row.total_reports}
                </span>
              </td>
              <td className="px-3 py-2 tabular-nums text-slate-700">{row.sif_reports}</td>
              <td className="px-3 py-2 tabular-nums text-slate-700">{row.total_reports}</td>
              <td className="px-3 py-2 tabular-nums text-slate-700">{row.rank_score.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
