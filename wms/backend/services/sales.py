"""Record sales that happened in another system (invoicing software, e-shop, file)."""
from db.supabase_client import supabase
from services.stock import apply_movement


def product_index(business_id: str) -> dict[str, dict]:
    """Lookup by lower-case SKU and by barcode."""
    rows = supabase.table("products").select("id, sku, barcode").eq("business_id", business_id).execute().data or []
    index: dict[str, dict] = {}
    for p in rows:
        index[p["sku"].strip().lower()] = p
        if p.get("barcode"):
            index.setdefault(p["barcode"].strip(), p)
    return index


def record_sale(
    *,
    business_id: str,
    external_ref: str,
    party: str | None,
    lines: list[tuple[str, int, float | None]],   # (product_id, quantity, unit price)
    note: str | None = None,
    at: str | None = None,
    affect_stock: bool = True,
    user_id: str | None = None,
) -> dict | None:
    """Create a completed sale order and its stock movements.
    Returns None when `external_ref` was already imported (so re-syncs are safe)."""
    exists = supabase.table("orders").select("id").eq("business_id", business_id) \
        .eq("external_ref", external_ref).limit(1).execute().data
    if exists:
        return None
    try:
        order = supabase.table("orders").insert({
            "business_id": business_id, "type": "sale", "status": "completed",
            "party_name": party, "notes": note, "external_ref": external_ref, "created_by": user_id,
            **({"created_at": at} if at else {}),
        }).execute().data[0]
    except Exception:
        return None  # lost a race with a concurrent sync: the unique index kept it single
    supabase.table("order_items").insert([
        {"order_id": order["id"], "product_id": pid, "quantity": qty, "unit_price": price}
        for pid, qty, price in lines
    ]).execute()
    for pid, qty, _ in lines:
        apply_movement(business_id=business_id, product_id=pid, type="outbound", quantity=qty,
                       user_id=user_id, reason=note, order_id=order["id"], at=at, affect_stock=affect_stock)
    return order
