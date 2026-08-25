/**
 * Self-check for `buildReportSegments`. Run it: `node lib/precursor_spans_check.ts` from
 * `frontend/` (Node 22.6+ strips the types; there is no test framework in this project yet).
 *
 * It exists because span slicing is the one place in the frontend where a bug corrupts the text a
 * judge is reading rather than merely misplacing a colour, and because the malformed cases below -
 * overlaps, reversed offsets, out-of-range offsets - cannot be produced on demand from the real
 * NER. Every case asserts the invariant from the module docstring: the segments rejoin to exactly
 * the original string.
 */

import { buildReportSegments } from "./precursor_spans.ts";
import type { EntityType, PrecursorOut } from "./api_client.ts";

function span(start: number, end: number, text: string, type: EntityType = "activity"): PrecursorOut {
  return { entity_type: type, entity_text: text, span_start: start, span_end: end };
}

/** Rejoined text is identical, and every highlighted segment's text matches the offsets it came
 * from - the same invariant `AUDIT.md` records for the backend (`text[start:end] == entity_text`). */
function check(label: string, text: string, precursors: PrecursorOut[], expectedHighlights: number) {
  const segments = buildReportSegments(text, precursors);
  const rejoined = segments.map((segment) => segment.text).join("");
  if (rejoined !== text) {
    throw new Error(`${label}: text corrupted\n  expected: ${JSON.stringify(text)}\n  got:      ${JSON.stringify(rejoined)}`);
  }
  const highlights = segments.filter((segment) => segment.entity);
  if (highlights.length !== expectedHighlights) {
    throw new Error(`${label}: expected ${expectedHighlights} highlights, got ${highlights.length}`);
  }
  if (segments.some((segment) => segment.text === "")) {
    throw new Error(`${label}: emitted an empty segment`);
  }
  const characters = Array.from(text);
  for (const segment of highlights) {
    const sliced = characters.slice(segment.entity!.span_start, segment.entity!.span_end).join("");
    if (sliced !== segment.text) {
      throw new Error(`${label}: highlight text does not match its offsets`);
    }
  }
  return segments;
}

const REPORT = "Welder was cutting pipe at height near the derrick without a harness.";

// The ordinary cases.
check("zero spans", REPORT, [], 0);
check("one span", REPORT, [span(0, 6, "Welder")], 1);
check("span at the very start", REPORT, [span(0, 6, "Welder", "activity")], 1);
check("span at the very end", REPORT, [span(61, 68, "harness", "equipment")], 1);
check("whole string is one span", REPORT, [span(0, Array.from(REPORT).length, REPORT)], 1);
check("three types, sorted input", REPORT, [
  span(11, 23, "cutting pipe", "activity"),
  span(27, 33, "height", "location"),
  span(61, 68, "harness", "equipment"),
], 3);

// Unsorted input must sort, not corrupt.
check("unsorted input", REPORT, [
  span(61, 68, "harness", "equipment"),
  span(11, 23, "cutting pipe", "activity"),
  span(27, 33, "height", "location"),
], 3);

// Adjacent spans must not emit an empty segment between them.
const adjacent = check("adjacent spans", REPORT, [span(0, 6, "Welder"), span(6, 10, " was")], 2);
if (adjacent[0].text !== "Welder" || adjacent[1].text !== " was") {
  throw new Error("adjacent spans: boundaries drifted");
}

// A repeated substring is the case string replacement gets wrong: only the SECOND "pipe" is
// tagged here, and slicing must highlight that one, not the first.
const repeated = "pipe near pipe";
const repeatedSegments = check("repeated substring", repeated, [span(10, 14, "pipe", "equipment")], 1);
if (repeatedSegments[0].text !== "pipe near " || repeatedSegments[1].text !== "pipe") {
  throw new Error("repeated substring: highlighted the wrong occurrence");
}

// Malformed span lists: a highlight may be lost, a character may not.
check("overlapping spans", REPORT, [span(0, 10, "Welder was"), span(4, 15, "er was cutt")], 1);
check("nested span inside a wider one", REPORT, [span(0, 10, "Welder was"), span(0, 6, "Welder")], 1);
check("duplicate identical spans", REPORT, [span(0, 6, "Welder"), span(0, 6, "Welder")], 1);
check("reversed offsets", REPORT, [span(20, 5, "nonsense")], 0);
check("zero-width span", REPORT, [span(7, 7, "")], 0);
check("negative start", REPORT, [span(-3, 6, "Welder")], 0);
check("end past the string", REPORT, [span(61, 9_999, "harness")], 0);
check("non-integer offsets", REPORT, [span(1.5, 6, "elder")], 0);
check("empty text with a span", "", [span(0, 4, "none")], 0);

// Offsets are Python code points, so a non-BMP character must not shift later spans. In UTF-16
// the flag is 4 units and "pipe" would start at 8; by code point it starts at 6, which is what
// Python reported. Getting this wrong highlights "ipe " instead.
const withEmoji = "ok 🇮🇳 pipe";
const emojiSegments = check("non-BMP characters", withEmoji, [span(6, 10, "pipe", "equipment")], 1);
if (emojiSegments.find((segment) => segment.entity)!.text !== "pipe") {
  throw new Error("non-BMP characters: code point offsets were treated as UTF-16 units");
}

// Devanagari, since real reports are mixed-script.
const hindi = "पाइप काटना";
check("devanagari", hindi, [span(0, 4, "पाइप", "equipment")], 1);

console.log("precursor_spans self-check: 20/20 cases passed");
