"""Prove every endpoint is correct against a GENUINELY empty database, then put every row back.

`PRD.md` § Edge cases requires explicit empty states with no exception anywhere. That cannot be
checked by reasoning, and it cannot be checked against a database that still holds rows: the only
honest test is to empty the tables, look, and restore.

HOW THE ROWS SURVIVE THIS. Every row of `sites`, `reports`, `classifications`, `iogp_tags` and
`precursors` is written to a snapshot file FIRST, and that file is read back and counted before a
single delete runs. Rows are restored with their original `id` values, so the foreign keys that
pointed at them still point at them afterwards - a restore with fresh uuids would reconnect
nothing. If any step after the delete fails, the snapshot is deliberately LEFT ON DISK and its
path printed: a file on disk is recoverable, a dropped table is not.

WHY `users` IS IN THE CYCLE, HAVING FIRST BEEN LEFT OUT. Leaving it alone was the intent - no page
reads it directly, and its ids must match Supabase Auth uids. But `users.site_id` references
`sites(id)` with no `on delete cascade`, and one row points at Duliajan, so deleting `sites` with
`users` still populated is a foreign-key violation - raised AFTER `reports` had already been
emptied. Including the table is a smaller fix than nulling one column and putting it back, and the
ids are restored verbatim from the snapshot rather than regenerated.

Run from the repo root with the backend already serving:
  backend/.venv/Scripts/python.exe scripts/check_empty_database.py
"""

import argparse
import json
import os
import sys
from uuid import uuid4

import httpx
from dotenv import load_dotenv

load_dotenv("backend/.env")
sys.path.insert(0, "backend")
from database import supabase  # noqa: E402  - needs the env loaded and sys.path set first

# Delete order: children before parents, so no delete depends on cascade behaviour. `reversed()`
# is therefore a valid restore order - a parent is always back before the rows referencing it.
#
# The two orderings that are load-bearing rather than incidental: `classifications` precedes
# `users` because `classifications.reviewed_by` references it, and `users` precedes `sites`
# because `users.site_id` does. Reversed, that restores `sites` -> `users` -> `reports` ->
# `classifications`, which is the only order in which every foreign key has its target present.
TABLES = ("precursors", "iogp_tags", "classifications", "reports", "users", "sites")

# All 9 canonical rules must still be reported at zero on an empty database rather than vanishing,
# so the count is asserted rather than the list merely being non-empty.
EXPECTED_RULE_COUNT = 9


def snapshot(path):
    """Write every row of every table to one file, then read it back and prove it round-tripped."""
    data = {table: supabase.table(table).select("*").execute().data or [] for table in TABLES}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, default=str)

    with open(path, encoding="utf-8") as handle:
        reread = json.load(handle)
    for table in TABLES:
        if len(reread[table]) != len(data[table]):
            raise SystemExit(f"snapshot of {table} did not round-trip - nothing was deleted")

    print(f"snapshot written and verified: {path}")
    for table in TABLES:
        print(f"  {table:16} {len(data[table])} rows")
    return reread


def empty_every_table():
    """Delete every row, children first. Stops dead if any table is not actually empty after."""
    for table in TABLES:
        rows = supabase.table(table).select("id").execute().data or []
        for row in rows:
            supabase.table(table).delete().eq("id", row["id"]).execute()
        remaining = len(supabase.table(table).select("id").execute().data or [])
        print(f"  emptied {table:16} {len(rows)} deleted, {remaining} remaining")
        if remaining:
            raise SystemExit(f"{table} still holds {remaining} rows - stopping before the checks")


def check(base_url):
    """Hit every read endpoint against the empty database. Returns [(name, ok, observed)]."""
    results = []

    def probe(name, path, verdict):
        try:
            response = httpx.get(f"{base_url}{path}", timeout=20.0)
            body = response.json()
        except Exception as error:  # a crash IS the failure this case exists to find
            results.append((name, False, f"raised {type(error).__name__}: {error}"))
            return
        ok, observed = verdict(response.status_code, body)
        results.append((name, ok, observed))

    probe("GET /sites -> []", "/api/v1/sites",
          lambda status, body: (status == 200 and body == [], f"HTTP {status} {body!r}"))
    probe("GET /reports -> []", "/api/v1/reports",
          lambda status, body: (status == 200 and body == [], f"HTTP {status} {body!r}"))
    probe("GET /analytics/density -> both empty", "/api/v1/analytics/density",
          lambda status, body: (status == 200 and body == {"by_site": [], "by_activity": []},
                                f"HTTP {status} {body!r}"))
    probe("GET /analytics/rules -> 9 rules all 0", "/api/v1/analytics/rules",
          lambda status, body: (
              status == 200 and isinstance(body, list) and len(body) == EXPECTED_RULE_COUNT
              and all(row["report_count"] == 0 for row in body),
              f"HTTP {status} {len(body) if isinstance(body, list) else body} rules, counts "
              f"{sorted({r['report_count'] for r in body}) if isinstance(body, list) else '-'}"))
    probe("GET /analytics/review-queue -> []", "/api/v1/analytics/review-queue",
          lambda status, body: (status == 200 and body == [], f"HTTP {status} {body!r}"))
    # A detail request for a report that cannot exist must be a clean 404, not an exception.
    probe("GET /reports/{unknown} -> 404", f"/api/v1/reports/{uuid4()}",
          lambda status, body: (status == 404, f"HTTP {status} {body!r}"))
    return results


def restore(data):
    """Insert every snapshotted row back, ids included, parents before children."""
    for table in reversed(TABLES):
        rows = data[table]
        if rows:
            supabase.table(table).insert(rows).execute()
        restored = len(supabase.table(table).select("id").execute().data or [])
        print(f"  restored {table:16} {restored} rows (snapshot held {len(rows)})")
        if restored != len(rows):
            raise SystemExit(f"{table} restored {restored} of {len(rows)} - SNAPSHOT KEPT")


def verify_restore(data):
    """Every original id must be back. A matching count with different ids is not a restore."""
    ok = True
    for table in TABLES:
        expected = {str(row["id"]) for row in data[table]}
        actual = {str(row["id"])
                  for row in supabase.table(table).select("id").execute().data or []}
        same = expected == actual
        ok &= same
        print(f"  {'ok  ' if same else 'FAIL'} {table:16} {len(actual)} ids, "
              f"{len(expected - actual)} missing, {len(actual - expected)} unexpected")
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # 127.0.0.1 and NOT localhost, deliberately: uvicorn binds IPv4-only, so `localhost`
    # resolves to ::1 first and every new connection pays a failed IPv6 attempt - about 2.5s
    # each, which is minutes across a whole run. Same requests, same results, far faster.
    # Measured in `AUDIT.md` 2026-08-26. Do not "fix" this back to localhost.
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--snapshot", default="empty_db_snapshot.json")
    args = parser.parse_args()

    # Port 8000 holds an unrelated service (`STAGES.md` § PORTS). Confirming the health body is
    # ours before deleting anything is the difference between emptying our database and someone
    # else's.
    if httpx.get(f"{args.base_url}/health", timeout=10.0).json() != {"status": "ok"}:
        raise SystemExit(f"{args.base_url}/health is not this backend - refusing to touch the DB")

    data = snapshot(args.snapshot)

    print("\nemptying every table")
    empty_every_table()

    print("\nchecks against the empty database")
    results = check(args.base_url)
    for name, ok, observed in results:
        print(f"  {'PASS' if ok else 'FAIL'} {name:38} {observed}")

    print("\nrestoring from the snapshot")
    restore(data)
    print("\nverifying the restore")
    restored_ok = verify_restore(data)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} empty-database checks passed; "
          f"restore {'verified' if restored_ok else 'FAILED'}")

    if restored_ok:
        os.remove(args.snapshot)
        print(f"snapshot {args.snapshot} removed - every row is back in the database")
    else:
        print(f"SNAPSHOT KEPT at {args.snapshot} - restore it by hand before anything else")
    raise SystemExit(0 if passed == len(results) and restored_ok else 1)


if __name__ == "__main__":
    main()
