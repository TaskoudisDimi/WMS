"""Tests never talk to Supabase: env vars point to a dummy project and every test
patches the client it needs. Set before any app import so .env values are ignored."""
import base64
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.test"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


def make_jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


class FakeTable:
    """In-memory stand-in for supabase.table(...) supporting the filters the app uses."""

    def __init__(self, db: "FakeDB", name: str):
        self.db, self.name = db, name
        self.rows = db.tables.setdefault(name, [])
        self.preds, self.single, self.op, self.payload = [], False, "select", None
        self._limit = None

    # query builders
    def select(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def limit(self, n): self._limit = n; return self
    def eq(self, col, val): self.preds.append(lambda r: r.get(col) == val); return self
    def neq(self, col, val): self.preds.append(lambda r: r.get(col) != val); return self
    def in_(self, col, vals): vals = list(vals); self.preds.append(lambda r: r.get(col) in vals); return self
    def gt(self, col, val): self.preds.append(lambda r: r.get(col) is not None and r[col] > val); return self
    def gte(self, col, val): self.preds.append(lambda r: r.get(col) is not None and r[col] >= val); return self
    def lt(self, col, val): self.preds.append(lambda r: r.get(col) is not None and r[col] < val); return self
    def lte(self, col, val): self.preds.append(lambda r: r.get(col) is not None and r[col] <= val); return self
    def like(self, col, pat): pre = pat.strip('%'); self.preds.append(lambda r: pre in str(r.get(col) or '')); return self
    @property
    def not_(self):
        outer = self
        class _Not:
            def is_(self_inner, col, val):
                outer.preds.append(lambda r: r.get(col) is not None); return outer
        return _Not()
    def maybe_single(self): self.single = True; return self
    def single(self): self.single = True; return self

    def insert(self, payload): self.op, self.payload = "insert", payload; return self
    def update(self, payload): self.op, self.payload = "update", payload; return self
    def delete(self): self.op = "delete"; return self

    def _match(self):
        return [r for r in self.rows if all(p(r) for p in self.preds)]

    def execute(self):
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            created = []
            for it in items:
                for key in self.db.unique.get(self.name, []):
                    if any(all(r.get(k) == it.get(k) for k in key) for r in self.rows):
                        raise Exception("duplicate key value violates unique constraint")
                row = {"id": f"{self.name}-{len(self.rows) + 1}", **it}
                self.rows.append(row)
                created.append(row)
            return SimpleNamespace(data=created)
        hits = self._match()
        if self.op == "update":
            for r in hits:
                r.update(self.payload)
            return SimpleNamespace(data=hits)
        if self.op == "delete":
            for r in hits:
                self.rows.remove(r)
            return SimpleNamespace(data=hits)
        if self._limit:
            hits = hits[:self._limit]
        if self.single:  # postgrest returns None (not an empty response) when nothing matches
            return SimpleNamespace(data=hits[0]) if hits else None
        return SimpleNamespace(data=hits, count=len(hits))


class FakeDB:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.unique: dict[str, list[tuple]] = {"integration_events": [("integration_id", "external_id")]}

    def table(self, name):
        return FakeTable(self, name)

    def rpc(self, fn, params):
        """Python versions of the SQL functions in migrations/001_features.sql."""
        db = self

        class Call:
            def execute(self_inner):
                if fn == "wms_adjust_stock":
                    items = db.tables.setdefault("inventory_items", [])
                    row = next((r for r in items if r["business_id"] == params["p_business"]
                                and r["product_id"] == params["p_product"]), None)
                    if row is None:
                        row = {"business_id": params["p_business"], "product_id": params["p_product"], "quantity": 0}
                        items.append(row)
                    old = row["quantity"]
                    new = params["p_absolute"] if params["p_absolute"] is not None else old + params["p_delta"]
                    row["quantity"] = max(new, 0)
                    return SimpleNamespace(data=[{"old_quantity": old, "new_quantity": row["quantity"]}])
                if fn == "wms_consume_lots":
                    remaining = params["p_qty"]
                    lots = sorted((l for l in db.tables.get("inventory_lots", [])
                                   if l["product_id"] == params["p_product"] and l["quantity"] > 0),
                                  key=lambda l: (l.get("expiry_date") is None, l.get("expiry_date") or ""))
                    for l in lots:
                        take = min(l["quantity"], remaining)
                        l["quantity"] -= take
                        remaining -= take
                    return SimpleNamespace(data=None)
                raise NotImplementedError(fn)
        return Call()


@pytest.fixture
def fake_db():
    """(tables dict, client) — the client stands in for `supabase` in any module."""
    db = FakeDB()
    return db.tables, db
