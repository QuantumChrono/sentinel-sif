"use client";

/**
 * Report count across the 9 IOGP Life-Saving Rules (`PRD.md` § Frontend pages item 4).
 *
 * ALL NINE BARS ALWAYS RENDER, INCLUDING ZEROS. `GET /api/v1/analytics/rules` returns all nine in
 * canonical `PRD.md` § Glossary order whether or not any report has been tagged with them, and this
 * chart draws every one it is given. A rule with no reports at our current dataset size is a real
 * finding - "nothing has been tagged Confined Space yet" - not an absence to hide by dropping the
 * category. Its bar is zero-width and its count reads `0` next to the axis label.
 *
 * HORIZONTAL, BECAUSE THE LABELS ARE LONG. "Safe Mechanical Lifting" and "Bypassing Safety
 * Controls" cannot sit under vertical columns without rotating to 45 degrees or truncating. Rotated
 * axis labels are the most common way this exact chart becomes unreadable.
 *
 * ONE HUE FOR ALL NINE BARS, NOT NINE. The rules are nominal - they have no order, and no rule is a
 * separate data series - so bar length already carries the only quantity here. Colouring each bar
 * differently would spend the identity channel re-encoding what length shows. The hue is blue
 * rather than this app's slate, rose or emerald: slate reads as gray at chart scale, and rose and
 * emerald are the reserved SIF verdict colours everywhere else in the UI, so reusing either here
 * would imply a verdict this chart is not making.
 *
 * EVERY VALUE IS DIRECT-LABELLED, so no number on this chart requires a hover to read - which is
 * also what makes the zero rules legible rather than merely honest.
 */

import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { RuleCount } from "@/lib/api_client";

/** Tailwind blue-700. Validated against a white surface: inside the OKLCH lightness band, above
 * the chroma floor, and over 3:1 contrast. */
const BAR_COLOR = "#1d4ed8";

const AXIS_COLOR = "#94a3b8";
const GRID_COLOR = "#e2e8f0";

/** Long rule names need a wide category gutter; 172px fits "Safe Mechanical Lifting" unwrapped. */
const LABEL_GUTTER = 172;

/** Per bar, so nine rules get a chart tall enough to breathe rather than nine crushed slivers. */
const ROW_HEIGHT = 34;
const AXIS_BAND = 44;

export function RuleDistributionChart({ rules }: { rules: RuleCount[] }) {
  const total = rules.reduce((sum, rule) => sum + rule.report_count, 0);

  // With no tagged reports at all, every bar is zero and the chart is nine labels against an empty
  // axis - technically honest, but it reads as broken. The sentence says what the chart would show.
  if (total === 0) {
    return (
      <div className="rounded border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-600">
          No report has been tagged against any Life-Saving Rule yet, so all nine counts are zero.
          The chart appears here once the first tagged report is processed.
        </p>
        <ul className="mt-3 grid gap-x-6 gap-y-1 text-sm text-slate-500 sm:grid-cols-2">
          {rules.map((rule) => (
            <li key={rule.rule_name}>{rule.rule_name} — 0</li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      {/* Height is computed from the row count plus the axis band, so the x-axis labels are inside
          the container and the card never grows a nested scrollbar. */}
      <ResponsiveContainer width="100%" height={rules.length * ROW_HEIGHT + AXIS_BAND}>
        <BarChart data={rules} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 0 }}>
          {/* Vertical rules only: horizontal lines between bars would box each one in. */}
          <CartesianGrid horizontal={false} stroke={GRID_COLOR} />
          <XAxis
            type="number"
            allowDecimals={false}
            tick={{ fill: "#475569", fontSize: 12 }}
            stroke={AXIS_COLOR}
          />
          <YAxis
            type="category"
            dataKey="rule_name"
            width={LABEL_GUTTER}
            tick={{ fill: "#334155", fontSize: 12 }}
            stroke={AXIS_COLOR}
          />
          <Tooltip
            // Recharts types the incoming value as possibly undefined, so it is coerced rather
            // than annotated as a number - `report_count` is an int on every row this chart draws.
            formatter={(value) => {
              const count = Number(value);
              return [`${count} report${count === 1 ? "" : "s"}`, "Tagged"];
            }}
            contentStyle={{ fontSize: 12, borderRadius: 4, border: `1px solid ${GRID_COLOR}` }}
          />
          <Bar dataKey="report_count" fill={BAR_COLOR} radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false}>
            {/* The count sits outside the bar end, so a zero-length bar still shows its zero and no
                label is ever clipped by a bar too short to hold it. */}
            <LabelList dataKey="report_count" position="right" fill="#334155" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
