-- SentinelSIF database schema — the six tables from PRD.md § Database schema (Supabase/Postgres).
-- Paste into the Supabase SQL Editor. Column names and types are exactly as specified in PRD.md;
-- nothing added, renamed, or retyped. Row Level Security is deliberately NOT enabled here — Day 1
-- Block 7 owns auth and RLS.
--
-- Table creation order is dependency order, not PRD listing order: users must exist before
-- classifications (classifications.reviewed_by references it), and sites before both.

create table sites (
  id        uuid primary key default gen_random_uuid(),
  name      text,
  region    text,
  latitude  float,
  longitude float
);

create table users (
  id      uuid primary key default gen_random_uuid(),
  name    text,
  role    text,  -- 'hse_manager' | 'site_supervisor' | 'admin'
  site_id uuid references sites (id)
);

create table reports (
  id                uuid primary key default gen_random_uuid(),
  site_id           uuid references sites (id),
  raw_text          text,
  cleaned_text      text,
  language_detected text,
  reporter_role     text,
  submitted_at      timestamptz,
  status            text  -- 'processed' | 'processing_failed' | 'needs_review'
);

create table classifications (
  id            uuid primary key default gen_random_uuid(),
  report_id     uuid references reports (id) on delete cascade,
  sif_potential boolean,
  confidence    float,
  model_version text,
  review_status text,  -- 'auto' | 'confirmed' | 'overridden'
  reviewed_by   uuid references users (id)
);

create table iogp_tags (
  id         uuid primary key default gen_random_uuid(),
  report_id  uuid references reports (id) on delete cascade,
  rule_name  text,
  confidence float
);

create table precursors (
  id          uuid primary key default gen_random_uuid(),
  report_id   uuid references reports (id) on delete cascade,
  entity_type text,  -- 'activity' | 'location' | 'equipment' | 'barrier_failure'
  entity_text text,
  span_start  int,
  span_end    int
);

-- Seed: 8 OIL operating areas. Every coordinate below was looked up in OpenStreetMap
-- (Nominatim) on 2026-08-24 and rounded to 5 decimal places; none are from memory.
-- Provenance per row is in the trailing comment: `place` = settlement record (town/village/
-- hamlet), `poi` = a named point inside the locality where OSM has no settlement record.
--
-- Three further OIL areas were considered and dropped because Nominatim returned no result
-- and inventing a coordinate is worse than a shorter seed: Dandewala, Bagitibba, Jorajan.

insert into sites (name, region, latitude, longitude) values
  ('Duliajan',    'Assam',     27.35591, 95.31923),  -- place: town, Dibrugarh district
  ('Naharkatiya', 'Assam',     27.28630, 95.32583),  -- place: town, Dibrugarh district
  ('Moran',       'Assam',     27.18574, 94.91043),  -- place: town, Dibrugarh district
  ('Baghjan',     'Assam',     27.60628, 95.40450),  -- place: hamlet (Baghjan Gaon), Tinsukia district
  ('Makum',       'Assam',     27.48454, 95.43813),  -- place: town, Tinsukia district
  ('Hapjan',      'Assam',     27.50013, 95.42785),  -- poi: Hapjan PHC, Tinsukia district — no settlement record in OSM
  ('Tanot',       'Rajasthan', 27.79601, 70.35316),  -- place: village, Jaisalmer district
  ('Ramgarh',     'Rajasthan', 27.37291, 70.49667);  -- place: village, Jaisalmer district
