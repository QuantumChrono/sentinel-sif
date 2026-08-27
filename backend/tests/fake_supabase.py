"""An in-memory stand-in for the real Supabase client, used only in tests.

WHY THIS EXISTS AND WHY IT IS SMALL. `routes/reports.py` writes a report and then reads it
back in the same request; testing that round trip needs something behind `supabase.table(...)`
that actually stores what was inserted. A real network call to Supabase would make the suite
non-deterministic and dependent on this machine's local state, which the Lane D brief
explicitly forbids. This fake implements exactly the chain calls `routes/reports.py` and
`routes/review.py` use today (`table`, `select`, `insert`, `update`, `eq`, `gte`, `lte`,
`order`, `limit`, `execute`) and nothing more - it is not a general Supabase mock.

NOT A REPLACEMENT FOR INTEGRATION TESTING AGAINST THE REAL DATABASE. This proves the route
handlers call the client correctly and handle the shapes that come back; it does not prove
Postgres itself behaves the same way (foreign keys, cascades, real constraint violations are
untested here). That gap is worth naming rather than hiding.
"""

import uuid


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: dict, table_name: str):
        self._store = store
        self._table_name = table_name
        self._op = None
        self._payload = None
        self._filters = []

    def select(self, _columns):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self._filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self._filters.append(("lte", column, value))
        return self

    def order(self, _column, desc=False):  # noqa: ARG002 - accepted, not needed by tests
        return self

    def limit(self, _n):  # noqa: ARG002 - accepted, not needed by tests
        return self

    def execute(self):
        rows = self._store.setdefault(self._table_name, [])

        if self._op == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            created = []
            for payload in payloads:
                row = dict(payload)
                row.setdefault("id", str(uuid.uuid4()))
                rows.append(row)
                created.append(row)
            return _Response(created)

        matched = self._apply_filters(rows)

        if self._op == "update":
            for row in matched:
                row.update(self._payload)
            return _Response(matched)

        # select (default): embed child rows the way reports.py's REPORT_SELECT expects.
        if self._table_name == "reports":
            matched = [self._embed(row) for row in matched]
        return _Response(matched)

    def _apply_filters(self, rows):
        result = rows
        for kind, column, value in self._filters:
            if kind == "eq":
                result = [row for row in result if str(row.get(column)) == str(value)]
            elif kind == "gte":
                result = [row for row in result if row.get(column, "") >= value]
            elif kind == "lte":
                result = [row for row in result if row.get(column, "") <= value]
        return result

    def _embed(self, row):
        out = dict(row)
        out["sites"] = None
        out["classifications"] = [
            c for c in self._store.get("classifications", []) if c["report_id"] == row["id"]
        ]
        out["iogp_tags"] = [
            t for t in self._store.get("iogp_tags", []) if t["report_id"] == row["id"]
        ]
        out["precursors"] = [
            p for p in self._store.get("precursors", []) if p["report_id"] == row["id"]
        ]
        return out


class FakeSupabase:
    """Drop-in for `database.supabase` in tests. `store` is inspectable directly, so a test
    can assert on exactly what was written without going back through the API.
    """

    def __init__(self):
        self.store: dict[str, list[dict]] = {}

    def table(self, name: str) -> _Query:
        return _Query(self.store, name)
