import { buildReportSegments } from "../lib/precursor_spans";

const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/v1/reports?limit=50`);
if (!res.ok) throw new Error(`Failed to list reports: ${res.status}`);
const reports = await res.json();

let reportCount = 0;
let spanCount = 0;
let mismatchCount = 0;
let invariantBreaks = 0;

for (const r of reports) {
  const full = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/v1/reports/${r.id}`).then(res => res.json());
  reportCount++;
  const chars = Array.from(full.cleaned_text);
  for (const span of full.precursors) {
    spanCount++;
    const sliced = chars.slice(span.span_start, span.span_end).join("");
    if (sliced !== span.entity_text) {
      mismatchCount++;
      console.log("MISMATCH", r.id, span, "got:", sliced);
    }
  }
  const segments = buildReportSegments(full.cleaned_text, full.precursors);
  const rebuilt = segments.map(s => s.text).join("");
  if (rebuilt !== full.cleaned_text) {
    invariantBreaks++;
    console.log("INVARIANT BROKEN", r.id);
  }
}

console.log(`\n--- Summary ---`);
console.log(`Reports checked: ${reportCount}`);
console.log(`Spans checked: ${spanCount}`);
console.log(`Mismatches: ${mismatchCount}`);
console.log(`Invariant breaks: ${invariantBreaks}`);
console.log(mismatchCount === 0 && invariantBreaks === 0 ? "✅ ALL PASSED" : "❌ FAILURES FOUND");