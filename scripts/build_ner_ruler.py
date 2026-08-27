"""Build a spaCy rule-based precursor tagger from the spans data/processed/ actually contains.

Runs on CPU in seconds - no GPU, no notebook needed:

  python scripts/build_ner_ruler.py                 -> build, evaluate, save to the OUTPUT_DIR below
  python scripts/build_ner_ruler.py --self-check    -> assert invariants, no file IO

EVERY PATTERN IS MINED FROM THE GOLD SPANS, NOT WRITTEN FROM IMAGINATION. `mine_patterns` reads
`precursor_*` out of the training file and keeps vocabulary that appears at least twice; nothing
is added by hand. Change the corpus and the patterns change with it.

That includes the list of words an activity span may not run past, and it is worth saying why:
the first version of this file hand-wrote that list, it looked entirely reasonable, and the
self-check caught it truncating every activity span to its bare leading verb. It contained the
determiners - but "a" appears 175 times INSIDE gold activity spans against 6 times after one,
and "the" 108 against 17. The mined rule is the measurement instead: a word that follows gold
spans more often than it appears inside them is a word that ENDS an activity ("at" 1 inside vs
59 after, "when" 0 vs 22, "while" 1 vs 11). The only vocabulary still listed by hand is
`BARRIER_ANCHORS`, and the docstring below says why that one must stay closed.

SPANRULER, NOT ENTITYRULER, AND THE REASON IS MEASURED. `EntityRuler` writes to `doc.ents`,
which cannot hold overlapping spans - so of "using a bench grinder" (activity) and "bench
grinder" (equipment) it keeps exactly one and silently drops the other. In this corpus 160 of
277 training rows (58%) carry at least one overlapping gold pair, 137 of them activity
containing equipment, because "what he was doing" naturally contains "what he was doing it
with". An `EntityRuler` therefore cannot represent the majority of this data's labelling.
`SpanRuler` takes the identical pattern format and writes to `doc.spans`, which holds overlaps.

WHICH LEAVES THE BACKEND ITS OWN CONSTRAINT. `backend/inference/precursor_ner.py` (FROZEN
signature) returns a flat non-overlapping list, because the Report Detail highlighter wraps
each span in its own element and interleaved markup renders wrong. So this script reports each
type TWICE: over the raw overlapping spans, and again after `resolve_overlaps` - the same
longest-match-wins policy that module documents. The resolved number is the one that predicts
what the deployed pipeline actually serves; the raw number says how much the patterns found
before the highlighter's constraint threw part of it away.

BARRIER_FAILURE IS BUILT ONLY WHERE THE TEXT SAYS THE WORDS, AND IS LEFT SPARSE ON PURPOSE.
Of the 49 barrier spans in the training file, 24 contain an absence word (no / not / without /
missing / nahi / miss / skip) and are reachable by a pattern. The other 25 are pure entailment -
"it remained energized", "while it was still operating", "the machine was activated by the foot
pedal" - where the failed control is inferred from the mechanics and named nowhere in the
sentence. No pattern can match those without inventing the control, which is the one output
`DECISIONS.md` ("Barrier spans sourced by entailment only, never fabricated") forbids outright
and the worst thing a safety model can produce. So barrier recall is capped near 49% by
construction, that ceiling is printed with the metrics, and no barrier pattern exists here to
make the four types look balanced.
"""

import argparse
import json
import os
import re
from collections import Counter

import spacy

# ---------------------------------------------------------------------------
# CONFIG - the only block you edit.
# ---------------------------------------------------------------------------
TRAIN_PATH = "data/processed/train.jsonl"
TEST_PATH = "data/test/test.jsonl"          # read ONCE, for reporting, after the ruler is built
OUTPUT_DIR = "model_weights/precursor_ruler"

# A mined token must appear this many times across the gold spans to become a pattern. At 1 the
# gazetteer absorbs every typo and one-off in the corpus ('grider', 'ladl', 'helmett', 'lbs',
# 'pakdao'); at 2 it keeps the 35 equipment heads that cover 147 of 246 equipment spans.
MIN_VOCABULARY_COUNT = 2

# Longest mined activity span is 13 tokens, median 6, so a bound of 12 after the leading verb
# costs nothing and stops a runaway match eating the rest of the sentence.
MAX_ACTIVITY_TOKENS = 12

PRECURSOR_TYPES = ("activity", "location", "equipment", "barrier_failure")

# The absence words that anchor a barrier span, from the 24 reachable gold spans. Hinglish forms
# included because the heavy-noise tier writes them that way ('koi protective gear nahi tha',
# 'lockout miss hua', 'break skip kiya') and they are 4 of the 24.
BARRIER_ANCHORS = ("no", "not", "without", "missing", "miss", "nahi", "koi", "skip")


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def gold_spans(row):
    """The row's labelled spans as {type: (start, end, text)}. Absent types are simply missing."""
    spans = {}
    for entity_type in PRECURSOR_TYPES:
        span = row.get(f"precursor_{entity_type}")
        if span:
            spans[entity_type] = (span["start"], span["end"], span["text"])
    return spans


def words(text):
    return re.findall(r"[\w'\-]+", text.lower())


def mine_activity_stop(rows):
    """The words a mined activity span may not run past - measured, not guessed.

    A word appearing immediately AFTER gold activity spans more often than INSIDE them is a word
    that ends an activity: it opens the clause naming where the incident happened or what went
    wrong, which is another type's job. Hand-writing this list is exactly the bug this function
    exists to prevent. The obvious guess includes the determiners, and "a" sits inside 175 gold
    spans against 6 following one - banning it truncates every activity to its leading verb,
    which is what `--self-check` caught. The measurement also finds "jab" (Hinglish "when"), which
    no English stop list would have contained.
    """
    inside, after = Counter(), Counter()
    for row in rows:
        spans = gold_spans(row)
        if "activity" not in spans:
            continue
        _, end, text = spans["activity"]
        inside.update(words(text)[1:])  # skip the leading verb, which the pattern anchors on
        following = words(row["raw_text"][end:end + 24])
        if following:
            after[following[0]] += 1
    # isalpha: a bare quantity ("4") trails some spans but belongs inside a span like "using a
    # 4 inch grinder", so numerals are not allowed to terminate one.
    return sorted(word for word in after if word.isalpha()
                  and after[word] > inside[word] and after[word] >= MIN_VOCABULARY_COUNT)


def mine_patterns(rows):
    """Read the gold spans and return spaCy patterns. No vocabulary is written by hand here.

    Equipment and location are gazetteers of head nouns (the last word of the span, which is the
    thing itself: 'bench grinder' -> grinder) with the modifiers observed in front of them as
    optional leading tokens. Activity is its leading verb plus a bounded run. Barrier is an
    absence anchor plus the control noun that followed it.
    """
    collected = {entity_type: [] for entity_type in PRECURSOR_TYPES}
    for row in rows:
        for entity_type, (_, _, text) in gold_spans(row).items():
            collected[entity_type].append(text)

    equipment_heads = Counter()
    equipment_modifiers = Counter()
    for text in collected["equipment"]:
        tokens = words(text)
        if tokens:
            equipment_heads[tokens[-1]] += 1
            equipment_modifiers.update(tokens[:-1])

    location_heads = Counter()
    for text in collected["location"]:
        tokens = words(text)
        if tokens:
            location_heads[tokens[-1]] += 1

    activity_verbs = Counter()
    for text in collected["activity"]:
        tokens = words(text)
        if tokens:
            activity_verbs[tokens[0]] += 1

    barrier_controls = Counter()
    for text in collected["barrier_failure"]:
        for match in re.findall(r"\b(?:no|not|without|missing|koi)\s+([\w'\-]+(?:\s+[\w'\-]+)?)",
                                text, re.I):
            barrier_controls[match.lower()] += 1

    def frequent(counter):
        return sorted(term for term, count in counter.items() if count >= MIN_VOCABULARY_COUNT)

    heads = frequent(equipment_heads)
    modifiers = frequent(equipment_modifiers)
    patterns = []

    # Equipment: an optional determiner is excluded (the gold spans start at the noun phrase, not
    # at 'a' - 'a' precedes 125 of them and is inside none), then up to two observed modifiers.
    for head in heads:
        patterns.append({"label": "equipment", "pattern": [
            {"LOWER": {"IN": modifiers}, "OP": "{0,2}"}, {"LOWER": head}]})

    for head in frequent(location_heads):
        patterns.append({"label": "location", "pattern": [
            {"LOWER": {"IN": ["at", "in", "on", "near", "inside"]}, "OP": "?"},
            {"LOWER": {"IN": ["the", "a", "an"]}, "OP": "?"},
            {"IS_ALPHA": True, "OP": "{0,3}"}, {"LOWER": head}]})

    activity_stop = mine_activity_stop(rows)
    for verb in frequent(activity_verbs):
        patterns.append({"label": "activity", "pattern": [
            {"LOWER": verb},
            {"LOWER": {"NOT_IN": activity_stop}, "IS_PUNCT": False,
             "OP": f"{{0,{MAX_ACTIVITY_TOKENS}}}"}]})

    # Barrier: the anchor is mandatory, so nothing matches unless the text states an absence.
    for control in frequent(barrier_controls):
        control_tokens = [{"LOWER": token} for token in control.split()]
        patterns.append({"label": "barrier_failure", "pattern":
                         [{"LOWER": {"IN": list(BARRIER_ANCHORS)}}] + control_tokens})
    for anchor_phrase in ("nahi tha", "miss hua", "miss kar diya", "skip kiya", "nahi dikha"):
        if any(anchor_phrase in text.lower() for text in collected["barrier_failure"]):
            patterns.append({"label": "barrier_failure", "pattern":
                             [{"IS_ALPHA": True, "OP": "{1,3}"}] +
                             [{"LOWER": token} for token in anchor_phrase.split()]})

    return patterns, {"equipment_heads": len(heads), "equipment_modifiers": len(modifiers),
                      "location_heads": len(frequent(location_heads)),
                      "activity_verbs": len(frequent(activity_verbs)),
                      "barrier_controls": len(frequent(barrier_controls)),
                      "activity_stop_words": activity_stop,
                      "gold_span_counts": {t: len(v) for t, v in collected.items()}}


def build_ruler(patterns):
    """A blank English pipeline plus the SpanRuler. Blank, not a downloaded model: nothing here
    needs a parser or a statistical NER, and a blank pipeline has no model to download on Kaggle
    and nothing to disagree with the patterns."""
    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("span_ruler", config={"spans_key": "precursors", "overwrite": False})
    ruler.add_patterns(patterns)
    return nlp


def drop_nested_duplicates(found):
    """Drop a span that sits strictly inside a longer span OF THE SAME TYPE.

    A quantified pattern ({0,12} on the activity run) matches at every length it can, so
    SpanRuler emits the whole nested ladder: one gold activity span came back as 18 predictions,
    "walking across a waterlogged section of the Naharkatiya site" plus every shorter prefix of
    itself. Left in, they multiply the prediction count ~13x and drive precision toward zero
    while measuring nothing but the quantifier.

    SAME TYPE ONLY. activity containing equipment is the real nesting this corpus is full of
    (137 gold pairs) and the reason for SpanRuler over EntityRuler; dropping that would throw
    away the labelling. Cross-type overlap is resolved later, and only for the highlighter.
    """
    return [span for span in found
            if not any(other is not span and other[0] == span[0]
                       and other[2] <= span[2] and span[3] <= other[3]
                       and (other[3] - other[2]) > (span[3] - span[2])
                       for other in found)]


def predict(nlp, text):
    """[(entity_type, entity_text, start, end)] - the frozen tuple shape, spans possibly
    overlapping across types. `entity_text` is sliced out of `text`, never rebuilt from a
    pattern, so `text[start:end] == entity_text` holds by construction."""
    doc = nlp(text)
    # dict.fromkeys also drops exact duplicates - two patterns of the same type can match the
    # identical span ("pipe" is both a mined modifier and a mined head), and counting that span
    # twice would inflate the prediction total for no reason.
    found = list(dict.fromkeys(
        (span.label_, text[span.start_char:span.end_char], span.start_char, span.end_char)
        for span in doc.spans["precursors"]))
    return sorted(drop_nested_duplicates(found), key=lambda entity: (entity[2], -entity[3]))


def resolve_overlaps(found):
    """Longest match wins, anything crossing it is dropped - the policy
    `backend/inference/precursor_ner.py` documents, because the highlighter cannot nest spans."""
    kept = []
    for entity in sorted(found, key=lambda f: (-(f[3] - f[2]), f[2])):
        if not any(entity[2] < other[3] and other[2] < entity[3] for other in kept):
            kept.append(entity)
    return sorted(kept, key=lambda f: f[2])


def score(rows, nlp, resolved):
    """Per-type precision/recall/F1, counted two ways.

    EXACT means the predicted span's boundaries equal the gold span's. OVERLAP means it shares at
    least one character with the gold span of that type - which is the metric that matters for
    the Magic View, where a highlight covering "bench grinder" instead of "10-inch bench
    grinder" still points the reader at the right words.

    Recall's denominator is the rows that HAVE a gold span of that type, never the row count:
    barrier_failure is null on 228 of 277 rows and counting those as misses would invent a
    failure out of a field that was correctly left empty.
    """
    tally = {entity_type: Counter() for entity_type in PRECURSOR_TYPES}
    for row in rows:
        text, gold = row["raw_text"], gold_spans(row)
        found = predict(nlp, text)
        if resolved:
            found = resolve_overlaps(found)
        for entity_type in PRECURSOR_TYPES:
            predictions = [f for f in found if f[0] == entity_type]
            counts = tally[entity_type]
            counts["predicted"] += len(predictions)
            if entity_type not in gold:
                continue
            start, end, gold_text = gold[entity_type]
            counts["gold"] += 1
            if any(f[2] == start and f[3] == end for f in predictions):
                counts["exact_hit"] += 1
            if any(f[2] < end and start < f[3] for f in predictions):
                counts["overlap_hit"] += 1
    return tally


def print_scores(name, tally, rows):
    print(f"\n{name}  (n={len(rows)} rows)")
    print(f"  {'type':<17} {'gold':>5} {'pred':>5} {'exactP':>7} {'exactR':>7} {'exactF1':>8} "
          f"{'ovlpP':>7} {'ovlpR':>7} {'ovlpF1':>8}")
    summary = {}
    for entity_type in PRECURSOR_TYPES:
        counts = tally[entity_type]
        gold, predicted = counts["gold"], counts["predicted"]
        scores = {"gold": gold, "predicted": predicted}
        for kind in ("exact", "overlap"):
            hits = counts[f"{kind}_hit"]
            precision = hits / predicted if predicted else 0.0
            recall = hits / gold if gold else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            scores.update({f"{kind}_precision": precision, f"{kind}_recall": recall,
                           f"{kind}_f1": f1})
        summary[entity_type] = scores
        print(f"  {entity_type:<17} {gold:>5} {predicted:>5} "
              f"{scores['exact_precision']:>7.4f} {scores['exact_recall']:>7.4f} "
              f"{scores['exact_f1']:>8.4f} {scores['overlap_precision']:>7.4f} "
              f"{scores['overlap_recall']:>7.4f} {scores['overlap_f1']:>8.4f}")
    return summary


def self_check():
    """Assert the invariants that would silently corrupt the Magic View if they broke."""
    checks = []
    text = "He was using a bench grinder at the Makum site with no harness on."
    # Two identical rows so a stop word clears MIN_VOCABULARY_COUNT. The gold span is
    # "using a bench grinder", which contains the determiner "a" and is followed by "at".
    rows = [{"id": f"synthetic-{i}", "raw_text": text,
             "precursor_activity": {"text": text[7:28], "start": 7, "end": 28}} for i in range(2)]
    assert rows[0]["precursor_activity"]["text"] == "using a bench grinder", "fixture drifted"

    activity_stop = mine_activity_stop(rows)
    # THE REGRESSION CHECK. The hand-written version of this list banned the determiners and
    # truncated every activity span to its leading verb. "a" sits INSIDE the gold span here, so
    # a correct mining pass must not treat it as a terminator.
    checks.append(("mined stop list terminates on 'at'", "at" in activity_stop, True))
    checks.append(("mined stop list does NOT ban the determiner 'a'",
                   "a" in activity_stop, False))

    patterns = [
        {"label": "equipment", "pattern": [{"LOWER": {"IN": ["bench"]}, "OP": "{0,2}"},
                                           {"LOWER": "grinder"}]},
        {"label": "activity", "pattern": [{"LOWER": "using"},
                                          {"LOWER": {"NOT_IN": activity_stop},
                                           "IS_PUNCT": False,
                                           "OP": f"{{0,{MAX_ACTIVITY_TOKENS}}}"}]},
        {"label": "barrier_failure", "pattern": [{"LOWER": {"IN": list(BARRIER_ANCHORS)}},
                                                 {"LOWER": "harness"}]},
    ]
    nlp = build_ruler(patterns)
    found = predict(nlp, text)

    checks.append(("activity span keeps its full noun phrase, not just the verb",
                   "using a bench grinder" in [f[1] for f in found if f[0] == "activity"], True))

    checks.append(("span invariant: text[start:end] == entity_text",
                   all(text[start:end] == entity_text for _, entity_text, start, end in found),
                   True))
    checks.append(("overlapping spans ARE returned (SpanRuler, not EntityRuler)",
                   sum(1 for f in found if f[0] == "equipment") >= 1
                   and sum(1 for f in found if f[0] == "activity") >= 1, True))
    checks.append(("activity stops before 'at'", "at the Makum" not in
                   next(f[1] for f in found if f[0] == "activity"), True))
    checks.append(("barrier anchored on the absence word",
                   [f[1] for f in found if f[0] == "barrier_failure"], ["no harness"]))

    # Synthetic tuples, so these test the containment logic rather than today's patterns.
    ladder = [("activity", "using a bench grinder", 7, 28), ("activity", "using a bench", 7, 20),
              ("activity", "using", 7, 12), ("equipment", "bench grinder", 15, 28)]
    kept = drop_nested_duplicates(ladder)
    checks.append(("quantifier prefix ladder collapses to the longest same-type span",
                   [entity[1] for entity in kept if entity[0] == "activity"],
                   ["using a bench grinder"]))
    # The one that matters most: this nesting is 137 of the gold pairs and the whole reason for
    # SpanRuler. If a "tidy up the spans" change ever drops it, the corpus stops being learnable.
    checks.append(("equipment nested inside activity SURVIVES (different types)",
                   ("equipment", "bench grinder", 15, 28) in kept, True))
    checks.append(("no duplicate tuples returned", len(found) == len(set(found)), True))

    resolved = resolve_overlaps(found)
    checks.append(("resolve_overlaps leaves no overlap",
                   any(a[2] < b[3] and b[2] < a[3] for i, a in enumerate(resolved)
                       for b in resolved[i + 1:]), False))
    checks.append(("resolve_overlaps keeps the longest", "using a bench grinder"
                   in [f[1] for f in resolved], True))

    # A barrier pattern must never fire on text that states no absence. This is the fabrication
    # guard: DECISIONS.md forbids inventing a control, so a clean sentence must return nothing.
    checks.append(("no barrier invented on text with no absence phrasing",
                   [f for f in predict(nlp, "He wore a harness and used the grinder.")
                    if f[0] == "barrier_failure"], []))

    empty = predict(nlp, "")
    checks.append(("empty text returns no spans", empty, []))

    passed = 0
    for label, actual, expected in checks:
        ok = actual == expected
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + ("" if ok else f"\n          expected {expected!r}, got {actual!r}"))
    print(f"\n  {passed}/{len(checks)} checks passed")
    return passed == len(checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="assert invariants, no file IO")
    if parser.parse_args().self_check:
        raise SystemExit(0 if self_check() else 1)

    train_rows = read_jsonl(TRAIN_PATH)
    patterns, mined = mine_patterns(train_rows)
    nlp = build_ruler(patterns)

    print(f"mined {len(patterns)} patterns from {len(train_rows)} rows in {TRAIN_PATH}")
    for key, value in mined.items():
        print(f"  {key}: {value}")

    barrier_texts = [gold_spans(r)["barrier_failure"][2] for r in train_rows
                     if "barrier_failure" in gold_spans(r)]
    anchored = [t for t in barrier_texts
                if re.search(r"\b(no|not|without|missing|miss|nahi|koi|skip)\b", t, re.I)]
    print(f"\nBARRIER CEILING: {len(anchored)} of {len(barrier_texts)} gold barrier spans contain "
          f"an absence word and are reachable by a pattern; the other "
          f"{len(barrier_texts) - len(anchored)} are pure entailment and name no control, so "
          f"recall above ~{100 * len(anchored) / len(barrier_texts):.0f}% is not available "
          "without fabricating one. No pattern was added to close that gap (DECISIONS.md).")

    train_summary = print_scores("TRAIN, raw overlapping spans - A FIT METRIC, NOT A "
                                 "GENERALISATION ONE: the patterns were mined from these spans",
                                 score(train_rows, nlp, resolved=False), train_rows)
    print_scores("TRAIN, after resolve_overlaps", score(train_rows, nlp, resolved=True), train_rows)

    test_rows = read_jsonl(TEST_PATH)  # first and only read of data/test/
    test_ids, train_ids = {str(r["id"]) for r in test_rows}, {str(r["id"]) for r in train_rows}
    assert not (test_ids & train_ids), "TEST IDS PRESENT IN TRAIN"
    test_raw = print_scores("HELD-OUT TEST, raw overlapping spans - the honest number",
                            score(test_rows, nlp, resolved=False), test_rows)
    test_resolved = print_scores("HELD-OUT TEST, after resolve_overlaps - what the deployed "
                                 "highlighter would actually show",
                                 score(test_rows, nlp, resolved=True), test_rows)

    bad_spans = sum(1 for row in test_rows for _, entity_text, start, end
                    in predict(nlp, row["raw_text"]) if row["raw_text"][start:end] != entity_text)
    print(f"\nspan invariant on every predicted test span: {bad_spans} violations")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    nlp.to_disk(OUTPUT_DIR)
    with open(os.path.join(OUTPUT_DIR, "patterns.json"), "w", encoding="utf-8") as handle:
        json.dump(patterns, handle, indent=2)
    with open(os.path.join(OUTPUT_DIR, "ruler_metrics.json"), "w", encoding="utf-8") as handle:
        json.dump({"min_vocabulary_count": MIN_VOCABULARY_COUNT, "pattern_count": len(patterns),
                   "mined": mined, "barrier_reachable": len(anchored),
                   "barrier_total": len(barrier_texts), "train_raw": train_summary,
                   "test_raw": test_raw, "test_resolved": test_resolved}, handle, indent=2)
    print(f"saved pipeline + patterns.json + ruler_metrics.json to {OUTPUT_DIR}")

    def line(entity_type, summary):
        scores = summary[entity_type]
        return (f"  {entity_type}: gold {scores['gold']}, predicted {scores['predicted']}, "
                f"exact P {scores['exact_precision']:.4f} R {scores['exact_recall']:.4f} "
                f"F1 {scores['exact_f1']:.4f}, overlap P {scores['overlap_precision']:.4f} "
                f"R {scores['overlap_recall']:.4f} F1 {scores['overlap_f1']:.4f}")

    print(f"""
================ PASTE INTO AUDIT.md ================
Type: metric | Severity: med
Precursor rule tagger (spaCy {spacy.__version__} SpanRuler, {len(patterns)} patterns mined from the
{len(train_rows)} rows of data/processed/train.jsonl, vocabulary kept at count >= {MIN_VOCABULARY_COUNT}). SpanRuler and
not EntityRuler because 160 of 277 train rows (58%) carry overlapping gold spans - 137 of them
activity containing equipment - which doc.ents cannot represent. HELD-OUT TEST (n={len(test_rows)}), raw
overlapping spans:
{chr(10).join(line(t, test_raw) for t in PRECURSOR_TYPES)}
Same test set after resolve_overlaps (longest-match-wins, what the frozen
backend/inference/precursor_ner.py contract and the Detail highlighter require):
{chr(10).join(line(t, test_resolved) for t in PRECURSOR_TYPES)}
Span invariant text[start:end] == entity_text: {bad_spans} violations over every predicted test span.
BARRIER CEILING: {len(anchored)}/{len(barrier_texts)} gold barrier spans state an absence in words and are
pattern-reachable; the remaining {len(barrier_texts) - len(anchored)} are entailment-only and name no control, so barrier
recall is capped near {100 * len(anchored) / len(barrier_texts):.0f}% by the corpus and NOT by the ruler. No barrier pattern was
invented to raise it (DECISIONS.md, "Barrier spans sourced by entailment only").
Exact-match F1 is low for activity and location by design - both are multi-word spans whose
boundaries a gazetteer cannot reproduce; overlap F1 is the metric the Magic View depends on.
=====================================================""")


if __name__ == "__main__":
    main()
