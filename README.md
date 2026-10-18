# WMS

Warehouse management for small businesses: stock, purchase and sale orders, forecast-based
reorder planning, customer analytics, e-shop sync and AI helpers. Greek and English.

**Live:** https://wms.task-code.com

---

## Features

**Warehouse**
- Products with SKU, barcode, supplier, lead time, prices; bulk **import from CSV/Excel**
- Stock levels and movement log; **lots and expiry dates** (stock leaves earliest-expiring first)
- Purchase and sale orders; completing an order moves stock
- **Barcode scanning** with the phone camera or a USB scanner
- **Stock-take**: count by scanning, apply only the differences

**Suppliers & purchasing**
- Suppliers with contacts, lead time, minimum order; products with minimum quantity and pack size
- Purchase orders as **PDF**, **emailed to the supplier** from the app (replies go to you)

**Sales from your invoicing software**
- **Elorus**: issued documents are pulled every 15 minutes and take stock out (matched by product code)
- **Any other program** (Epsilon, SoftOne, Prisma, Oxygen…): import a sales export (Excel/CSV);
  each document is imported once; past sales can be recorded for forecasts without touching stock

**Planning & insights**
- Per-product **demand forecast** from the app's own sales (weekday pattern, safety stock)
- **Reorder suggestions** with quantity and order-by date → draft purchase orders per supplier
- **Unusual activity**: sudden sales drops/spikes, stock lost in recounts, revenue drop
- Customer analysis (RFM segments) and CSV-based sales forecast (Random Forest)
- **Daily alert emails** to owners/admins
- **Reports**: stock value at cost, ABC analysis, dead stock (no sales in 90 days), margins; CSV export

**AI (Claude API, optional)**
- **Scan an invoice / delivery note** (photo or PDF) → lines matched to products → purchase order
- **Assistant**: ask questions about sales, customers and stock in plain language
- **Message drafts** for customers who stopped buying

**Team & integrations**
- Roles: owner / admin / member, invites by email, switch between businesses
- **WooCommerce and Shopify**: paid orders take stock out automatically (by SKU)

**Getting started & mobile**
- First-run guide (products → suppliers → first order) and **demo data in a separate business**
- **Installable app (PWA)**; stock-take works **without signal** and syncs when back online

**Account & compliance**
- Email/password auth with confirmation and password reset (Supabase Auth, httpOnly cookies)
- Privacy policy and terms (el/en), data export, account deletion, self-hosted fonts
- Nightly database + file backups

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3, TypeScript, Vite, Pinia, vue-i18n |
| Backend | FastAPI (Python 3.12) |
| Database / auth / files | Supabase (PostgreSQL, Auth, Storage) |
| AI | Anthropic Claude API (`claude-opus-5-5`) |
| Forecasting | statistical model in `services/forecasting.py`; scikit-learn Random Forest for CSV forecasts |
| Hosting | Hetzner VPS, Traefik v3, systemd |

---

## Quick start (local)

Requirements: Python 3.12, Node 20+, a Supabase project.

```bash
cp wms/backend/.env.example wms/backend/.env   # fill in SUPABASE_URL / SUPABASE_KEY at least
./run-local.sh                                 # backend :8000 + frontend :5173, Ctrl+C stops both
```

`run-local.sh` creates `wms/backend/venv`, installs Python and npm packages when they change,
and writes `frontend/ui/.env.local`. Other modes:

```bash
./run-local.sh --test      # backend tests + frontend type-check
./run-local.sh --migrate   # apply pending database migrations, then start
```

> Local and production use the same Supabase project unless your `.env` points elsewhere.

Demo data for testing or recording a video: see [TESTING.md](TESTING.md).

---

## Deploying

```bash
./deploy.sh                # tests + build locally → push → update the server → health check
./deploy.sh --skip-checks
```

On the server it pulls, installs dependencies, **applies database migrations**, builds the
frontend, installs the systemd units in `wms/deploy/systemd/` and restarts the backend.
It refuses to start (and changes nothing) if migrations can't run.

Override the target with `DEPLOY_HOST` / `DEPLOY_DIR`, or a git-ignored `.deploy.env`:

```bash
DEPLOY_HOST=root@188.245.64.189
DEPLOY_DIR=/var/www/wms
```

### One-time server setup

1. **Postgres client** (for migrations and backups) — `pg_dump` must be at least the Supabase
   Postgres major version (Supabase → Settings → Infrastructure):
   ```bash
   apt install -y postgresql-common && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
   apt install -y postgresql-client-17
   ```
2. **`wms/backend/.env`** on the server — see [`.env.example`](wms/backend/.env.example):
   `DATABASE_URL`, `FRONTEND_URL=https://wms.task-code.com`, `COOKIE_SECURE=true`,
   `SMTP_*`, `ANTHROPIC_API_KEY`, `SENTRY_DSN`. For browser errors too, put `VITE_SENTRY_DSN`
   in `wms/frontend/ui/.env.production.local` (see `.env.production.example`).
3. **Supabase dashboard**
   - Authentication → URL Configuration: Site URL `https://wms.task-code.com`; Redirect URLs
     `https://wms.task-code.com/login` and `https://wms.task-code.com/reset-password`
     (plus the `http://localhost:5173/...` equivalents for development).
   - Authentication → Emails → SMTP Settings: your SMTP provider (e.g. Resend). The built-in
     sender only delivers to your own team and is rate-limited.
4. **Legal details** — fill in `wms/frontend/ui/src/config/site.ts` (legal name, VAT number,
   address, contact email) and have the texts in `src/legal/documents.ts` reviewed.
5. **Monitoring** — create a free [sentry.io](https://sentry.io) account with two projects
   (FastAPI and Vue) for the DSNs above. Uptime: `.github/workflows/uptime.yml` checks the site
   every 10 minutes from GitHub; failures email you (GitHub → Settings → Notifications → Actions).
6. Run `./deploy.sh`.

### What runs on the server

| Unit | What |
|---|---|
| `wms-backend.service` | uvicorn on port 8001 (API + built frontend) |
| `wms-alerts.timer` | 07:30 Athens — daily alert emails (`scripts/send_alerts.py`) |
| `wms-backup.timer` | 03:15 Athens — `scripts/backup_db.sh` → `/var/backups/wms`, 14 days kept |
| `wms-invoicing.timer` | every 15 min — pull new documents from Elorus (`scripts/sync_invoicing.py`) |

```bash
systemctl status wms-backend
journalctl -u wms-backend -n 50
systemctl list-timers 'wms-*'
```

Restore a backup into a fresh project: `pg_restore --no-owner --dbname "$DATABASE_URL" db-<stamp>.dump`,
then extract `storage-<stamp>.tar.gz` and upload the files back to the `datasets` bucket.

### Infrastructure

```
Browser → wms.task-code.com:443 → Traefik (Docker) → 172.18.0.1:8001 → uvicorn (systemd)
                                                         ├── /api/...  FastAPI
                                                         └── /         Vue build (dist/)
```

Traefik — `/opt/taskcode/traefik-conf/wms.yml`:

```yaml
http:
  routers:
    wms:
      rule: "Host(`wms.task-code.com`)"
      entrypoints: [websecure]
      service: wms-svc
      tls: { certresolver: le }
  services:
    wms-svc:
      loadBalancer:
        servers:
          - url: "http://172.18.0.1:8001"
```

Firewall: `ufw allow from 172.18.0.0/16 to any port 8001`. DNS (Cloudflare): A record
`wms` → `188.245.64.189`, DNS only.

---

## Invoicing software

**Elorus** — Settings → Integrations → Elorus: API key (Elorus → User profile) and organization ID.
Only documents issued after connecting reduce stock; optionally the last 90 days are imported for
forecasts without changing stock. Product codes in Elorus must match WMS SKUs (or barcodes).
Not handled yet: credit notes (returns) and documents voided after import.

**Other programs** — Orders → Import sales: an Excel/CSV export with one row per document line
(document no., date, customer, product code, quantity, price). Re-uploading the same file is safe.

## E-shop integrations

Settings → Integrations shows a webhook URL per shop.

- **WooCommerce** → Settings → Advanced → Webhooks → Add: topic *Order updated*, the URL and the
  secret shown in WMS. Orders in *processing / completed / on-hold* take stock out.
- **Shopify** → Settings → Notifications → Webhooks → Create: *Order payment*, JSON. Paste
  Shopify's signing secret into WMS.

Line items are matched by SKU; unknown SKUs are skipped and listed on the created order.
Each shop order is processed once even if the webhook is retried.

---

## Project structure

```
run-local.sh · deploy.sh · TESTING.md
wms/
├── backend/
│   ├── main.py                    FastAPI app, routers, serves frontend/ui/dist
│   ├── api/routes/                auth, user, business (team), products, inventory, orders,
│   │                              customers, datasets, predictions, alerts, integrations, ai
│   ├── services/                  stock (every stock change), forecasting, permissions,
│   │                              mailer, alerts, ai
│   ├── migrations/                SQL, applied by scripts/migrate.sh
│   ├── scripts/                   migrate.sh, backup_db.sh, send_alerts.py, seed_demo.py
│   └── tests/                     pytest (no network; fake Supabase)
├── frontend/ui/src/
│   ├── views/                     pages (Landing, Auth, Dashboard, wms/*, Assistant, legal)
│   ├── components/                ui/BaseModal, BarcodeScanner, settings/*, products/* …
│   ├── i18n/                      el.json, en.json
│   └── config/site.ts             legal details shown on /privacy and /terms
├── deploy/systemd/                backend, alerts and backup units
└── testdata/                      CSV files for the sales forecast
```

---

## API overview

Every endpoint needs the `access_token` cookie except auth and the e-shop webhook.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register · login · logout · forgot-password · reset-password`, `GET /api/auth/me` |
| Account | `PATCH /api/user`, `/user/email`, `/user/password`, `GET /api/user/export`, `DELETE /api/user` |
| Team | `GET/POST /api/businesses/{id}/members`, `PATCH/DELETE /api/businesses/{id}/members/{user}` |
| Products | `GET/POST /api/products`, `POST /api/products/import`, `GET /api/products/lookup`, `PATCH/DELETE /api/products/{id}` |
| Inventory | `GET /api/inventory`, `POST /api/inventory/movement`, `GET /api/inventory/movements · lots · anomalies`, `GET /api/inventory/reorder-suggestions`, `GET /api/inventory/forecast/{product}`, `POST /api/inventory/reorder/purchase-orders`, `POST /api/inventory/stocktake` |
| Orders | `GET/POST /api/orders`, `GET /api/orders/{id}`, `PATCH /api/orders/{id}/status`, `POST /api/orders/{id}/complete` |
| Suppliers | `GET/POST /api/suppliers`, `PATCH/DELETE /api/suppliers/{id}` |
| Purchasing | `GET /api/orders/{id}/pdf`, `POST /api/orders/{id}/send`, `POST /api/orders/import-sales` |
| Reports | `GET /api/reports?days=90` |
| Onboarding | `GET /api/onboarding`, `POST /api/onboarding/dismiss`, `POST /api/onboarding/demo` |
| Analytics | `GET /api/customers/analysis`, `/api/datasets…`, `/api/predictions…` |
| Alerts | `GET /api/alerts/preview`, `POST /api/alerts/test` |
| Integrations | `GET/POST /api/integrations`, `POST /api/integrations/elorus`, `POST /api/integrations/{id}/sync`, `PATCH/DELETE /api/integrations/{id}`, `POST /api/integrations/webhook/{id}` (HMAC) |
| AI | `GET /api/ai/status`, `POST /api/ai/scan-invoice · chat · draft-message` |
| Health | `GET /api/health` (`?deep=1` also checks the database) |

Interactive docs: http://localhost:8000/docs when running locally.
