"""Split the generated dataset into train/test, stratified on label AND noise tier.

Run by hand after localize_dataset.py. Reads the checkpoint .jsonl exactly as it is on
disk, including a PARTIAL one: if the generation run was stopped at 600 rows, this
produces a clean 85/15 of those 600 and says so. That is the normal case here, not an
edge case - the run takes hours and gets stopped.

Stratified on the PAIR (sif_potential, noise_tier), not on the label alone. Stratifying
on the label alone lets the 10% heavy-noise rows land entirely in train, leaving a test
set of tidy English that reports a score the messy real inputs will not reproduce.

Usage:
  python scripts/split_dataset.py                    -> data/processed/ + data/test/
  python scripts/split_dataset.py --self-check       -> assert invariants, no file IO
"""

import argparse
import json
import os
import random
from collections import Counter, defaultdict

# PRD.md section Glossary, canonical 9. Listed here so a rule with ZERO examples still
# prints as 0 rather than being invisible by absence.
IOGP_RULES = [
    "Bypassing Safety Controls", "Confined Space", "Driving", "Energy Isolation",
    "Hot Work", "Line of Fire", "Safe Mechanical Lifting", "Work Authorisation",
    "Working at Height",
]
PRECURSORS = ("activity", "location", "equipment", "barrier_failure")


def read_jsonl(path):
    """Read the checkpoint, skipping a torn final line.

    A run killed mid-write can leave a partial last line. Dropping it with a warning is
    correct; the alternative is a crash that makes an interrupted run unusable, which is
    exactly the case this script exists to serve.
    """
    rows, torn = [], 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                torn += 1
    if torn:
        print(f"  warning: skipped {torn} unparseable line(s) - run stopped mid-write")
    return rows


def stratified_split(rows, test_frac, seed):
    """Split within every (sif_potential, noise_tier) stratum.

    Returns (train, test, table). Per stratum the test count is round(n * frac), so a
    stratum too small to yield one test row contributes none rather than being dropped -
    the printed table flags it instead of hiding it.
    """
    strata = defaultdict(list)
    for row in rows:
        strata[(bool(row["sif_potential"]), row["noise_tier"])].append(row)

    rng = random.Random(seed)
    train, test, table = [], [], []
    for key in sorted(strata, key=lambda k: (k[0], str(k[1]))):
        members = sorted(strata[key], key=lambda r: str(r["id"]))  # stable before shuffle
        rng.shuffle(members)
        n_test = round(len(members) * test_frac)
        test += members[:n_test]
        train += members[n_test:]
        table.append((key, len(members), len(members) - n_test, n_test))
    return train, test, table


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def report(name, rows):
    """Print real computed counts for one split. Every number here is counted, not assumed."""
    print(f"\n{name}: {len(rows)} rows")
    if not rows:
        return
    n = len(rows)
    positives = sum(1 for r in rows if r["sif_potential"])
    print(f"  sif_potential  true {positives} ({positives / n:.1%}) | "
          f"false {n - positives} ({(n - positives) / n:.1%})")
    tiers = Counter(r["noise_tier"] for r in rows)
    print("  noise tiers    " + " | ".join(
        f"{tier} {tiers.get(tier, 0)} ({tiers.get(tier, 0) / n:.1%})"
        for tier in ("clean", "moderate", "heavy")))
    rules = Counter(rule for r in rows for rule in r.get("iogp_rules") or [])
    untagged = sum(1 for r in rows if not (r.get("iogp_rules") or []))
    print(f"  iogp rules     {sum(rules.values())} tags over {n} rows; {untagged} untagged")
    for rule in IOGP_RULES:
        count = rules.get(rule, 0)
        print(f"    {rule:26} {count}"
              + ("   <- sparse" if count < max(1, round(n * 0.01)) else ""))
    print("  precursor spans")
    for field in PRECURSORS:
        have = sum(1 for r in rows if r.get(f"precursor_{field}"))
        print(f"    {field:16} {have}/{n} ({have / n:.1%})")


def self_check(test_frac, seed):
    """Assert what the split must never break, on synthetic rows. No file IO."""
    def make(i, label, tier):
        return {"id": str(i), "sif_potential": label, "noise_tier": tier,
                "iogp_rules": [], **{f"precursor_{f}": None for f in PRECURSORS}}

    rows = [make(i, i % 2 == 0, ("clean", "moderate", "heavy")[i % 3]) for i in range(100)]
    train, test, table = stratified_split(rows, test_frac, seed)
    ids_train, ids_test = {r["id"] for r in train}, {r["id"] for r in test}
    checks = [
        ("no row lost", len(train) + len(test), len(rows)),
        ("no row duplicated", len(ids_train | ids_test), 100),
        ("no overlap", len(ids_train & ids_test), 0),
        # Not exactly test_frac, and it cannot be: each stratum rounds independently, so
        # several strata rounding the same way accumulate (4 strata of 17 give 3 test rows
        # each, 2 of 16 give 2, = 16/100). Bounded by 0.5 rows per stratum, so it shrinks
        # as the file grows - at 1200 rows the worst case is 3 rows, 0.25%. A tolerance is
        # the honest assertion; forcing exact 15% would need largest-remainder bookkeeping
        # to buy a quarter of a percent.
        ("test fraction within 2pt", abs(len(test) / len(rows) - test_frac) <= 0.02, True),
        ("every stratum present", len(table), 6),
        # A tier landing wholly in one split is the bug this stratification exists to stop.
        ("heavy tier in test", any(r["noise_tier"] == "heavy" for r in test), True),
        ("heavy tier in train", any(r["noise_tier"] == "heavy" for r in train), True),
        ("both labels in test", len({r["sif_potential"] for r in test}), 2),
        ("deterministic", [r["id"] for r in stratified_split(rows, test_frac, seed)[1]],
         [r["id"] for r in test]),
    ]
    # A partial file is the normal case here, so it is asserted rather than assumed.
    for size in (60, 11):
        part_train, part_test, _ = stratified_split(rows[:size], test_frac, seed)
        checks.append((f"partial {size} loses nothing",
                       len(part_train) + len(part_test), size))
    part_test = stratified_split(rows[:60], test_frac, seed)[1]
    checks += [("partial 60 has test rows", len(part_test) > 0, True),
               ("partial 60 keeps heavy in test",
                any(r["noise_tier"] == "heavy" for r in part_test), True)]
    # A single-row stratum yields no test row and must still not vanish.
    one_train, one_test, one_table = stratified_split([make(0, True, "heavy")],
                                                      test_frac, seed)
    checks += [("single row kept", len(one_train) + len(one_test), 1),
               ("single row goes to train", len(one_train), 1),
               ("single row stratum reported", len(one_table), 1)]

    failed = 0
    for name, got, want in checks:
        ok = got == want
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name:30} got {got!r:<16} want {want!r}")
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    raise SystemExit(1 if failed else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/processed/localized.jsonl")
    parser.add_argument("--train-out", default="data/processed/train.jsonl")
    parser.add_argument("--test-out", default="data/test/test.jsonl")
    parser.add_argument("--test-frac", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--expect", type=int, default=1200,
                        help="row count of a completed run, for the partial-file notice")
    parser.add_argument("--self-check", action="store_true",
                        help="assert the split's invariants on synthetic rows; no file IO")
    args = parser.parse_args()

    if args.self_check:
        self_check(args.test_frac, args.seed)
    if not os.path.exists(args.input):
        raise SystemExit(f"{args.input} not found - run localize_dataset.py first")

    rows = read_jsonl(args.input)
    if not rows:
        raise SystemExit(f"{args.input} holds no rows")
    unique = {r["id"] for r in rows}
    if len(unique) != len(rows):
        print(f"  warning: {len(rows) - len(unique)} duplicate id(s) in the checkpoint")
    print(f"read {len(rows)} rows from {args.input}")
    print(f"  PARTIAL FILE: splitting the {len(rows)} rows present, not a completed "
          f"{args.expect}-row run" if len(rows) < args.expect
          else f"  complete run present ({len(rows)} rows)")

    train, test, table = stratified_split(rows, args.test_frac, args.seed)

    print(f"\nper-stratum split (target test fraction {args.test_frac:.0%})")
    print(f"  {'sif':6} {'tier':10} {'total':>6} {'train':>6} {'test':>6}")
    for (label, tier), total, n_train, n_test in table:
        flag = "   <- too small to yield a test row" if total and not n_test else ""
        print(f"  {str(label):6} {str(tier):10} {total:6} {n_train:6} {n_test:6}{flag}")

    write_jsonl(args.train_out, train)
    write_jsonl(args.test_out, test)
    report(f"TRAIN  {args.train_out}", train)
    report(f"TEST   {args.test_out}", test)
    print(f"\nwrote {len(train)} train + {len(test)} test = {len(train) + len(test)} "
          f"of {len(rows)} read")


if __name__ == "__main__":
    main()
