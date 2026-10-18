"""Pull new sales documents from connected invoicing software (Elorus) for every
business. Run every 15 minutes by wms-invoicing.timer:

    cd wms/backend && venv/bin/python scripts/sync_invoicing.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.supabase_client import supabase  # noqa: E402
from services import elorus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("invoicing")

rows = supabase.table("integrations").select("*").eq("provider", "elorus").eq("enabled", True).execute().data or []
for row in rows:
    stats = elorus.sync(row)
    log.info("business %s: %s", row["business_id"], stats)
