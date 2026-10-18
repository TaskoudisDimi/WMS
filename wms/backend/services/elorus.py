"""
Elorus (elorus.gr) sync: issued sales documents → completed sales in WMS, matched by
product code (= WMS SKU) or barcode. API docs: https://developer.elorus.com/el/

Elorus has no webhooks, so we poll (scripts/sync_invoicing.py every 15 minutes, or
"Sync now" in Settings). Each document is imported once (orders.external_ref).
Not handled yet: credit notes (returns) and voiding a document after it was imported.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from db.supabase_client import supabase
from services.sales import product_index, record_sale
from services.secret_box import decrypt

log = logging.getLogger(__name__)
BASE = "https://api.elorus.com/v1.2"


class ElorusError(Exception):
    pass


class Elorus:
    def __init__(self, api_key: str, organization_id: str):
        self.http = httpx.Client(base_url=BASE, timeout=30, headers={
            "Authorization": f"Token {api_key}",
            "X-Elorus-Organization": str(organization_id),
            "Accept": "application/json",
        })

    def get(self, path: str, **params) -> dict:
        r = self.http.get(path, params=params)
        if r.status_code in (401, 403):
            raise ElorusError("Elorus rejected the API key or organization ID")
        if r.status_code >= 400:
            raise ElorusError(f"Elorus error {r.status_code}: {r.text[:200]}")
        return r.json()

    def paged(self, path: str, **params):
        page = 1
        while True:
            data = self.get(path, page=page, page_size=250, **params)
            yield from data.get("results", [])
            if not data.get("next"):
                return
            page += 1

    def check(self) -> None:
        self.get("/products/", page_size=1)

    def product_codes(self) -> dict[str, list[str]]:
        """Elorus product id → [code, barcodes…]"""
        out: dict[str, list[str]] = {}
        for p in self.paged("/products/"):
            keys = [p["code"]] if p.get("code") else []
            keys += [b.get("barcode") for b in p.get("barcodes") or [] if b.get("barcode")]
            out[str(p["id"])] = keys
        return out


def client_for(integration: dict) -> Elorus:
    key = decrypt(integration["secret"])
    if not key:
        raise ElorusError("Stored API key can't be read — re-enter it in Settings")
    return Elorus(key, integration["config"].get("organization_id"))


def sync(integration: dict, *, since: datetime | None = None, until: datetime | None = None,
         affect_stock: bool = True) -> dict:
    """Import documents created in [since, until). Defaults to everything since the last sync."""
    business_id = integration["business_id"]
    config = dict(integration.get("config") or {})
    started = datetime.now(timezone.utc)
    if since is None:
        since = datetime.fromisoformat(config.get("synced_until") or config["start_at"])
    since = since - timedelta(minutes=10)  # overlap: documents saved while the last sync ran

    stats = {"imported": 0, "already": 0, "unmatched_skus": set(), "documents": 0}
    try:
        api = client_for(integration)
        codes = api.product_codes()
        ours = product_index(business_id)
        params = {"created_after": since.isoformat(), "draft": 0, "is_void": 0, "ordering": "created"}
        if until:
            params["created_before"] = until.isoformat()
        for doc in api.paged("/invoices/", **params):
            stats["documents"] += 1
            detail = api.get(f"/invoices/{doc['id']}/")
            lines = []
            for item in detail.get("items") or []:
                keys = codes.get(str(item.get("product") or ""), [])
                match = next((ours[k.strip().lower()] for k in keys if k.strip().lower() in ours), None) or \
                        next((ours[k.strip()] for k in keys if k.strip() in ours), None)
                qty = int(round(float(item.get("quantity") or 0)))
                if not match:
                    if item.get("product"):
                        stats["unmatched_skus"].add(keys[0] if keys else item.get("title") or "?")
                    continue
                if qty > 0:
                    price = item.get("unit_value")
                    lines.append((match["id"], qty, float(price) if price not in (None, "") else None))
            if not lines:
                continue
            order = record_sale(
                business_id=business_id, external_ref=f"elorus:{doc['id']}",
                party=detail.get("client_display_name"), lines=lines,
                note=f"Elorus {detail.get('representation') or doc['id']}",
                at=f"{detail['date']}T12:00:00+00:00" if detail.get("date") else None,
                affect_stock=affect_stock,
            )
            stats["imported" if order else "already"] += 1
        if until is None:
            config["synced_until"] = started.isoformat()
        update = {"config": config, "last_sync_at": started.isoformat(), "last_error": None}
    except (ElorusError, httpx.HTTPError) as e:
        log.warning("Elorus sync failed for %s: %s", business_id, e)
        update = {"last_error": str(e)[:300], "last_sync_at": started.isoformat()}
        stats["error"] = str(e)
    supabase.table("integrations").update(update).eq("id", integration["id"]).execute()
    stats["unmatched_skus"] = sorted(stats["unmatched_skus"])[:50]
    return stats
