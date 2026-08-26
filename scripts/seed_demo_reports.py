"""Seed ~50 already-processed demo reports as the demo-day network-lag fallback.

`PRD.md` § Edge cases: "keep ~50 pre-seeded already-processed reports so Dashboard/Density views
show something real even if live inference stalls."

=== OWNED TECH DEBT: THESE ROWS GO STALE THE MOMENT REAL WEIGHTS LAND ===================
Every row this script writes is classified, tagged and span-extracted by the INTERIM_LANE_A
keyword implementations in `backend/inference/`, and carries `model_version =
'interim-keyword-0.1'`. They are NOT real model output. When Block 8 swaps in the fine-tuned
weights, every one of these rows is stale and disagrees with what the same text would score
afterwards - so LANE A MUST RE-RUN THIS SCRIPT AFTER THE SWAP. Logged in `AUDIT.md`
(2026-08-26, tech-debt) rather than left as a comment only. Find the stale rows with:
  select count(*) from classifications where model_version = 'interim-keyword-0.1';
=========================================================================================

HOW THE ROWS ARE PROCESSED. Each one is submitted to the real `POST /api/v1/reports` over HTTP,
so it runs the exact ingest path a live submission runs - preprocessing, all three heads, the
confidence-threshold routing, every insert. Nothing here reimplements any of that, which is why
these rows cannot drift from real ones as Lane C edits `routes/reports.py`.

WHY `submitted_at` IS REWRITTEN AFTERWARDS. The endpoint sets `submitted_at` to now() and takes
no date from the client, correctly - it is a server-set field. But 20 reports all stamped within
one minute give the dashboard a single-day history, so each row's date is updated to a spread
value after it is written. This is the one field this script sets that ingest did not, and it is
the only reason it touches the database directly at all.

WHY THE DATASET'S OWN `site_name` IS RESPECTED AND NOT REDISTRIBUTED. A row's `raw_text` names
its site in the prose ("Ramgarh FIELD me ek fitter...") and its `precursor_location` span points
at those characters. Reassigning the row to another site to flatten the distribution would make
the text and the foreign key contradict each other. The site spread is therefore whatever the
dataset actually holds, and the script prints it.

Reads the checkpoint .jsonl exactly as it is on disk. It does not wait for the generation run and
does not hold the file open. Fewer rows than the target is the normal case, not a failure: it
seeds what exists and prints the real number.

Run from the repo root, with the backend serving:
  backend/.venv/Scripts/python.exe scripts/seed_demo_reports.py
  backend/.venv/Scripts/python.exe scripts/seed_demo_reports.py --input data/processed/localized.jsonl
"""

import argparse
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from split_dataset import read_jsonl  # the torn-final-line handling already lives there

load_dotenv("backend/.env")
sys.path.insert(0, "backend")
from database import supabase  # noqa: E402  - needs the env loaded and sys.path set first

# Dates are spread backwards from this many days ago so the dashboard shows a history rather than
# one spike. The step pattern is deliberately uneven - a fixed row-per-day stride would make every
# day identical, which demonstrates as little as a flat site ranking does.
DAY_SPREAD = 21
DAY_STEPS = (0, 2, 3, 5, 8, 9, 13, 14, 17, 20)

# Neither is in the dataset, so both are assigned here. Most field reports come from supervisors.
ROLE_CYCLE = ("site_supervisor", "site_supervisor", "site_supervisor", "hse_manager")


def site_ids_by_name(base_url):
    """Map site name -> id from the real API, so no uuid is hardcoded or invented."""
    response = httpx.get(f"{base_url}/api/v1/sites", timeout=20.0)
    response.raise_for_status()
    return {site["name"]: site["id"] for site in response.json()}


def already_seeded(rows):
    """`raw_text` values already in the database, so a re-run does not double-seed.

    Matching on the text is enough and needs no new column: these narratives are verbatim from
    the dataset, so an exact match is the same report and not a coincidence.
    """
    existing = supabase.table("reports").select("raw_text").execute().data or []
    return {row["raw_text"] for row in existing if row["raw_text"]}


def submitted_at_for(index):
    """A deterministic spread date. Same input file, same dates - re-runs stay comparable."""
    step = DAY_STEPS[index % len(DAY_STEPS)]
    # The hour varies with the index so two reports on one day are not simultaneous.
    return (datetime.now(timezone.utc)
            - timedelta(days=DAY_SPREAD - step, hours=(index * 5) % 24)).isoformat()


def seed_one(base_url, row, site_id, index):
    """POST one report through the real pipeline, then set its spread date. Returns (detail, ms)."""
    payload = {"site_id": site_id, "raw_text": row["raw_text"],
               "reporter_role": ROLE_CYCLE[index % len(ROLE_CYCLE)]}

    started = time.perf_counter()
    response = httpx.post(f"{base_url}/api/v1/reports", json=payload, timeout=30.0)
    elapsed_ms = (time.perf_counter() - started) * 1000

    if response.status_code != 200:
        return None, elapsed_ms, f"HTTP {response.status_code} {response.text[:120]}"

    detail = response.json()
    supabase.table("reports").update(
        {"submitted_at": submitted_at_for(index)}).eq("id", detail["id"]).execute()
    return detail, elapsed_ms, None


def report_shape(seeded):
    """Print the real distribution actually written. Every number here is counted, not assumed."""
    if not seeded:
        return
    print(f"\nwhat landed ({len(seeded)} rows)")
    positives = sum(1 for d in seeded if (d.get("classification") or {}).get("sif_potential"))
    print(f"  sif_potential    true {positives} | false {len(seeded) - positives}")

    statuses = {}
    for detail in seeded:
        statuses[detail["status"]] = statuses.get(detail["status"], 0) + 1
    print("  status           " + " | ".join(f"{k} {v}" for k, v in sorted(statuses.items())))

    tagged = sum(1 for d in seeded if d.get("iogp_tags"))
    tags = sum(len(d.get("iogp_tags") or []) for d in seeded)
    spans = sum(len(d.get("precursors") or []) for d in seeded)
    print(f"  iogp tags        {tags} tags over {tagged} tagged rows, "
          f"{len(seeded) - tagged} untagged")
    print(f"  precursor spans  {spans} across {len(seeded)} rows")

    languages = {}
    for detail in seeded:
        languages[detail["language_detected"]] = languages.get(detail["language_detected"], 0) + 1
    print("  language         " + " | ".join(f"{k} {v}" for k, v in sorted(languages.items())))


def print_density(base_url):
    """Show the ranking these rows actually produce - a flat table demonstrates nothing."""
    response = httpx.get(f"{base_url}/api/v1/analytics/density", timeout=20.0)
    by_site = response.json()["by_site"]
    print(f"\ndensity by site ({len(by_site)} groups, ranked)")
    for row in by_site:
        print(f"  {row['group_name']:14} {row['sif_reports']:2}/{row['total_reports']:<3} "
              f"rate {row['sif_rate']:.2f}  rank_score {row['rank_score']:.4f}")
    scores = {row["rank_score"] for row in by_site}
    print(f"  {len(scores)} distinct rank_scores across {len(by_site)} sites"
          + ("  <- FLAT, ranking demonstrates nothing" if len(scores) <= 1 else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/sample/localized.jsonl",
                        help="checkpoint .jsonl, read as-is; a partial file is normal")
    parser.add_argument("--target", type=int, default=50,
                        help="how many to seed at most (PRD.md says ~50)")
    # 127.0.0.1 and NOT localhost, deliberately: uvicorn binds IPv4-only, so `localhost`
    # resolves to ::1 first and every new connection pays a failed IPv6 attempt - about 2.5s
    # each, which is minutes across a whole run. Same requests, same results, far faster.
    # Measured in `AUDIT.md` 2026-08-26. Do not "fix" this back to localhost.
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    if httpx.get(f"{args.base_url}/health", timeout=10.0).json() != {"status": "ok"}:
        raise SystemExit(f"{args.base_url}/health is not this backend - refusing to write")
    if not os.path.exists(args.input):
        raise SystemExit(f"{args.input} not found - nothing to seed from")

    rows = read_jsonl(args.input)
    print(f"read {len(rows)} rows from {args.input}")
    if len(rows) < args.target:
        # The honest number, not a failure and not padded by duplicating rows: the same narrative
        # inserted twice would inflate every denominator on the dashboard.
        print(f"  FEWER THAN {args.target}: seeding the {len(rows)} rows that exist. The "
              f"generation run is incomplete (AUDIT.md 2026-08-26).")

    site_ids = site_ids_by_name(args.base_url)
    seen = already_seeded(rows)
    print(f"  {len(site_ids)} sites available; {len(seen)} report texts already in the database")

    seeded, skipped, failed, timings = [], 0, [], []
    for index, row in enumerate(rows[:args.target]):
        site_id = site_ids.get(row.get("site_name"))
        if not site_id:
            failed.append((row.get("id"), f"unknown site {row.get('site_name')!r}"))
            continue
        if row["raw_text"] in seen:
            skipped += 1
            continue

        detail, elapsed_ms, error = seed_one(args.base_url, row, site_id, index)
        timings.append(elapsed_ms)
        if error:
            failed.append((row.get("id"), error))
        else:
            seeded.append(detail)

    print(f"\nseeded {len(seeded)} | skipped {skipped} already present | failed {len(failed)}")
    for osha_id, error in failed:
        print(f"  FAILED {osha_id}: {error}")
    if timings:
        print(f"  ingest latency  median {statistics.median(timings):.0f} ms | "
              f"max {max(timings):.0f} ms  (PRD.md target: under 3000 ms)")

    report_shape(seeded)
    print_density(args.base_url)
    print("\nEvery row above carries model_version 'interim-keyword-0.1' and is STALE once real "
          "weights land - Lane A re-runs this script after Block 8.")


if __name__ == "__main__":
    main()
