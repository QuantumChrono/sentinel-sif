"""Backfill null precursor spans and missing IOGP tags on an existing checkpoint, offline.

Run by hand after localize_dataset.py, against its output. Re-runs ONLY that script's
stage 2 (extraction), against the Indian narrative already stored in each row. It never
re-rewrites prose: raw_text is read and never written, so every span already stored stays
valid and no row's SIF label can move.

FILL-ONLY, NEVER OVERWRITE. A null precursor is filled if the model finds one; an existing
span is left exactly as it is; iogp_rules are UNIONED with what comes back. The rows this
runs against were human-reviewed, and a re-extraction that replaced them would silently
discard that review to chase a coverage number. Losing a reviewed tag is worse than missing
a new one.

Resumable, because it will not finish in one sitting: the free-tier daily quota walls part
way through a few hundred rows. The whole file is rewritten after every row, and a re-run
skips rows that already have a barrier. Stopping early is the normal case, not an error.

Usage:
  python scripts/backfill_barriers.py --self-check     assert merge invariants, no IO
  python scripts/backfill_barriers.py --limit 5        5 rows, into data/scratch/
  python scripts/backfill_barriers.py --apply          update the checkpoint in place
"""

import argparse
import json
import os
import shutil

from dotenv import load_dotenv

from localize_dataset import (EXTRACT_ITEM, IOGP_RULES, PROMPT_EXTRACT, build_fleet,
                              call_llm_batch, find_span, to_ascii_punctuation)

PRECURSORS = ("activity", "location", "equipment", "barrier_failure")


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path, rows):
    """Write via a temp file and one atomic replace, so a crash cannot truncate the input."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temp = path + ".partial"
    with open(temp, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temp, path)


def merge_extraction(row, fields, union_tags=False):
    """Fill null precursors on one row, in place. Returns a list of what changed.

    The only place this script decides anything, which is what --self-check covers.

    Tags are NOT merged unless union_tags is set, and it defaults off because the tags this
    pass returns were measured to over-claim. On the 26-row top-up, `20161110769` (a grinder
    spark igniting fumes inside a fuel tank, from outside it) came back as Hot Work +
    Confined Space + Work Authorisation: only Hot Work is in the text. Nobody entered the
    tank, and neither the report nor its OSHA source mentions a permit - the model inferred
    that hot work on a tank requires one, so one must have been missing (AUDIT.md
    2026-08-26). Unioning that into reviewed rows would manufacture exactly the fabricated
    Work Authorisation examples DECISIONS.md refuses to create. Barriers are quoted
    substrings and fail closed when absent from the text; a tag has no such anchor.
    """
    changed = []
    for field in PRECURSORS:
        key = f"precursor_{field}"
        if row.get(key):
            continue  # reviewed value present - not ours to touch
        span = find_span(row["raw_text"], to_ascii_punctuation(fields.get(key)))
        if span:
            row[key] = span
            changed.append(field)

    if not union_tags:
        return changed
    returned = [r for r in fields.get("iogp_rules") or [] if r in IOGP_RULES]
    added = [r for r in returned if r not in (row.get("iogp_rules") or [])]
    if added:
        keep = set(row.get("iogp_rules") or []) | set(returned)
        row["iogp_rules"] = [r for r in IOGP_RULES if r in keep]
        changed += [f"+{r}" for r in added]
    rejected = [r for r in fields.get("iogp_rules") or [] if r not in IOGP_RULES]
    if rejected:
        row["iogp_rules_rejected"] = sorted(
            set(row.get("iogp_rules_rejected") or []) | set(rejected))
    return changed


def extract_one(fleet, row):
    """Stage 2 only, for one stored row. Same prompt, fleet and validation as generation."""
    item = EXTRACT_ITEM.format(index=1, event_title=row["osha_event_title"],
                               nature_title=row["osha_nature_title"], text=row["raw_text"])
    results, _, _ = call_llm_batch(
        fleet, PROMPT_EXTRACT.format(n=1, items=item, iogp_list=" | ".join(IOGP_RULES)), 1)
    return results[0]


def self_check():
    """Assert what the merge must never break, on synthetic rows. No IO, no API calls."""
    text = "The fitter was welding on the flange with no guard fitted at the Moran site."
    existing = {"text": "welding", "start": 15, "end": 22}

    def row(**over):
        return {"raw_text": text, "iogp_rules": ["Line of Fire"], "iogp_rules_rejected": [],
                **{f"precursor_{f}": None for f in PRECURSORS}, **over}

    checks = []
    one = row()
    merge_extraction(one, {"precursor_barrier_failure": "no guard fitted", "iogp_rules": []})
    span = one["precursor_barrier_failure"]
    checks.append(("null barrier filled", span["text"], "no guard fitted"))
    checks.append(("filled span round-trips", text[span["start"]:span["end"]], "no guard fitted"))

    one = row(precursor_barrier_failure=existing)
    merge_extraction(one, {"precursor_barrier_failure": "no guard fitted", "iogp_rules": []})
    checks.append(("existing span never overwritten", one["precursor_barrier_failure"], existing))

    one = row()
    merge_extraction(one, {"precursor_barrier_failure": "a control never written down"})
    checks.append(("quote absent from text stays null", one["precursor_barrier_failure"], None))

    # The default. A returned tag is dropped on the floor unless the caller asks for it,
    # because this pass was measured over-claiming Confined Space and Work Authorisation.
    one = row()
    changed = merge_extraction(one, {"iogp_rules": ["Hot Work"]})
    checks.append(("tags NOT merged by default", one["iogp_rules"], ["Line of Fire"]))
    checks.append(("unmerged tag not reported as a change", changed, []))

    one = row()
    merge_extraction(one, {"iogp_rules": ["Hot Work"]}, union_tags=True)
    checks.append(("tag added, canonical order", one["iogp_rules"], ["Hot Work", "Line of Fire"]))

    one = row()
    merge_extraction(one, {"iogp_rules": []}, union_tags=True)
    checks.append(("empty tag list loses nothing", one["iogp_rules"], ["Line of Fire"]))

    one = row()
    merge_extraction(one, {"iogp_rules": ["Housekeeping"]}, union_tags=True)
    checks.append(("non-canonical tag dropped", one["iogp_rules"], ["Line of Fire"]))
    checks.append(("non-canonical tag recorded", one["iogp_rules_rejected"], ["Housekeeping"]))

    one = row()
    changed = merge_extraction(one, {"precursor_activity": "welding", "iogp_rules": ["Hot Work"]},
                              union_tags=True)
    checks.append(("changes reported", sorted(changed), ["+Hot Work", "activity"]))

    # A barrier still fills with tags off: the two are independent, which is the whole point.
    one = row()
    merge_extraction(one, {"precursor_barrier_failure": "no guard fitted",
                           "iogp_rules": ["Confined Space"]})
    checks.append(("barrier fills while tags stay put",
                   (one["precursor_barrier_failure"]["text"], one["iogp_rules"]),
                   ("no guard fitted", ["Line of Fire"])))

    one = row(precursor_activity=existing, precursor_barrier_failure=existing)
    before = json.dumps(one, sort_keys=True)
    merge_extraction(one, {"precursor_activity": "x", "precursor_barrier_failure": "y",
                           "iogp_rules": ["Line of Fire"]})
    checks.append(("nothing to fill leaves row identical", json.dumps(one, sort_keys=True), before))

    failed = 0
    for name, got, want in checks:
        ok = got == want
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name:36} got {got!r:<32} want {want!r}")
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    raise SystemExit(1 if failed else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/processed/localized.jsonl")
    parser.add_argument("--apply", action="store_true",
                        help="write back to --input (a .bak copy is made first). Without it, "
                             "output goes to --out and --input is never touched")
    parser.add_argument("--out", default="data/scratch/backfilled.jsonl")
    parser.add_argument("--limit", type=int, help="process at most N null-barrier rows")
    parser.add_argument("--ids", help="re-extract only these comma-separated OSHA ids (still "
                                      "skipping any that already has a barrier). For spending "
                                      "a walled daily quota on the rows most likely to yield")
    parser.add_argument("--union-tags", action="store_true",
                        help="also union returned iogp_rules into each row. OFF by default: "
                             "this pass was measured inventing Confined Space and Work "
                             "Authorisation tags (AUDIT.md 2026-08-26), and a tag has no "
                             "verbatim-substring check to fail closed on")
    parser.add_argument("--self-check", action="store_true",
                        help="assert the merge invariants on synthetic rows; no IO")
    args = parser.parse_args()

    if args.self_check:
        self_check()

    rows = read_jsonl(args.input)
    todo = [r for r in rows if not r.get("precursor_barrier_failure")]
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",") if i.strip()}
        todo = [r for r in todo if r["id"] in wanted]
        missing = wanted - {r["id"] for r in todo}
        if missing:
            print(f"  note: {len(missing)} requested id(s) already have a barrier or are "
                  f"absent: {', '.join(sorted(missing))}")
    if args.limit:
        todo = todo[:args.limit]
    out_path = args.input if args.apply else args.out
    print(f"read {len(rows)} rows from {args.input}")
    print(f"  {len(todo)} with a null barrier to re-extract -> {out_path}")

    load_dotenv("scripts/.env")
    fleet = build_fleet()
    print(f"  fleet: {' -> '.join(model for _, model in fleet)}")
    if args.apply:
        shutil.copyfile(args.input, args.input + ".bak")
        print(f"  backup: {args.input}.bak")

    filled = failed = 0
    for done, row in enumerate(todo, 1):
        try:
            changed = merge_extraction(row, extract_one(fleet, row), args.union_tags)
        except Exception as error:
            failed += 1
            print(f"  [{done}/{len(todo)}] {row['id']} FAILED "
                  f"{type(error).__name__}: {error}")
            continue
        filled += "barrier_failure" in changed
        write_jsonl(out_path, rows)  # after every row: the daily wall arrives without warning
        print(f"  [{done}/{len(todo)}] {row['id']} {', '.join(changed) or 'no change'}")

    write_jsonl(out_path, rows)
    barriers = sum(1 for r in rows if r.get("precursor_barrier_failure"))
    print(f"\nre-extracted {len(todo) - failed} of {len(todo)} ({failed} failed); "
          f"{filled} new barrier span(s)")
    print(f"barrier coverage now {barriers}/{len(rows)} ({barriers / len(rows):.1%}) "
          f"in {out_path}")


if __name__ == "__main__":
    main()
