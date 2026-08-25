/**
 * Turns `cleaned_text` plus a list of `PrecursorOut` spans into a flat list of segments to render.
 *
 * WHY THIS IS A PURE FUNCTION IN ITS OWN FILE. It is the one piece of real logic in the frontend,
 * two pages render it (the Intake page's inline result and the Report Detail Magic View share one
 * renderer, which is why `backend/schemas.py` returns one shape for both), and it is checkable
 * without a browser - `precursor_spans_check.ts` asserts the invariant below on 20 cases.
 *
 * SLICING, NEVER REPLACEMENT. The offsets are cut out of the string in order. A `replace()` or a
 * regex over `entity_text` would match the wrong occurrence of a repeated word ("pipe" appearing
 * three times) and would shift every later offset by the length of whatever markup it inserted.
 *
 * THE INVARIANT: `segments.map(s => s.text).join("") === text`, always, for any span list at all -
 * including overlapping, reversed, negative and out-of-range offsets. The rendered report is the
 * report, character for character; a span list this function does not like loses a highlight, never
 * a character of text.
 *
 * OFFSETS ARE CODE POINTS, NOT UTF-16 UNITS. Python's `len()` and slicing count code points, so
 * that is what `span_start` / `span_end` mean. JavaScript's `String.prototype.slice` counts UTF-16
 * units, which differ the moment a non-BMP character (an emoji) appears - every later offset would
 * silently shift by one per surrogate pair and highlight the wrong words. `Array.from` splits by
 * code point, so slicing that array matches Python exactly. Devanagari is inside the BMP, so this
 * costs nothing today and is correct anyway if a report ever carries an emoji.
 */

import type { EntityType, PrecursorOut } from "./api_client";

/** One run of text. `entity` absent means plain, unhighlighted text. */
export interface ReportSegment {
  text: string;
  entity?: PrecursorOut;
}

export function buildReportSegments(text: string, precursors: PrecursorOut[]): ReportSegment[] {
  const characters = Array.from(text);

  // Defensive, in offset order. A span that cannot be sliced is dropped rather than clamped:
  // clamping invents a highlight over text the model never pointed at.
  const usable = precursors
    .filter(
      (span) =>
        Number.isInteger(span.span_start) &&
        Number.isInteger(span.span_end) &&
        span.span_start >= 0 &&
        span.span_end <= characters.length &&
        span.span_start < span.span_end,
    )
    // Same start: the longer span first, so the wider highlight wins and the span nested inside
    // it is the one dropped below. Dropping the wider one would leave its tail unhighlighted.
    .sort((a, b) => a.span_start - b.span_start || b.span_end - a.span_end);

  const segments: ReportSegment[] = [];
  let cursor = 0;

  for (const span of usable) {
    // Overlaps a span already emitted. Two highlights cannot own the same character without
    // duplicating it in the output, so the later one is dropped - it stays visible as plain text
    // or as part of the highlight that already covers it. The NER should not emit overlaps; this
    // is here so that a bad span list degrades to a missing colour, not to corrupted text.
    if (span.span_start < cursor) continue;

    // Skipped when spans are adjacent (`span_start === cursor`), so no empty segment is emitted.
    if (span.span_start > cursor) {
      segments.push({ text: characters.slice(cursor, span.span_start).join("") });
    }
    segments.push({ text: characters.slice(span.span_start, span.span_end).join(""), entity: span });
    cursor = span.span_end;
  }

  if (cursor < characters.length) {
    segments.push({ text: characters.slice(cursor).join("") });
  }
  return segments;
}

/** The four entity types, with everything the UI needs to render one honestly.
 *
 * COLOUR IS NEVER THE ONLY CHANNEL. Each type carries a distinct underline style as well as a
 * distinct colour, and `label` names it in words in the legend and in the precursor list, so a
 * colourblind reader distinguishes them by line style and by name. `screenReaderLabel` is what a
 * screen reader announces around the highlighted run.
 *
 * `barrier_failure` spans are deliberately sparse in our data (`DECISIONS.md`), so a report with
 * only three of the four types is the NORMAL case. The legend renders all four regardless, with
 * the absent ones marked "none in this report" - a legend that changed shape per report would
 * teach a reader that a missing colour means a missing feature.
 */
export const ENTITY_STYLES: Record<
  EntityType,
  { label: string; abbreviation: string; screenReaderLabel: string; mark: string; swatch: string }
> = {
  activity: {
    label: "Activity",
    abbreviation: "ACT",
    screenReaderLabel: "activity precursor",
    mark: "bg-sky-100 text-sky-950 decoration-sky-700 decoration-solid",
    swatch: "bg-sky-100 border-sky-700 border-b-2 border-solid",
  },
  location: {
    label: "Location",
    abbreviation: "LOC",
    screenReaderLabel: "location precursor",
    mark: "bg-amber-100 text-amber-950 decoration-amber-700 decoration-dashed",
    swatch: "bg-amber-100 border-amber-700 border-b-2 border-dashed",
  },
  equipment: {
    label: "Equipment",
    abbreviation: "EQP",
    screenReaderLabel: "equipment precursor",
    mark: "bg-violet-100 text-violet-950 decoration-violet-700 decoration-dotted",
    swatch: "bg-violet-100 border-violet-700 border-b-2 border-dotted",
  },
  barrier_failure: {
    label: "Barrier failure",
    abbreviation: "BAR",
    screenReaderLabel: "barrier failure precursor",
    mark: "bg-rose-100 text-rose-950 decoration-rose-700 decoration-double",
    swatch: "bg-rose-100 border-rose-700 border-b-4 border-double",
  },
};

export const ENTITY_TYPES = Object.keys(ENTITY_STYLES) as EntityType[];
