-- Aristotle v4.0 — Supabase schema
-- Run this once in the Supabase SQL editor for your Aristotle project.
-- Stores each reconciliation snapshot. Read by the Vercel dashboard.

create table if not exists public.snapshots (
  id               bigserial primary key,
  created_at       timestamptz not null default now(),
  as_of            text,
  combined_net_liq numeric,
  deployed_pct     numeric,
  cash_reserve_pct numeric,
  fail_count       int default 0,
  warn_count       int default 0,
  action_count     int default 0,
  payload          jsonb not null       -- full reconcile.py output
);

create index if not exists snapshots_created_at_idx
  on public.snapshots (created_at desc);

-- Lock it down. This is private financial data.
-- RLS ON + no policies = only the service_role key (server-side) can read/write.
-- The local Python pusher and the Vercel server component both use the service
-- role key; the public anon key can see NOTHING.
alter table public.snapshots enable row level security;

-- (Intentionally no policies for anon/authenticated. Do not add a public SELECT
--  policy unless you also add real auth to the dashboard.)
