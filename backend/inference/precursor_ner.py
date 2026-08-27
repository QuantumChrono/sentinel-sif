"""Precursor entity extraction. One public function, `extract_precursors`.

THE SIGNATURE IS FROZEN (`STAGES.md` § FROZEN files):
`extract_precursors(text) -> list[(entity_type, entity_text, span_start, span_end)]`.

THE SPAN INVARIANT IS THE WHOLE POINT OF THIS FILE. `text[span_start:span_end] == entity_text`
holds for every tuple returned, and it holds BY CONSTRUCTION rather than by care: `entity_text`
is never assembled or copied from a pattern, it is always sliced back out of the exact string
that was passed in. This is the explainability mechanism in `PRD.md` § ML pipeline detail - the
Report Detail view highlights `cleaned_text` directly from these offsets, so an off-by-one is
visible on a projector. spaCy's `start_char`/`end_char` are Python string indices, so the slice
and the offsets cannot disagree even on astral-plane characters.

SPANS NEVER OVERLAP. The highlighter wraps each span in its own element, so two overlapping
spans would produce nested or interleaved markup and render wrong. `_resolve_overlaps` keeps the
longest match at each position and drops anything crossing it - the same policy
`scripts/build_ner_ruler.py` measures its "resolved" numbers under, so the metrics below predict
what this function actually serves.

WHY THIS IS A SPANRULER AND NOT A STATISTICAL NER. `scripts/build_ner_ruler.py` mines all 111
patterns from the gold spans in `data/processed/train.jsonl` - vocabulary kept at count >= 2,
nothing hand-written except the barrier anchors. A 277-row corpus does not support training a
statistical NER, and a gazetteer mined from the corpus is honest about being one.

=== WHAT THESE PATTERNS SCORE, FROM `ruler_metrics.json` =================================
Held-out test, AFTER overlap resolution - the numbers that describe what the pipeline serves.
Overlap F1 is the metric the Magic View depends on (a highlight covering "bench grinder"
instead of "10-inch bench grinder" is useful; exact-boundary F1 punishes it as a miss):

  location          overlap F1 0.69   exact F1 0.19
  activity          overlap F1 0.61   exact F1 0.13
  equipment         overlap F1 0.23   exact F1 0.00   - weak, and the weakest of the four
  barrier_failure   overlap F1 0.20   exact F1 0.00   - capped by the corpus, see below

BARRIER_FAILURE IS SPARSE ON PURPOSE AND ITS RECALL IS CAPPED NEAR 49% BY CONSTRUCTION.
`DECISIONS.md` ("Barrier spans sourced by entailment only") establishes that OSHA narratives
record what happened, not which control was missing. Of the 49 barrier spans in the training
file only 24 contain an absence word a pattern can match; the other 25 are pure entailment
("it remained energized") where the failed control is named nowhere in the sentence. No pattern
can match those without inventing the control, which is the one output that decision forbids
outright. Returning three of the four entity types is therefore the NORMAL case here, not a
failure, and this module must never invent a barrier to fill the gap: a fabricated cause is the
worst output a safety model can produce.
========================================================================================
"""

from functools import lru_cache
from pathlib import Path

import spacy

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "model_weights" / "precursor_ner"

MODEL_VERSION = "spacy-spanruler-1.0"

# The key `build_ner_ruler.py` writes its spans under. spaCy puts SpanRuler output in
# `doc.spans[key]`, not `doc.ents`, which is what lets it hold the overlapping spans this
# corpus is full of (160 of 277 train rows carry an overlapping gold pair).
SPANS_KEY = "precursors"


@lru_cache(maxsize=1)
def _ruler():
    """Load the pipeline once, on first call, and keep it. Same lazy-load reasoning as the two
    transformer heads, though this one is cheap: a blank English pipeline plus 111 patterns, no
    weights to read and no model to download."""
    return spacy.load(WEIGHTS_DIR)


def _resolve_overlaps(found: list[tuple[str, str, int, int]]) -> list[tuple[str, str, int, int]]:
    """Longest match wins; anything crossing an accepted span is dropped.

    This also subsumes the nested-duplicate problem `build_ner_ruler.py` handles separately: a
    quantified pattern matches at every length it can, so one activity span comes back as the
    whole nested ladder of its own prefixes. Every one of those overlaps the longest match, so
    keeping longest-first drops them here without a second pass. The build script needs both
    because it reports raw pre-resolution metrics; this module only ever serves resolved spans.
    """
    kept: list[tuple[str, str, int, int]] = []
    for entity in sorted(found, key=lambda f: (-(f[3] - f[2]), f[2])):
        if not any(entity[2] < other[3] and other[2] < entity[3] for other in kept):
            kept.append(entity)
    return sorted(kept, key=lambda f: f[2])


def extract_precursors(text: str) -> list[tuple[str, str, int, int]]:
    """Return [(entity_type, entity_text, span_start, span_end)], non-overlapping, in text order.

    FROZEN SIGNATURE. `text[span_start:span_end] == entity_text` for every tuple returned.
    An empty list is valid, and three of the four entity types is the normal case.
    """
    if not text or not text.strip():
        return []

    doc = _ruler()(text)
    # `dict.fromkeys` drops exact duplicates: two patterns of the same type can match the
    # identical span ("pipe" is both a mined modifier and a mined head), and the same span
    # returned twice would render two stacked highlights over one phrase.
    found = list(dict.fromkeys(
        (span.label_, text[span.start_char:span.end_char], span.start_char, span.end_char)
        for span in doc.spans[SPANS_KEY]))
    return _resolve_overlaps(found)
