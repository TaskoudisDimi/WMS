from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user
from db.supabase_client import supabase
from services import demo
from services.permissions import check_business_access

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


def _count(table: str, business_id: str, **eq) -> int:
    q = supabase.table(table).select("id", count="exact").eq("business_id", business_id)
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.limit(1).execute().count or 0


@router.get("")
def status(business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    biz = supabase.table("businesses").select("onboarding_dismissed, is_demo").eq("id", business_id).single().execute().data
    return {
        "dismissed": biz["onboarding_dismissed"] or biz["is_demo"],
        "steps": {
            "products": _count("products", business_id) > 0,
            "suppliers": _count("suppliers", business_id) > 0,
            "orders": _count("orders", business_id) > 0,
            "team": _count("business_members", business_id) > 1,
            "sales_source": _count("integrations", business_id) > 0
                            or bool(supabase.table("orders").select("id").eq("business_id", business_id)
                                    .not_.is_("external_ref", "null").limit(1).execute().data),
        },
    }


class DismissRequest(BaseModel):
    business_id: str


@router.post("/dismiss")
def dismiss(body: DismissRequest, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, body.business_id, min_role="admin")
    supabase.table("businesses").update({"onboarding_dismissed": True}).eq("id", body.business_id).execute()
    return {"ok": True}


@router.post("/demo")
def create_demo(user_id: str = Depends(get_current_user)):
    """A separate demo business full of sample data, so real data stays clean.
    Reuses the user's existing demo business if there is one (re-seeded)."""
    owned = supabase.table("businesses").select("id").eq("owner_id", user_id).eq("is_demo", True).execute().data
    if owned:
        biz_id = owned[0]["id"]
        supabase.table("orders").delete().eq("business_id", biz_id).execute()
        supabase.table("products").delete().eq("business_id", biz_id).execute()
        supabase.table("suppliers").delete().eq("business_id", biz_id).execute()
    else:
        if len(supabase.table("businesses").select("id").eq("owner_id", user_id).execute().data or []) >= 10:
            raise HTTPException(400, "Too many businesses")
        biz_id = supabase.table("businesses").insert({
            "owner_id": user_id, "name": "Demo · Χονδρική Συσκευασίας", "industry": "demo", "is_demo": True,
            "alert_email_enabled": False,
        }).execute().data[0]["id"]
        supabase.table("business_members").insert({"business_id": biz_id, "user_id": user_id, "role": "owner"}).execute()
    stats = demo.seed(biz_id, user_id, sku_prefix="")
    return {"business_id": biz_id, **stats}
