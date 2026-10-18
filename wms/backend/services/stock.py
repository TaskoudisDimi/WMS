"""Single place where stock changes happen, so orders, manual movements, stock-takes
and e-shop webhooks all update inventory, lots and the movement log the same way."""
from datetime import date
from db.supabase_client import supabase

MOVEMENT_TYPES = ("inbound", "outbound", "adjustment")


def apply_movement(
    *,
    business_id: str,
    product_id: str,
    type: str,
    quantity: int,
    user_id: str | None,
    reason: str | None = None,
    order_id: str | None = None,
    lot_code: str | None = None,
    expiry_date: date | str | None = None,
    at: str | None = None,
    affect_stock: bool = True,
) -> dict:
    """Record a movement and update stock atomically.

    inbound/outbound: `quantity` is the amount moved.
    adjustment: `quantity` is the new counted total.
    at: when it happened (ISO), for history imported from elsewhere.
    affect_stock=False records the movement (so forecasts learn from it) without
    changing stock — for past sales the current count already reflects.
    Returns the inserted movement with `new_quantity`.
    """
    if type not in MOVEMENT_TYPES:
        raise ValueError(f"invalid movement type {type!r}")

    delta = quantity if type == "inbound" else -quantity if type == "outbound" else 0
    if not affect_stock:
        row = supabase.table("inventory_movements").insert({
            "product_id": product_id, "business_id": business_id, "type": type, "quantity": quantity,
            "delta": 0, "reason": reason, "order_id": order_id, "created_by": user_id,
            **({"created_at": at} if at else {}),
        }).execute()
        return {**(row.data[0] if row.data else {}), "new_quantity": None}

    res = supabase.rpc("wms_adjust_stock", {
        "p_business": business_id,
        "p_product": product_id,
        "p_delta": delta,
        "p_absolute": quantity if type == "adjustment" else None,
    }).execute()
    row = res.data[0]
    old_qty, new_qty = row["old_quantity"], row["new_quantity"]

    lot_id = None
    if type == "inbound" and (lot_code or expiry_date):
        lot = supabase.table("inventory_lots").insert({
            "business_id": business_id,
            "product_id": product_id,
            "lot_code": lot_code or None,
            "expiry_date": str(expiry_date) if expiry_date else None,
            "quantity": quantity,
        }).execute()
        lot_id = lot.data[0]["id"]
    elif new_qty < old_qty:
        # Stock left the shelf (sale, loss, recount) — use up the oldest lots first
        supabase.rpc("wms_consume_lots", {"p_product": product_id, "p_qty": old_qty - new_qty}).execute()

    movement = supabase.table("inventory_movements").insert({
        "product_id": product_id,
        "business_id": business_id,
        "type": type,
        "quantity": quantity,
        "delta": new_qty - old_qty,
        "reason": reason,
        "order_id": order_id,
        "lot_id": lot_id,
        "created_by": user_id,
        **({"created_at": at} if at else {}),
    }).execute()

    return {**(movement.data[0] if movement.data else {}), "new_quantity": new_qty}
