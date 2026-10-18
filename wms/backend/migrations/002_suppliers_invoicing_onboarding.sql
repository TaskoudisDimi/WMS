-- 002: suppliers as records, order quantities, invoicing-software sync,
-- onboarding and demo businesses. Idempotent.

-- ── Suppliers ───────────────────────────────────────────────────────────────
create table if not exists suppliers (
  id              uuid primary key default gen_random_uuid(),
  business_id     uuid not null references businesses(id) on delete cascade,
  name            text not null,
  contact_name    text,
  email           text,
  phone           text,
  vat_number      text,
  address         text,
  notes           text,
  lead_time_days  integer check (lead_time_days is null or lead_time_days > 0),
  min_order_value numeric(12,2),
  created_at      timestamptz not null default now()
);
create unique index if not exists suppliers_business_name_idx on suppliers (business_id, lower(name));

alter table products add column if not exists supplier_id    uuid references suppliers(id) on delete set null;
alter table products add column if not exists min_order_qty  integer not null default 0 check (min_order_qty >= 0);
alter table products add column if not exists order_multiple integer not null default 1 check (order_multiple >= 1);

-- Turn the free-text supplier names from 001 into supplier records
insert into suppliers (business_id, name)
select distinct on (business_id, lower(trim(supplier))) business_id, trim(supplier)
  from products
 where supplier is not null and trim(supplier) <> ''
on conflict do nothing;

update products p
   set supplier_id = s.id
  from suppliers s
 where p.supplier_id is null
   and s.business_id = p.business_id
   and lower(s.name) = lower(trim(p.supplier));

-- ── Orders ──────────────────────────────────────────────────────────────────
alter table orders add column if not exists supplier_id  uuid references suppliers(id) on delete set null;
alter table orders add column if not exists sent_at      timestamptz;
-- Document id in another system (e.g. "elorus:123", "file:ΤΔΑ-0042"), so imports never double-count
alter table orders add column if not exists external_ref text;
create unique index if not exists orders_business_external_ref_idx
  on orders (business_id, external_ref) where external_ref is not null;

-- ── Invoicing software (Elorus) ─────────────────────────────────────────────
alter table integrations drop constraint if exists integrations_provider_check;
alter table integrations add constraint integrations_provider_check
  check (provider in ('woocommerce', 'shopify', 'elorus'));
alter table integrations add column if not exists config       jsonb not null default '{}'::jsonb;
alter table integrations add column if not exists last_sync_at timestamptz;
alter table integrations add column if not exists last_error   text;

-- ── Onboarding & demo ───────────────────────────────────────────────────────
alter table businesses add column if not exists is_demo              boolean not null default false;
alter table businesses add column if not exists onboarding_dismissed boolean not null default false;
