from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from db.supabase_client import supabase
from services.forecasting import detect_anomalies, plan_reorders, plan_to_dict, product_forecast
from services.permissions import check_business_access
from services.stock import MOVEMENT_TYPES, apply_movement

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])


def _product_in_business(product_id: str, business_id: str) -> dict:
    p = supabase.table("products").select("id, name, sku") \
        .eq("id", product_id).eq("business_id", business_id).maybe_single().execute()
    if not p or not p.data:
        raise HTTPException(404, "Product not found")
    return p.data


@router.get("")
def list_inventory(business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    res = supabase.table("inventory_items") \
        .select("*, products(id, sku, name, category, unit, reorder_point, cost_price, sell_price, barcode, supplier, track_expiry)") \
        .eq("business_id", business_id).execute()
    return res.data or []


class MovementCreate(BaseModel):
    business_id: str
    product_id: str
    type: str
    quantity: int = Field(ge=0)
    reason: Optional[str] = None
    order_id: Optional[str] = None
    lot_code: Optional[str] = Field(default=None, max_length=80)
    expiry_date: Optional[date] = None


@router.post("/movement")
def record_movement(body: MovementCreate, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, body.business_id)
    if body.type not in MOVEMENT_TYPES:
        raise HTTPException(400, "Invalid movement type")
    _product_in_business(body.product_id, body.business_id)

    movement = apply_movement(
        business_id=body.business_id, product_id=body.product_id, type=body.type,
        quantity=body.quantity, user_id=user_id, reason=body.reason, order_id=body.order_id,
        lot_code=body.lot_code, expiry_date=body.expiry_date,
    )
    return {"movement": movement, "new_quantity": movement["new_quantity"]}


@router.get("/movements")
def list_movements(
    business_id: str,
    product_id: Optional[str] = None,
    user_id: str = Depends(get_current_user),
):
    check_business_access(user_id, business_id)
    query = supabase.table("inventory_movements") \
        .select("*, products(sku, name)") \
        .eq("business_id", business_id) \
        .order("created_at", desc=True) \
        .limit(200)
    if product_id:
        query = query.eq("product_id", product_id)
    return query.execute().data or []


# ── Forecast-based reorder planning ───────────────────────────────────────────

@router.get("/reorder-suggestions")
def reorder_suggestions(business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    plans = [p for p in plan_reorders(business_id) if p.urgency != "ok"]
    plans.sort(key=lambda p: (0 if p.urgency == "critical" else 1,
                              p.days_until_stockout if p.days_until_stockout is not None else 999))
    return [plan_to_dict(p) for p in plans]


@router.get("/forecast/{product_id}")
def get_product_forecast(product_id: str, business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    _product_in_business(product_id, business_id)
    plan = plan_reorders(business_id, [product_id])
    return {**product_forecast(business_id, product_id), "plan": plan_to_dict(plan[0]) if plan else None}


class PurchaseOrdersRequest(BaseModel):
    business_id: str
    # product_id -> quantity; omitted products use the suggested quantity
    quantities: dict[str, int] = {}
    product_ids: Optional[list[str]] = None


@router.post("/reorder/purchase-orders")
def create_purchase_orders(body: PurchaseOrdersRequest, user_id: str = Depends(get_current_user)):
    """Turn reorder suggestions into draft purchase orders, one per supplier."""
    check_business_access(user_id, body.business_id)
    plans = plan_reorders(body.business_id, body.product_ids)
    if not body.product_ids:
        plans = [p for p in plans if p.urgency != "ok"]

    by_supplier: dict[str, list] = defaultdict(list)
    for p in plans:
        qty = body.quantities.get(p.product_id, p.suggested_qty)
        if qty > 0:
            by_supplier[p.supplier_id or ""].append((p, qty))
    if not by_supplier:
        raise HTTPException(400, "Nothing to order")

    created = []
    for supplier_id, lines in by_supplier.items():
        order = supabase.table("orders").insert({
            "business_id": body.business_id, "type": "purchase", "status": "draft",
            "supplier_id": supplier_id or None, "party_name": lines[0][0].supplier,
            "notes": "Reorder suggestion", "created_by": user_id,
        }).execute().data[0]
        supabase.table("order_items").insert([{
            "order_id": order["id"], "product_id": p.product_id, "quantity": qty, "unit_price": p.cost_price,
        } for p, qty in lines]).execute()
        created.append({**order, "lines": len(lines)})
    return created


# ── Lots & expiry ─────────────────────────────────────────────────────────────

@router.get("/lots")
def list_lots(business_id: str, expiring_within_days: Optional[int] = None, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    q = supabase.table("inventory_lots") \
        .select("*, products(sku, name, unit)") \
        .eq("business_id", business_id).gt("quantity", 0) \
        .order("expiry_date", desc=False)
    if expiring_within_days is not None:
        until = (datetime.now(timezone.utc).date() + timedelta(days=expiring_within_days)).isoformat()
        q = q.lte("expiry_date", until)
    return q.execute().data or []


# ── Stock-take ────────────────────────────────────────────────────────────────

class StocktakeLine(BaseModel):
    product_id: str
    counted: int = Field(ge=0)


class StocktakeRequest(BaseModel):
    business_id: str
    lines: list[StocktakeLine] = Field(min_length=1, max_length=5000)
    note: Optional[str] = Field(default=None, max_length=200)


@router.post("/stocktake")
def apply_stocktake(body: StocktakeRequest, user_id: str = Depends(get_current_user)):
    """Set counted quantities; only products whose count differs get an adjustment."""
    check_business_access(user_id, body.business_id)
    current = {r["product_id"]: r["quantity"] for r in (supabase.table("inventory_items")
               .select("product_id, quantity").eq("business_id", body.business_id).execute().data or [])}
    owned = {r["id"] for r in (supabase.table("products").select("id")
             .eq("business_id", body.business_id).execute().data or [])}

    changed = []
    for line in body.lines:
        if line.product_id not in owned:
            raise HTTPException(400, "Unknown product in stock-take")
        before = current.get(line.product_id, 0)
        if before == line.counted:
            continue
        apply_movement(business_id=body.business_id, product_id=line.product_id, type="adjustment",
                       quantity=line.counted, user_id=user_id, reason=body.note or "Stock-take")
        changed.append({"product_id": line.product_id, "before": before, "after": line.counted})
    return {"changed": changed, "unchanged": len(body.lines) - len(changed)}


# ── Unusual activity ──────────────────────────────────────────────────────────

@router.get("/anomalies")
def anomalies(business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    return detect_anomalies(business_id)
