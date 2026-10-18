from datetime import date
from datetime import date as Date  # field below is named `date`
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Optional, List
from core.security import get_current_user
from db.supabase_client import supabase
from services.permissions import check_business_access
from services.stock import apply_movement
from services import mailer
from services.documents import purchase_order_pdf
from services.sales import product_index, record_sale
from datetime import datetime, timezone
from pydantic import EmailStr
from typing import Literal

router = APIRouter(prefix="/api/orders", tags=["Orders"])


class OrderItemIn(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)
    lot_code: Optional[str] = Field(default=None, max_length=80)
    expiry_date: Optional[date] = None


class OrderCreate(BaseModel):
    business_id: str
    type: str
    supplier_id: Optional[str] = None
    party_name: Optional[str] = None
    notes: Optional[str] = None
    items: List[OrderItemIn] = []


class StatusUpdate(BaseModel):
    status: str


@router.get("")
def list_orders(
    business_id: str,
    type: Optional[str] = None,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user),
):
    check_business_access(user_id, business_id)
    query = supabase.table("orders").select("*") \
        .eq("business_id", business_id).order("created_at", desc=True)
    if type:
        query = query.eq("type", type)
    if status:
        query = query.eq("status", status)
    return query.execute().data or []


@router.post("")
def create_order(body: OrderCreate, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, body.business_id)
    if body.type not in ("purchase", "sale"):
        raise HTTPException(400, "Invalid order type")

    product_ids = {item.product_id for item in body.items}
    if product_ids:
        owned = supabase.table("products").select("id") \
            .eq("business_id", body.business_id).in_("id", list(product_ids)).execute()
        if len(owned.data or []) != len(product_ids):
            raise HTTPException(400, "Unknown product in order")

    party_name = body.party_name
    if body.supplier_id:
        sup = supabase.table("suppliers").select("name").eq("id", body.supplier_id) \
            .eq("business_id", body.business_id).maybe_single().execute()
        if not sup or not sup.data:
            raise HTTPException(400, "Unknown supplier")
        party_name = party_name or sup.data["name"]

    order_res = supabase.table("orders").insert({
        "business_id": body.business_id,
        "type": body.type,
        "status": "draft",
        "supplier_id": body.supplier_id,
        "party_name": party_name,
        "notes": body.notes,
        "created_by": user_id,
    }).execute()

    if not order_res.data:
        raise HTTPException(500, "Failed to create order")

    order = order_res.data[0]

    if body.items:
        supabase.table("order_items").insert([
            {
                "order_id": order["id"],
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "lot_code": item.lot_code,
                "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
            }
            for item in body.items
        ]).execute()

    return order


@router.get("/{order_id}")
def get_order(order_id: str, user_id: str = Depends(get_current_user)):
    order = supabase.table("orders").select("*") \
        .eq("id", order_id).maybe_single().execute()
    if not order or not order.data:
        raise HTTPException(404, "Order not found")
    check_business_access(user_id, order.data["business_id"])
    items = supabase.table("order_items") \
        .select("*, products(sku, name, unit)") \
        .eq("order_id", order_id).execute()
    return {**order.data, "items": items.data or []}


@router.patch("/{order_id}/status")
def update_status(
    order_id: str,
    body: StatusUpdate,
    user_id: str = Depends(get_current_user),
):
    if body.status not in ("draft", "confirmed", "cancelled"):
        raise HTTPException(400, "Invalid status")
    order = supabase.table("orders").select("*") \
        .eq("id", order_id).maybe_single().execute()
    if not order or not order.data:
        raise HTTPException(404, "Order not found")
    check_business_access(user_id, order.data["business_id"])
    if order.data["status"] == "completed":
        raise HTTPException(400, "Completed orders can't change status")
    res = supabase.table("orders").update({"status": body.status}).eq("id", order_id).execute()
    return res.data[0]


@router.post("/{order_id}/complete")
def complete_order(order_id: str, user_id: str = Depends(get_current_user)):
    order = supabase.table("orders").select("*") \
        .eq("id", order_id).maybe_single().execute()
    if not order or not order.data:
        raise HTTPException(404, "Order not found")
    check_business_access(user_id, order.data["business_id"])

    # Claim the order atomically first, so two concurrent requests can't both
    # apply the stock movements
    claimed = supabase.table("orders").update({"status": "completed"}) \
        .eq("id", order_id).in_("status", ["draft", "confirmed"]).execute()
    if not claimed.data:
        raise HTTPException(400, "Order is already completed or cancelled")

    items = supabase.table("order_items").select("product_id, quantity, lot_code, expiry_date") \
        .eq("order_id", order_id).execute()

    movement_type = "inbound" if order.data["type"] == "purchase" else "outbound"
    for item in (items.data or []):
        apply_movement(
            business_id=order.data["business_id"], product_id=item["product_id"], type=movement_type,
            quantity=item["quantity"], user_id=user_id, reason=f"Order #{order_id[:8]}", order_id=order_id,
            lot_code=item.get("lot_code"), expiry_date=item.get("expiry_date"),
        )

    return claimed.data[0]


# ── Purchase order PDF / email to supplier ────────────────────────────────────

def _po_context(order_id: str, user_id: str) -> tuple[dict, list, dict, dict | None, dict]:
    order = supabase.table("orders").select("*").eq("id", order_id).maybe_single().execute()
    if not order or not order.data:
        raise HTTPException(404, "Order not found")
    order = order.data
    check_business_access(user_id, order["business_id"])
    if order["type"] != "purchase":
        raise HTTPException(400, "Only purchase orders can be sent to suppliers")
    items = supabase.table("order_items").select("quantity, unit_price, products(sku, name, unit)") \
        .eq("order_id", order_id).execute().data or []
    business = supabase.table("businesses").select("name").eq("id", order["business_id"]).single().execute().data
    supplier = None
    if order.get("supplier_id"):
        s = supabase.table("suppliers").select("*").eq("id", order["supplier_id"]).maybe_single().execute()
        supplier = s.data if s else None
    profile = supabase.table("users").select("full_name").eq("id", user_id).maybe_single().execute()
    email = supabase.auth.admin.get_user_by_id(user_id).user.email
    contact = {"name": (profile.data or {}).get("full_name") if profile else None, "email": email}
    return order, items, business, supplier, contact


@router.get("/{order_id}/pdf")
def order_pdf(order_id: str, lang: Literal["el", "en"] = "el", user_id: str = Depends(get_current_user)):
    order, items, business, supplier, contact = _po_context(order_id, user_id)
    pdf = purchase_order_pdf(order, items, business, supplier, contact, lang)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="PO-{order_id[:8].upper()}.pdf"'})


class SendRequest(BaseModel):
    to: Optional[EmailStr] = None
    message: Optional[str] = Field(default=None, max_length=2000)
    lang: Literal["el", "en"] = "el"


@router.post("/{order_id}/send")
def send_to_supplier(order_id: str, body: SendRequest, user_id: str = Depends(get_current_user)):
    if not mailer.is_configured():
        raise HTTPException(400, "Email sending is not configured on the server")
    order, items, business, supplier, contact = _po_context(order_id, user_id)
    to = body.to or (supplier or {}).get("email")
    if not to:
        raise HTTPException(400, "The supplier has no email address")
    if order["status"] == "cancelled":
        raise HTTPException(400, "Cancelled orders can't be sent")

    number = order_id[:8].upper()
    pdf = purchase_order_pdf(order, items, business, supplier, contact, body.lang)
    el = body.lang == "el"
    subject = f"Παραγγελία {number} — {business['name']}" if el else f"Purchase order {number} — {business['name']}"
    default = ("Καλησπέρα,\n\nσας επισυνάπτουμε την παραγγελία μας. Παρακαλούμε επιβεβαιώστε διαθεσιμότητα και ημερομηνία παράδοσης."
               if el else "Hello,\n\nplease find our purchase order attached. Kindly confirm availability and delivery date.")
    text = f"{body.message or default}\n\n{contact.get('name') or ''}\n{business['name']}\n{contact['email']}".strip()
    mailer.send(to, subject, text, attachments=[(f"PO-{number}.pdf", pdf, "application/pdf")], reply_to=contact["email"])

    fields: dict = {"sent_at": datetime.now(timezone.utc).isoformat()}
    if order["status"] == "draft":
        fields["status"] = "confirmed"
    supabase.table("orders").update(fields).eq("id", order_id).execute()
    return {"sent_to": to}


# ── Sales from another program (CSV/Excel export) ─────────────────────────────

class SaleRow(BaseModel):
    document: Optional[str] = Field(default=None, max_length=80)
    date: Optional[Date] = None
    customer: Optional[str] = Field(default=None, max_length=200)
    sku: str = Field(min_length=1, max_length=64)
    quantity: float = Field(gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)


class SalesImport(BaseModel):
    business_id: str
    rows: list[SaleRow] = Field(min_length=1, max_length=20000)
    # Past sales the current stock count already reflects: record for forecasts only
    update_stock: bool = True


@router.post("/import-sales")
def import_sales(body: SalesImport, user_id: str = Depends(get_current_user)):
    """Group rows into documents and record each as a completed sale, once."""
    check_business_access(user_id, body.business_id)
    index = product_index(body.business_id)
    docs: dict[str, dict] = {}
    unmatched: set[str] = set()
    for r in body.rows:
        product = index.get(r.sku.strip().lower()) or index.get(r.sku.strip())
        if not product:
            unmatched.add(r.sku.strip())
            continue
        key = r.document or f"{r.date or ''}|{r.customer or ''}"
        d = docs.setdefault(key, {"date": r.date, "customer": r.customer, "lines": {}})
        price_qty = d["lines"].setdefault(product["id"], [0, r.unit_price])
        price_qty[0] += int(round(r.quantity))

    created = skipped = 0
    for key, d in docs.items():
        order = record_sale(
            business_id=body.business_id, external_ref=f"file:{key}", party=d["customer"],
            lines=[(pid, qty, price) for pid, (qty, price) in d["lines"].items() if qty > 0],
            note=f"Import {key}" if not key.startswith("|") else "Import",
            at=f"{d['date'].isoformat()}T12:00:00+00:00" if d["date"] else None,
            affect_stock=body.update_stock, user_id=user_id,
        )
        created += 1 if order else 0
        skipped += 0 if order else 1
    return {"created": created, "skipped": skipped, "unmatched_skus": sorted(unmatched)[:100]}
