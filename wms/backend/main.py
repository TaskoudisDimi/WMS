import mimetypes
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routes import (auth, user, business, datasets, predictions, products, inventory, orders, customers,
                        alerts, integrations, ai, suppliers, reports, onboarding)
from core.monitoring import init_sentry

init_sentry()
from core.middleware import RefreshSessionMiddleware

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://wms.task-code.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RefreshSessionMiddleware)

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(business.router)
app.include_router(datasets.router)
app.include_router(predictions.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(orders.router)
app.include_router(customers.router)
app.include_router(alerts.router)
app.include_router(integrations.router)
app.include_router(ai.router)
app.include_router(suppliers.router)
app.include_router(reports.router)
app.include_router(onboarding.router)


@app.get("/api/health", include_in_schema=False)
def health(deep: bool = False):
    """Liveness for the uptime monitor; ?deep=1 also checks the database."""
    if deep:
        from db.supabase_client import supabase
        try:
            supabase.table("businesses").select("id").limit(1).execute()
        except Exception:
            raise HTTPException(503, "Database unreachable")
    return {"ok": True}


# ─── Frontend (production) ───────────────────────────────────────────────────
# Serves the built Vue app from frontend/ui/dist when it exists. Relative to this
# file, so it keeps working if the repo is moved; FRONTEND_DIST overrides it.
DIST_DIR = Path(os.getenv(
    "FRONTEND_DIST",
    Path(__file__).resolve().parent.parent / "frontend" / "ui" / "dist",
)).resolve()

mimetypes.add_type("application/manifest+json", ".webmanifest")

if DIST_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Unknown API routes should 404, not return the SPA
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        # Root-level files from public/ (favicon.svg, …); resolve() + the parent
        # check blocks ../ path traversal
        file = (DIST_DIR / full_path).resolve()
        if full_path and file.is_file() and DIST_DIR in file.parents:
            return FileResponse(file)
        # Everything else is a client-side route (/login, /reset-password, …)
        return FileResponse(DIST_DIR / "index.html")

# Dev: uvicorn main:app --reload
