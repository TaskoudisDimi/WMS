from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from core.security import get_current_user
from db.supabase_client import supabase
from services.permissions import check_business_access

router = APIRouter(prefix="/api/suppliers", tags=["Suppliers"])


class SupplierFields(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    contact_name: Optional[str] = Field(default=None, max_length=150)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=40)
    vat_number: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = Field(default=None, max_length=1000)
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=365)
    min_order_value: Optional[float] = Field(default=None, ge=0)


class SupplierCreate(SupplierFields):
    business_id: str


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    vat_number: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=365)
    min_order_value: Optional[float] = Field(default=None, ge=0)


def _owned(supplier_id: str, user_id: str) -> dict:
    row = supabase.table("suppliers").select("*").eq("id", supplier_id).maybe_single().execute()
    if not row or not row.data:
        raise HTTPException(404, "Supplier not found")
    check_business_access(user_id, row.data["business_id"])
    return row.data


def _clean(d: dict) -> dict:
    return {k: (v.strip() or None) if isinstance(v, str) and k != "name" else (v.strip() if isinstance(v, str) else v)
            for k, v in d.items()}


@router.get("")
def list_suppliers(business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    rows = supabase.table("suppliers").select("*").eq("business_id", business_id).order("name").execute().data or []
    counts: dict[str, int] = {}
    for p in supabase.table("products").select("supplier_id").eq("business_id", business_id).execute().data or []:
        if p.get("supplier_id"):
            counts[p["supplier_id"]] = counts.get(p["supplier_id"], 0) + 1
    return [{**r, "product_count": counts.get(r["id"], 0)} for r in rows]


@router.post("")
def create_supplier(body: SupplierCreate, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, body.business_id)
    try:
        return supabase.table("suppliers").insert(
            {"business_id": body.business_id, **_clean(body.model_dump(exclude={"business_id"}))}).execute().data[0]
    except Exception:
        raise HTTPException(409, "A supplier with this name already exists")


@router.patch("/{supplier_id}")
def update_supplier(supplier_id: str, body: SupplierUpdate, user_id: str = Depends(get_current_user)):
    current = _owned(supplier_id, user_id)
    fields = _clean(body.model_dump(exclude_unset=True))
    if not fields:
        raise HTTPException(400, "No fields to update")
    row = supabase.table("suppliers").update(fields).eq("id", supplier_id).execute().data[0]
    if "name" in fields and fields["name"] != current["name"]:
        # keep the denormalised name on products in sync
        supabase.table("products").update({"supplier": fields["name"]}).eq("supplier_id", supplier_id).execute()
    return row


@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: str, user_id: str = Depends(get_current_user)):
    _owned(supplier_id, user_id)
    supabase.table("products").update({"supplier": None}).eq("supplier_id", supplier_id).execute()
    supabase.table("suppliers").delete().eq("id", supplier_id).execute()
    return {"ok": True}
