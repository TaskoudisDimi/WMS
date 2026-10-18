"""Owner-facing reports computed from data the app already has."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from db.supabase_client import supabase

DEAD_DAYS = 90


def _sales(business_id: str, since: datetime) -> list[dict]:
    orders = supabase.table("orders").select("id").eq("business_id", business_id).eq("type", "sale") \
        .eq("status", "completed").gte("created_at", since.isoformat()).limit(50000).execute().data or []
    ids = [o["id"] for o in orders]
    items: list[dict] = []
    for i in range(0, len(ids), 300):
        items += supabase.table("order_items").select("product_id, quantity, unit_price") \
            .in_("order_id", ids[i:i + 300]).execute().data or []
    return items


def build(business_id: str, days: int = 90) -> dict:
    now = datetime.now(timezone.utc)
    products = supabase.table("products") \
        .select("id, sku, name, category, unit, cost_price, sell_price, created_at") \
        .eq("business_id", business_id).execute().data or []
    stock = {r["product_id"]: r["quantity"] for r in (supabase.table("inventory_items")
             .select("product_id, quantity").eq("business_id", business_id).execute().data or [])}

    # ── Stock valuation (at cost) ──
    valuation, by_category, missing_cost = [], defaultdict(float), 0
    for p in products:
        qty = stock.get(p["id"], 0)
        if qty <= 0:
            continue
        if p.get("cost_price") is None:
            missing_cost += 1
            continue
        value = qty * float(p["cost_price"])
        valuation.append({"product_id": p["id"], "sku": p["sku"], "name": p["name"], "category": p.get("category"),
                          "quantity": qty, "unit": p.get("unit"), "cost_price": float(p["cost_price"]),
                          "value": round(value, 2)})
        by_category[p.get("category") or "—"] += value
    valuation.sort(key=lambda r: -r["value"])
    total_value = round(sum(r["value"] for r in valuation), 2)

    # ── Sales per product → ABC and margins ──
    sold: dict[str, dict] = defaultdict(lambda: {"units": 0, "revenue": 0.0, "priced_units": 0})
    for it in _sales(business_id, now - timedelta(days=days)):
        s = sold[it["product_id"]]
        s["units"] += it["quantity"]
        if it.get("unit_price") is not None:
            s["revenue"] += it["quantity"] * float(it["unit_price"])
            s["priced_units"] += it["quantity"]
    total_revenue = sum(s["revenue"] for s in sold.values())

    by_id = {p["id"]: p for p in products}
    ranked = sorted((pid for pid in sold if pid in by_id), key=lambda pid: -sold[pid]["revenue"])
    abc, cumulative = [], 0.0
    for pid in ranked:
        rev = sold[pid]["revenue"]
        share = rev / total_revenue if total_revenue else 0
        cumulative += share
        cls = "A" if cumulative - share < 0.80 else "B" if cumulative - share < 0.95 else "C"
        p = by_id[pid]
        abc.append({"product_id": pid, "sku": p["sku"], "name": p["name"], "units": sold[pid]["units"],
                    "revenue": round(rev, 2), "share": round(share * 100, 1),
                    "cumulative": round(cumulative * 100, 1), "class": cls})
    no_sales = [{"product_id": p["id"], "sku": p["sku"], "name": p["name"]} for p in products if p["id"] not in sold]
    counts = {c: sum(1 for r in abc if r["class"] == c) for c in "ABC"}
    revenue_share = {c: round(sum(r["share"] for r in abc if r["class"] == c), 1) for c in "ABC"}

    margins = []
    for pid in ranked:
        p, s = by_id[pid], sold[pid]
        if p.get("cost_price") is None or not s["priced_units"]:
            continue
        cost = s["priced_units"] * float(p["cost_price"])
        profit = s["revenue"] - cost
        margins.append({"product_id": pid, "sku": p["sku"], "name": p["name"], "units": s["units"],
                        "revenue": round(s["revenue"], 2), "cost": round(cost, 2), "profit": round(profit, 2),
                        "margin_pct": round(profit / s["revenue"] * 100, 1) if s["revenue"] else None})
    margins.sort(key=lambda r: -r["profit"])

    # ── Dead stock: in stock, but nothing went out for DEAD_DAYS ──
    cutoff = now - timedelta(days=DEAD_DAYS)
    moved = {r["product_id"] for r in (supabase.table("inventory_movements").select("product_id")
             .eq("business_id", business_id).eq("type", "outbound").gte("created_at", cutoff.isoformat())
             .limit(100000).execute().data or [])}
    last_out: dict[str, str] = {}
    for r in supabase.table("inventory_movements").select("product_id, created_at") \
            .eq("business_id", business_id).eq("type", "outbound").lt("created_at", cutoff.isoformat()) \
            .limit(100000).execute().data or []:
        last_out[r["product_id"]] = max(last_out.get(r["product_id"], ""), r["created_at"])
    dead = []
    for p in products:
        qty = stock.get(p["id"], 0)
        created = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")) if p.get("created_at") else now
        if qty > 0 and p["id"] not in moved and created < cutoff:
            value = qty * float(p["cost_price"]) if p.get("cost_price") is not None else None
            dead.append({"product_id": p["id"], "sku": p["sku"], "name": p["name"], "quantity": qty,
                         "unit": p.get("unit"), "value": round(value, 2) if value is not None else None,
                         "last_sale": (last_out.get(p["id"]) or "")[:10] or None})
    dead.sort(key=lambda r: -(r["value"] or 0))

    return {
        "days": days,
        "valuation": {"total": total_value, "items": valuation, "missing_cost": missing_cost,
                      "by_category": sorted(({"category": k, "value": round(v, 2)} for k, v in by_category.items()),
                                            key=lambda r: -r["value"])},
        "abc": {"items": abc, "no_sales": no_sales, "counts": counts, "revenue_share": revenue_share,
                "total_revenue": round(total_revenue, 2)},
        "margins": {"items": margins, "total_profit": round(sum(m["profit"] for m in margins), 2),
                    "total_revenue": round(sum(m["revenue"] for m in margins), 2)},
        "dead_stock": {"items": dead, "value": round(sum(d["value"] or 0 for d in dead), 2), "days": DEAD_DAYS},
    }
