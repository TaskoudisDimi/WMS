"""
Per-product demand forecasting and reorder planning from the business's own
stock movements — no CSV upload needed.

Model (deliberately simple and explainable):
  • daily outbound quantities for the last HISTORY_DAYS days
  • weekday factors (shrunk towards 1) when there are at least 4 weeks of history
  • a level from the 7-day rolling mean, exponentially smoothed (recent weeks count more)
  • residual spread → safety stock for a 95% service level

Also flags unusual activity (sudden drops/spikes, stock lost through recounts,
revenue drop) for the dashboard and alert emails.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone

from db.supabase_client import supabase

HISTORY_DAYS = 84          # 12 weeks
REVIEW_DAYS = 14           # an order should cover lead time + two weeks
SERVICE_Z = 1.65           # ~95% chance of not running out during lead time
ALPHA = 0.12               # smoothing: higher = reacts faster to recent days


@dataclass
class ProductPlan:
    product_id: str
    sku: str
    name: str
    category: str | None
    unit: str | None
    supplier: str | None
    supplier_id: str | None
    cost_price: float | None
    current_stock: int
    on_order: int
    reorder_point: int
    lead_time_days: int
    avg_daily: float               # forecast daily demand (level)
    forecast_7: float
    forecast_30: float
    safety_stock: int
    suggested_qty: int
    days_until_stockout: float | None
    reorder_by: str | None         # ISO date: place the order by this day
    urgency: str                   # critical | warning | ok
    history_days: int

    # kept for the existing UI
    @property
    def avg_daily_outbound(self) -> float:
        return round(self.avg_daily, 2)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _daily_outbound(business_id: str, since: date) -> dict[str, dict[date, int]]:
    rows = supabase.table("inventory_movements") \
        .select("product_id, quantity, created_at") \
        .eq("business_id", business_id).eq("type", "outbound") \
        .gte("created_at", since.isoformat()).limit(100000).execute().data or []
    out: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        d = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).date()
        out[r["product_id"]][d] += r["quantity"]
    return out


def _on_order(business_id: str) -> dict[str, int]:
    """Units already ordered from suppliers but not received yet."""
    orders = supabase.table("orders").select("id") \
        .eq("business_id", business_id).eq("type", "purchase") \
        .in_("status", ["draft", "confirmed"]).execute().data or []
    if not orders:
        return {}
    items = supabase.table("order_items").select("product_id, quantity") \
        .in_("order_id", [o["id"] for o in orders]).execute().data or []
    totals: dict[str, int] = defaultdict(int)
    for it in items:
        totals[it["product_id"]] += it["quantity"]
    return totals


def fit_series(series: dict[date, int], start: date, end: date) -> tuple[float, list[float], float, int]:
    """Return (level, weekday_factors[7], residual_sd, history_days) for one product."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    values = [series.get(d, 0) for d in days]
    n = len(values)
    total = sum(values)
    if n == 0 or total == 0:
        return 0.0, [1.0] * 7, 0.0, n

    mean = total / n
    factors = [1.0] * 7
    if n >= 28:
        by_wd: dict[int, list[int]] = defaultdict(list)
        for d, v in zip(days, values):
            by_wd[d.weekday()].append(v)
        for wd in range(7):
            raw = (sum(by_wd[wd]) / len(by_wd[wd])) / mean if by_wd[wd] else 1.0
            factors[wd] = 0.6 * raw + 0.4  # shrink towards 1 so a few odd days don't dominate
        norm = sum(factors) / 7
        factors = [f / norm for f in factors]

    # Level: smoothed 7-day rolling mean. A full week averages out the weekday
    # pattern, so the level stays unbiased (de-seasonalising day by day with
    # shrunk factors under-forecasts).
    if n < 7:
        level = mean
        rolling = [mean] * n
    else:
        rolling = [mean] * 6 + [sum(values[i - 6:i + 1]) / 7 for i in range(6, n)]
        level = rolling[6]
        for m in rolling[7:]:
            level = ALPHA * m + (1 - ALPHA) * level

    residuals = [v - r * factors[d.weekday()] for d, v, r in zip(days, values, rolling)]
    sd = math.sqrt(sum(x * x for x in residuals) / max(n - 1, 1))
    return level, factors, sd, n


def forecast_days(level: float, factors: list[float], start: date, days: int) -> list[float]:
    return [level * factors[(start + timedelta(days=i)).weekday()] for i in range(days)]


def plan_reorders(business_id: str, product_ids: list[str] | None = None) -> list[ProductPlan]:
    today = _today()
    start = today - timedelta(days=HISTORY_DAYS)

    q = supabase.table("products") \
        .select("id, sku, name, category, unit, supplier, supplier_id, cost_price, reorder_point, lead_time_days, "
                "min_order_qty, order_multiple, created_at") \
        .eq("business_id", business_id)
    if product_ids:
        q = q.in_("id", product_ids)
    products = q.execute().data or []
    stock = {r["product_id"]: r["quantity"] for r in (supabase.table("inventory_items")
             .select("product_id, quantity").eq("business_id", business_id).execute().data or [])}
    outbound = _daily_outbound(business_id, start)
    on_order = _on_order(business_id)

    plans = []
    for p in products:
        created = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).date() if p.get("created_at") else start
        series_start = max(start, created)
        level, factors, sd, hist = fit_series(outbound.get(p["id"], {}), series_start, today - timedelta(days=1))
        lead = max(int(p.get("lead_time_days") or 7), 1)
        on_hand = int(stock.get(p["id"], 0))
        incoming = int(on_order.get(p["id"], 0))
        reorder_point = int(p.get("reorder_point") or 0)

        horizon = forecast_days(level, factors, today, max(lead + REVIEW_DAYS, 30))
        f7, f30 = sum(horizon[:7]), sum(horizon[:30])
        lead_demand = sum(horizon[:lead])
        safety = math.ceil(SERVICE_Z * sd * math.sqrt(lead)) if level > 0 else 0
        reorder_level = max(math.ceil(lead_demand + safety), reorder_point)

        # Walk forward day by day: when does stock run out / hit the reorder level?
        days_out = None
        reorder_in = None
        remaining = on_hand
        position = on_hand + incoming
        long_horizon = forecast_days(level, factors, today, 365) if level > 0 else []
        for i, demand in enumerate(long_horizon):
            if reorder_in is None and position - lead_demand - safety <= 0:
                reorder_in = i
            remaining -= demand
            position -= demand
            if remaining <= 0:
                days_out = round(i + 1 + remaining / demand, 1) if demand else float(i + 1)
                break
        if level > 0 and reorder_in is None and position <= reorder_level:
            reorder_in = 0
        if on_hand <= reorder_point:
            reorder_in = 0

        cover = sum(horizon[:lead + REVIEW_DAYS])
        suggested = max(0, math.ceil(cover + safety - on_hand - incoming)) if (level > 0 or on_hand <= reorder_point) else 0
        if suggested == 0 and on_hand + incoming <= reorder_point:
            suggested = max(reorder_point * 2 - on_hand - incoming, 1)
        if suggested > 0:
            # Respect the supplier's minimum and pack size (e.g. boxes of 12)
            suggested = max(suggested, int(p.get("min_order_qty") or 0))
            pack = max(int(p.get("order_multiple") or 1), 1)
            suggested = math.ceil(suggested / pack) * pack

        if on_hand <= reorder_point or (days_out is not None and days_out <= lead):
            urgency = "critical"
        elif reorder_in is not None and reorder_in <= 7:
            urgency = "warning"
        else:
            urgency = "ok"

        plans.append(ProductPlan(
            product_id=p["id"], sku=p["sku"], name=p["name"], category=p.get("category"), unit=p.get("unit"),
            supplier=p.get("supplier"), supplier_id=p.get("supplier_id"), cost_price=p.get("cost_price"),
            current_stock=on_hand, on_order=incoming, reorder_point=reorder_point, lead_time_days=lead,
            avg_daily=round(level, 2), forecast_7=round(f7, 1), forecast_30=round(f30, 1),
            safety_stock=safety, suggested_qty=suggested,
            days_until_stockout=days_out,
            reorder_by=(today + timedelta(days=reorder_in)).isoformat() if reorder_in is not None else None,
            urgency=urgency, history_days=hist,
        ))
    return plans


def plan_to_dict(plan: ProductPlan) -> dict:
    d = asdict(plan)
    d["avg_daily_outbound"] = plan.avg_daily_outbound
    return d


def product_forecast(business_id: str, product_id: str, days: int = 28) -> dict:
    """Last 4 weeks actual vs next `days` forecast, for a chart."""
    today = _today()
    start = today - timedelta(days=HISTORY_DAYS)
    series = _daily_outbound(business_id, start).get(product_id, {})
    level, factors, sd, hist = fit_series(series, start, today - timedelta(days=1))
    past = [{"date": (today - timedelta(days=i)).isoformat(), "actual": series.get(today - timedelta(days=i), 0)}
            for i in range(28, 0, -1)]
    future = [{"date": (today + timedelta(days=i)).isoformat(), "forecast": round(v, 2)}
              for i, v in enumerate(forecast_days(level, factors, today, days))]
    return {"history": past, "forecast": future, "avg_daily": round(level, 2), "history_days": hist}


# ── Unusual activity ──────────────────────────────────────────────────────────

def detect_anomalies(business_id: str) -> list[dict]:
    today = _today()
    since = today - timedelta(days=70)
    products = {p["id"]: p for p in (supabase.table("products").select("id, sku, name, unit")
                .eq("business_id", business_id).execute().data or [])}
    rows = supabase.table("inventory_movements") \
        .select("product_id, type, quantity, delta, created_at") \
        .eq("business_id", business_id).gte("created_at", since.isoformat()).limit(100000).execute().data or []

    # Two-week windows: B2B customers order in lumps, so a single quiet week is normal
    recent: dict[str, int] = defaultdict(int)      # outbound, last 14 days
    baseline: dict[str, int] = defaultdict(int)    # outbound, days 15–70 ago (8 weeks)
    outbound_30: dict[str, int] = defaultdict(int)
    lost_30: dict[str, int] = defaultdict(int)     # stock removed by recounts
    for r in rows:
        d = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).date()
        age = (today - d).days
        if r["type"] == "outbound":
            if age < 14:
                recent[r["product_id"]] += r["quantity"]
            else:
                baseline[r["product_id"]] += r["quantity"]
            if age < 30:
                outbound_30[r["product_id"]] += r["quantity"]
        elif r["type"] == "adjustment" and (r.get("delta") or 0) < 0 and age < 30:
            lost_30[r["product_id"]] += -r["delta"]

    found = []
    for pid, p in products.items():
        expected = baseline[pid] / 4        # 8 weeks of baseline → per two weeks
        actual = recent[pid]
        if expected >= 14 and actual < 0.35 * expected:
            found.append({"kind": "sales_drop", "severity": "warning" if actual else "critical",
                          "product_id": pid, "sku": p["sku"], "name": p["name"],
                          "actual": actual, "expected": round(expected, 1)})
        elif expected >= 8 and actual > 2.5 * expected and actual >= 20:
            found.append({"kind": "sales_spike", "severity": "info",
                          "product_id": pid, "sku": p["sku"], "name": p["name"],
                          "actual": actual, "expected": round(expected, 1)})
        lost = lost_30[pid]
        if lost >= max(5, 0.1 * outbound_30[pid]):
            found.append({"kind": "stock_loss", "severity": "warning",
                          "product_id": pid, "sku": p["sku"], "name": p["name"],
                          "actual": lost, "expected": 0})

    revenue = _weekly_revenue(business_id, today)
    if revenue["baseline"] > 0 and revenue["last_7"] < 0.6 * revenue["baseline"]:
        found.append({"kind": "revenue_drop", "severity": "warning",
                      "actual": round(revenue["last_7"], 2), "expected": round(revenue["baseline"], 2)})

    order = {"critical": 0, "warning": 1, "info": 2}
    found.sort(key=lambda a: order.get(a["severity"], 3))
    return found


def _weekly_revenue(business_id: str, today: date) -> dict:
    since = today - timedelta(days=35)
    orders = supabase.table("orders").select("id, created_at") \
        .eq("business_id", business_id).eq("type", "sale").eq("status", "completed") \
        .gte("created_at", since.isoformat()).execute().data or []
    if not orders:
        return {"last_7": 0.0, "baseline": 0.0}
    age = {o["id"]: (today - datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")).date()).days for o in orders}
    items = supabase.table("order_items").select("order_id, quantity, unit_price") \
        .in_("order_id", list(age)).execute().data or []
    last_7 = sum(i["quantity"] * (i["unit_price"] or 0) for i in items if age[i["order_id"]] < 7)
    prev = sum(i["quantity"] * (i["unit_price"] or 0) for i in items if 7 <= age[i["order_id"]] < 35)
    return {"last_7": last_7, "baseline": prev / 4}
