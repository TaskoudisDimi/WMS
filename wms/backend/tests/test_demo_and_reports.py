import services.demo as demo
import services.forecasting as forecasting


def test_demo_seed_produces_a_realistic_business(monkeypatch, fake_db):
    tables, db = fake_db
    monkeypatch.setattr(demo, "supabase", db)
    monkeypatch.setattr(forecasting, "supabase", db)
    tables["products"] = []

    result = demo.seed("biz", "user", sku_prefix="")
    assert result["products"] == 12 and result["suppliers"] == 3
    assert all(p["supplier_id"] for p in tables["products"])
    assert any(o["type"] == "purchase" and o.get("supplier_id") for o in tables["orders"])

    plans = {p.sku: p for p in forecasting.plan_reorders("biz")}
    assert {s for s, p in plans.items() if p.urgency == "critical"} >= {"PW-023", "TP-48"}
    # suggestions respect pack sizes (PW-023 comes in packs of 6, TP-48 of 36)
    assert plans["PW-023"].suggested_qty % 6 == 0 and plans["TP-48"].suggested_qty % 36 == 0

    demo.clean("biz")  # only removes DEMO- products; here prefix was empty so products stay
    assert tables["products"]


# ── Reports ───────────────────────────────────────────────────────────────────

import services.reports as reports  # noqa: E402


def test_reports_valuation_abc_dead_stock(monkeypatch, fake_db):
    tables, db = fake_db
    monkeypatch.setattr(reports, "supabase", db)
    old = "2026-01-01T00:00:00+00:00"
    tables["products"] = [
        {"id": "a", "business_id": "b", "sku": "A", "name": "Star", "cost_price": 5, "created_at": old},
        {"id": "c", "business_id": "b", "sku": "C", "name": "Tail", "cost_price": 1, "created_at": old},
        {"id": "d", "business_id": "b", "sku": "D", "name": "Dusty", "cost_price": 2, "created_at": old},
    ]
    tables["inventory_items"] = [{"business_id": "b", "product_id": "a", "quantity": 10},
                                 {"business_id": "b", "product_id": "c", "quantity": 0},
                                 {"business_id": "b", "product_id": "d", "quantity": 50}]
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    tables["orders"] = [{"id": "o1", "business_id": "b", "type": "sale", "status": "completed", "created_at": now}]
    tables["order_items"] = [{"order_id": "o1", "product_id": "a", "quantity": 90, "unit_price": 10},
                             {"order_id": "o1", "product_id": "c", "quantity": 10, "unit_price": 10}]
    tables["inventory_movements"] = [{"business_id": "b", "product_id": "a", "type": "outbound", "created_at": now}]

    r = reports.build("b")
    assert r["valuation"]["total"] == 10 * 5 + 50 * 2
    # the product that crosses 80% still counts as A; the next starts at 90% → B
    assert [x["class"] for x in r["abc"]["items"]] == ["A", "B"]
    assert r["margins"]["items"][0]["margin_pct"] == 50.0                  # (10-5)/10
    assert [d["sku"] for d in r["dead_stock"]["items"]] == ["D"]


# ── Sales import (file) and Elorus sync ───────────────────────────────────────

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.routes.orders as orders_routes  # noqa: E402
import services.elorus as elorus  # noqa: E402
import services.permissions as permissions  # noqa: E402
import services.sales as sales  # noqa: E402
import services.stock as stock  # noqa: E402
from core.security import get_current_user  # noqa: E402


def _patch(monkeypatch, db):
    for mod in (permissions, sales, stock, orders_routes, elorus):
        monkeypatch.setattr(mod, "supabase", db)


def test_sales_import_groups_documents_and_never_double_counts(monkeypatch, fake_db):
    tables, db = fake_db
    _patch(monkeypatch, db)
    tables["business_members"] = [{"user_id": "u", "business_id": "b", "role": "owner"}]
    tables["products"] = [{"id": "p1", "business_id": "b", "sku": "TP-48", "barcode": None}]
    tables["inventory_items"] = [{"business_id": "b", "product_id": "p1", "quantity": 100}]
    app = FastAPI(); app.include_router(orders_routes.router)
    app.dependency_overrides[get_current_user] = lambda: "u"
    client = TestClient(app)
    rows = [{"document": "ΤΔΑ-1", "date": "2026-10-01", "customer": "Κρητικός", "sku": "tp-48", "quantity": 4, "unit_price": 1},
            {"document": "ΤΔΑ-1", "date": "2026-10-01", "customer": "Κρητικός", "sku": "TP-48", "quantity": 2, "unit_price": 1},
            {"document": "ΤΔΑ-2", "date": "2026-10-02", "sku": "UNKNOWN", "quantity": 1}]

    r1 = client.post("/api/orders/import-sales", json={"business_id": "b", "rows": rows}).json()
    r2 = client.post("/api/orders/import-sales", json={"business_id": "b", "rows": rows}).json()
    assert r1 == {"created": 1, "skipped": 0, "unmatched_skus": ["UNKNOWN"]}
    assert r2["created"] == 0 and r2["skipped"] == 1
    assert tables["inventory_items"][0]["quantity"] == 94
    assert tables["inventory_movements"][0]["created_at"].startswith("2026-10-01")


def test_history_import_records_movements_without_touching_stock(monkeypatch, fake_db):
    tables, db = fake_db
    _patch(monkeypatch, db)
    tables["inventory_items"] = [{"business_id": "b", "product_id": "p1", "quantity": 100}]
    sales.record_sale(business_id="b", external_ref="x:1", party=None, lines=[("p1", 30, None)], affect_stock=False)
    assert tables["inventory_items"][0]["quantity"] == 100
    assert tables["inventory_movements"][0]["quantity"] == 30


class FakeElorus:
    def __init__(self, *a): pass
    def product_codes(self): return {"e1": ["TP-48"], "e2": ["5201111111111"]}
    def paged(self, path, **params): return iter([{"id": "inv1"}, {"id": "inv2"}])
    def get(self, path, **params):
        return {"inv1": {"id": "inv1", "date": "2026-10-17", "client_display_name": "Delta Pack", "representation": "ΤΔΑ Α-12",
                         "items": [{"product": "e1", "quantity": "5.0000", "unit_value": "0.95"},
                                   {"product": "e9", "title": "Μεταφορικά", "quantity": "1"}]},
                "inv2": {"id": "inv2", "date": "2026-10-17", "items": [{"product": "e2", "quantity": "2"}]}}[path.split("/")[2]]


def test_elorus_sync_imports_once_and_matches_by_code_or_barcode(monkeypatch, fake_db):
    tables, db = fake_db
    _patch(monkeypatch, db)
    monkeypatch.setattr(elorus, "client_for", lambda integration: FakeElorus())
    tables["products"] = [{"id": "p1", "business_id": "b", "sku": "TP-48", "barcode": None},
                          {"id": "p2", "business_id": "b", "sku": "GL-NIT", "barcode": "5201111111111"}]
    tables["inventory_items"] = [{"business_id": "b", "product_id": "p1", "quantity": 50},
                                 {"business_id": "b", "product_id": "p2", "quantity": 50}]
    tables["integrations"] = [{"id": "i", "business_id": "b", "provider": "elorus", "secret": "x",
                               "config": {"start_at": "2026-10-01T00:00:00+00:00"}}]
    first = elorus.sync(tables["integrations"][0])
    second = elorus.sync(tables["integrations"][0])
    assert first["imported"] == 2 and second["already"] == 2
    qty = {i["product_id"]: i["quantity"] for i in tables["inventory_items"]}
    assert qty == {"p1": 45, "p2": 48}
    assert tables["integrations"][0]["config"]["synced_until"]
