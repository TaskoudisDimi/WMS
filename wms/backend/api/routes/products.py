from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from core.security import get_current_user
from db.supabase_client import supabase
from services.permissions import check_business_access
from services.stock import apply_movement
from services.suppliers import resolve_supplier

router = APIRouter(prefix="/api/products", tags=["Products"])

EDITABLE = ("sku", "name", "category", "unit", "reorder_point", "cost_price", "sell_price",
            "barcode", "supplier", "supplier_id", "lead_time_days", "track_expiry",
            "min_order_qty", "order_multiple")


class ProductFields(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: Optional[str] = Field(default=None, max_length=100)
    unit: str = Field(default="τεμ", max_length=20)
    reorder_point: int = Field(default=0, ge=0)
    cost_price: Optional[float] = Field(default=None, ge=0)
    sell_price: Optional[float] = Field(default=None, ge=0)
    barcode: Optional[str] = Field(default=None, max_length=64)
    supplier: Optional[str] = Field(default=None, max_length=120)
    supplier_id: Optional[str] = None
    lead_time_days: int = Field(default=7, ge=1, le=365)
    track_expiry: bool = False
    min_order_qty: int = Field(default=0, ge=0)
    order_multiple: int = Field(default=1, ge=1)


class ProductCreate(ProductFields):
    business_id: str


class ProductUpdate(BaseModel):
    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[str] = None
    unit: Optional[str] = None
    reorder_point: Optional[int] = Field(default=None, ge=0)
    cost_price: Optional[float] = Field(default=None, ge=0)
    sell_price: Optional[float] = Field(default=None, ge=0)
    barcode: Optional[str] = None
    supplier: Optional[str] = None
    supplier_id: Optional[str] = None
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=365)
    track_expiry: Optional[bool] = None
    min_order_qty: Optional[int] = Field(default=None, ge=0)
    order_multiple: Optional[int] = Field(default=None, ge=1)


def _with_supplier(business_id: str, fields: dict, cache: dict | None = None) -> dict:
    """Keep supplier_id and the denormalised supplier name consistent.
    A supplier_id wins; otherwise a supplier name is resolved (created if new)."""
    if fields.get("supplier_id"):
        row = supabase.table("suppliers").select("name").eq("id", fields["supplier_id"]) \
            .eq("business_id", business_id).maybe_single().execute()
        if not row or not row.data:
            raise HTTPException(400, "Unknown supplier")
        fields["supplier"] = row.data["name"]
    elif "supplier_id" in fields:          # explicitly cleared
        fields["supplier"] = None
    elif fields.get("supplier"):
        fields["supplier_id"] = resolve_supplier(business_id, fields["supplier"], cache)
    return fields


def _clean(fields: dict) -> dict:
    """Trim strings; empty optional strings become NULL."""
    out = {}
    for k, v in fields.items():
        if isinstance(v, str):
            v = v.strip()
            if v == "" and k not in ("sku", "name"):
                v = None
        out[k] = v
    return out


@router.get("")
def list_products(business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    res = supabase.table("products").select("*") \
        .eq("business_id", business_id).order("created_at").execute()
    return res.data or []


@router.get("/lookup")
def lookup_product(business_id: str, code: str, user_id: str = Depends(get_current_user)):
    """Find a product by scanned barcode, falling back to SKU."""
    check_business_access(user_id, business_id)
    code = code.strip()
    for column in ("barcode", "sku"):
        res = supabase.table("products").select("*") \
            .eq("business_id", business_id).eq(column, code).limit(1).execute()
        if res.data:
            return res.data[0]
    raise HTTPException(404, "No product with this code")


@router.post("")
def create_product(body: ProductCreate, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, body.business_id)
    fields = _with_supplier(body.business_id, _clean(body.model_dump(include=set(EDITABLE))))
    res = supabase.table("products").insert({"business_id": body.business_id, **fields}).execute()
    if not res.data:
        raise HTTPException(500, "Failed to create product")
    product = res.data[0]
    supabase.table("inventory_items").insert({
        "product_id": product["id"],
        "business_id": body.business_id,
        "quantity": 0,
    }).execute()
    return product


class ImportRow(ProductFields):
    initial_stock: Optional[int] = Field(default=None, ge=0)


class ImportRequest(BaseModel):
    business_id: str
    rows: list[ImportRow] = Field(min_length=1, max_length=5000)
    update_existing: bool = True


@router.post("/import")
def import_products(body: ImportRequest, user_id: str = Depends(get_current_user)):
    """Bulk create/update products by SKU (from a CSV/Excel file parsed in the browser).
    `initial_stock` sets the counted quantity through a stock adjustment."""
    check_business_access(user_id, body.business_id)

    seen, rows = set(), []
    for r in body.rows:  # last row wins for duplicate SKUs in the file
        key = r.sku.strip().lower()
        if key in seen:
            rows = [x for x in rows if x.sku.strip().lower() != key]
        seen.add(key)
        rows.append(r)

    existing = {p["sku"].lower(): p for p in (supabase.table("products").select("id, sku")
                .eq("business_id", body.business_id).execute().data or [])}
    to_create, to_update, skipped = [], [], 0
    supplier_cache: dict = {}
    for r in rows:
        fields = _with_supplier(body.business_id, _clean(r.model_dump(include=set(EDITABLE), exclude_unset=True)
                                                        | {"sku": r.sku, "name": r.name}), supplier_cache)
        match = existing.get(r.sku.strip().lower())
        if match and not body.update_existing:
            skipped += 1
        elif match:
            fields.pop("sku")  # keep the existing SKU's casing; it's the identity
            to_update.append((match["id"], fields, r.initial_stock))
        else:
            to_create.append((fields, r.initial_stock))

    created_ids = []
    for i in range(0, len(to_create), 500):
        chunk = to_create[i:i + 500]
        res = supabase.table("products").insert(
            [{"business_id": body.business_id, **f} for f, _ in chunk]).execute()
        supabase.table("inventory_items").insert(
            [{"product_id": p["id"], "business_id": body.business_id, "quantity": 0} for p in res.data]).execute()
        created_ids += [(p["id"], stock) for p, (_, stock) in zip(res.data, chunk)]

    for pid, fields, _ in to_update:
        supabase.table("products").update(fields).eq("id", pid).execute()

    for pid, stock in created_ids + [(pid, stock) for pid, _, stock in to_update]:
        if stock is not None:
            apply_movement(business_id=body.business_id, product_id=pid, type="adjustment",
                           quantity=stock, user_id=user_id, reason="Import")

    return {"created": len(to_create), "updated": len(to_update), "skipped": skipped}


@router.patch("/{product_id}")
def update_product(
    product_id: str,
    body: ProductUpdate,
    user_id: str = Depends(get_current_user),
):
    p = supabase.table("products").select("business_id") \
        .eq("id", product_id).maybe_single().execute()
    if not p or not p.data:
        raise HTTPException(404, "Not found")
    check_business_access(user_id, p.data["business_id"])
    fields = _with_supplier(p.data["business_id"], _clean(body.model_dump(exclude_unset=True)))
    if not fields:
        raise HTTPException(400, "No fields to update")
    res = supabase.table("products").update(fields).eq("id", product_id).execute()
    return res.data[0]


@router.delete("/{product_id}")
def delete_product(product_id: str, user_id: str = Depends(get_current_user)):
    p = supabase.table("products").select("business_id") \
        .eq("id", product_id).maybe_single().execute()
    if not p or not p.data:
        raise HTTPException(404, "Not found")
    check_business_access(user_id, p.data["business_id"])
    supabase.table("products").delete().eq("id", product_id).execute()
    return {"ok": True}
