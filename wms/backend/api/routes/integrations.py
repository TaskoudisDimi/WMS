"""
E-shop integrations: WooCommerce and Shopify send an "order" webhook, we match line
items to products by SKU, create a completed sale order and take the stock out.

Setup (shown in Settings → Integrations):
  WooCommerce → Settings → Advanced → Webhooks → Add: topic "Order updated",
               delivery URL = webhook_url, secret = the secret shown here.
  Shopify     → Settings → Notifications → Webhooks → Create: event "Order payment",
               format JSON, URL = webhook_url; paste Shopify's signing secret here.
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.config import FRONTEND_URL
from core.security import get_current_user
from db.supabase_client import supabase
from services.permissions import check_business_access
from services.stock import apply_movement
from services import elorus
from services.secret_box import encrypt

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])
log = logging.getLogger(__name__)

# WooCommerce statuses that mean "stock has left" (on-hold = awaiting bank transfer)
WOO_PROCESS_STATUSES = {"processing", "completed", "on-hold"}


def _public(row: dict) -> dict:
    if row["provider"] == "elorus":
        # never send the (encrypted) API key back to the browser
        return {**{k: v for k, v in row.items() if k != "secret"}, "webhook_url": None}
    return {**row, "webhook_url": f"{FRONTEND_URL}/api/integrations/webhook/{row['id']}"}


def _owned(integration_id: str, user_id: str) -> dict:
    row = supabase.table("integrations").select("*").eq("id", integration_id).maybe_single().execute()
    if not row or not row.data:
        raise HTTPException(404, "Integration not found")
    check_business_access(user_id, row.data["business_id"], min_role="admin")
    return row.data


class ElorusConnect(BaseModel):
    business_id: str
    api_key: str = Field(min_length=10, max_length=200)
    organization_id: str = Field(min_length=1, max_length=40)
    # Import the last N days for forecasts only (stock untouched: it already reflects them)
    history_days: int = Field(default=0, ge=0, le=365)


class IntegrationCreate(BaseModel):
    business_id: str
    provider: Literal["woocommerce", "shopify"]
    secret: Optional[str] = Field(default=None, min_length=8, max_length=200)


class IntegrationUpdate(BaseModel):
    enabled: Optional[bool] = None
    secret: Optional[str] = Field(default=None, min_length=8, max_length=200)
    regenerate_secret: bool = False


@router.get("")
def list_integrations(business_id: str, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id, min_role="admin")
    rows = supabase.table("integrations").select("*").eq("business_id", business_id).execute().data or []
    return [_public(r) for r in rows]


@router.post("")
def create_integration(body: IntegrationCreate, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, body.business_id, min_role="admin")
    try:
        row = supabase.table("integrations").insert({
            "business_id": body.business_id, "provider": body.provider,
            "secret": body.secret or secrets.token_urlsafe(32),
        }).execute().data[0]
    except Exception:
        raise HTTPException(409, "This integration already exists")
    return _public(row)


@router.post("/elorus")
def connect_elorus(body: ElorusConnect, background: BackgroundTasks, user_id: str = Depends(get_current_user)):
    check_business_access(user_id, body.business_id, min_role="admin")
    try:
        elorus.Elorus(body.api_key.strip(), body.organization_id.strip()).check()
    except (elorus.ElorusError, Exception) as e:
        raise HTTPException(400, f"Could not connect to Elorus: {e}")

    now = datetime.now(timezone.utc)
    fields = {"secret": encrypt(body.api_key.strip()), "enabled": True, "last_error": None,
              # Only documents issued from now on reduce stock
              "config": {"organization_id": body.organization_id.strip(), "start_at": now.isoformat()}}
    existing = supabase.table("integrations").select("id").eq("business_id", body.business_id) \
        .eq("provider", "elorus").maybe_single().execute()
    if existing and existing.data:
        row = supabase.table("integrations").update(fields).eq("id", existing.data["id"]).execute().data[0]
    else:
        row = supabase.table("integrations").insert(
            {"business_id": body.business_id, "provider": "elorus", **fields}).execute().data[0]

    if body.history_days:
        background.add_task(elorus.sync, row, since=now - timedelta(days=body.history_days), until=now,
                            affect_stock=False)
    return _public(row)


@router.post("/{integration_id}/sync")
def sync_now(integration_id: str, user_id: str = Depends(get_current_user)):
    row = _owned(integration_id, user_id)
    if row["provider"] != "elorus":
        raise HTTPException(400, "This integration syncs automatically via webhooks")
    if not row["enabled"]:
        raise HTTPException(400, "Integration is paused")
    return elorus.sync(row)


@router.patch("/{integration_id}")
def update_integration(integration_id: str, body: IntegrationUpdate, user_id: str = Depends(get_current_user)):
    _owned(integration_id, user_id)
    fields: dict = {}
    if body.enabled is not None:
        fields["enabled"] = body.enabled
    if body.secret:
        fields["secret"] = body.secret
    if body.regenerate_secret:
        fields["secret"] = secrets.token_urlsafe(32)
    if not fields:
        raise HTTPException(400, "No fields to update")
    row = supabase.table("integrations").update(fields).eq("id", integration_id).execute().data[0]
    return _public(row)


@router.delete("/{integration_id}")
def delete_integration(integration_id: str, user_id: str = Depends(get_current_user)):
    _owned(integration_id, user_id)
    supabase.table("integrations").delete().eq("id", integration_id).execute()
    return {"ok": True}


# ── Webhook receiver (public, authenticated by HMAC signature) ────────────────

def _valid_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, signature.strip())


def _parse_order(provider: str, payload: dict) -> tuple[str, str | None, list[dict]] | None:
    """Return (external_id, customer_name, [{sku, quantity, price}]) or None to ignore."""
    if provider == "woocommerce":
        if payload.get("status") not in WOO_PROCESS_STATUSES:
            return None
        billing = payload.get("billing") or {}
        name = billing.get("company") or " ".join(
            x for x in (billing.get("first_name"), billing.get("last_name")) if x) or None
        lines = [{"sku": li.get("sku"), "quantity": li.get("quantity"), "price": li.get("price")}
                 for li in payload.get("line_items") or []]
        return str(payload.get("id")), name, lines

    customer = payload.get("customer") or {}
    address = payload.get("billing_address") or {}
    name = address.get("company") or address.get("name") or " ".join(
        x for x in (customer.get("first_name"), customer.get("last_name")) if x) or None
    lines = [{"sku": li.get("sku"), "quantity": li.get("quantity"), "price": li.get("price")}
             for li in payload.get("line_items") or []]
    return str(payload.get("id")), name, lines


@router.post("/webhook/{integration_id}", include_in_schema=False)
async def receive_webhook(integration_id: str, request: Request):
    body = await request.body()
    row = supabase.table("integrations").select("*").eq("id", integration_id).maybe_single().execute()
    if not row or not row.data:
        raise HTTPException(404, "Unknown webhook")
    integration = row.data
    provider = integration["provider"]

    # WooCommerce pings the URL (form-encoded "webhook_id=…") when the webhook is created
    if provider == "woocommerce" and not request.headers.get("x-wc-webhook-topic"):
        return {"ok": True}

    signature = request.headers.get("x-wc-webhook-signature" if provider == "woocommerce" else "x-shopify-hmac-sha256")
    if not _valid_signature(integration["secret"], body, signature):
        raise HTTPException(401, "Invalid signature")
    if not integration["enabled"]:
        return {"ok": True, "ignored": "disabled"}

    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Body is not JSON")
    parsed = _parse_order(provider, payload)
    if not parsed:
        return {"ok": True, "ignored": "status"}
    external_id, customer, lines = parsed

    # Idempotency: claim the external order id first; a retry hits the unique constraint
    try:
        event = supabase.table("integration_events").insert({
            "integration_id": integration_id, "external_id": external_id,
        }).execute().data[0]
    except Exception:
        return {"ok": True, "ignored": "duplicate"}

    business_id = integration["business_id"]
    skus = [l["sku"] for l in lines if l.get("sku")]
    products = {p["sku"].lower(): p for p in (supabase.table("products").select("id, sku")
                .eq("business_id", business_id).in_("sku", skus).execute().data or [])} if skus else {}
    matched = [(products[l["sku"].lower()], int(l["quantity"] or 0), l.get("price"))
               for l in lines if l.get("sku") and l["sku"].lower() in products and int(l["quantity"] or 0) > 0]
    unmatched = [l.get("sku") or "?" for l in lines if not (l.get("sku") and l["sku"].lower() in products)]

    if not matched:
        log.warning("webhook %s order %s: no SKUs matched (%s)", integration_id, external_id, unmatched)
        return {"ok": True, "matched": 0, "unmatched": unmatched}

    label = "WooCommerce" if provider == "woocommerce" else "Shopify"
    note = f"{label} #{external_id}" + (f" · unmatched SKUs: {', '.join(unmatched)}" if unmatched else "")
    order = supabase.table("orders").insert({
        "business_id": business_id, "type": "sale", "status": "completed",
        "party_name": customer or label, "notes": note,
    }).execute().data[0]
    supabase.table("order_items").insert([{
        "order_id": order["id"], "product_id": p["id"], "quantity": q,
        "unit_price": float(price) if price not in (None, "") else None,
    } for p, q, price in matched]).execute()
    for p, q, _ in matched:
        apply_movement(business_id=business_id, product_id=p["id"], type="outbound", quantity=q,
                       user_id=None, reason=f"{label} #{external_id}", order_id=order["id"])

    supabase.table("integration_events").update({"order_id": order["id"]}).eq("id", event["id"]).execute()
    supabase.table("integrations").update({"last_event_at": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", integration_id).execute()
    return {"ok": True, "order_id": order["id"], "matched": len(matched), "unmatched": unmatched}
