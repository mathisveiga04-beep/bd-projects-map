-- Optional manual schema for Supabase SQL Editor.
-- The FastAPI backend can also create these tables automatically via SQLAlchemy.
create table if not exists projects (
  id bigserial primary key,
  owner_id text default '',
  owner_email text default '',
  title text not null,
  description text default '',
  country text default 'Cambodia',
  city text default '',
  address text default '',
  latitude double precision,
  longitude double precision,
  is_localized boolean default false,
  sector text default '',
  project_type text default 'Project',
  status text default 'identified',
  priority text default 'medium',
  color text default '#F59E0B',
  source text default 'Manual',
  source_url text default '',
  funder text default '',
  estimated_budget text default '',
  deadline text default '',
  reliability text default 'medium',
  confidence text default 'medium',
  opportunity_size text default 'unknown',
  scope_summary text default '',
  ai_summary text default '',
  ai_recommendation text default 'watch',
  contributor text default 'system',
  created_at timestamp default now(),
  updated_at timestamp default now()
);

alter table projects add column if not exists owner_id text default '';
alter table projects add column if not exists owner_email text default '';

create table if not exists tenders (
  id bigserial primary key,
  title text not null,
  country text default 'Cambodia',
  sector text default '',
  funder text default '',
  stage text default 'EOI',
  fit text default 'medium',
  estimated_budget text default '',
  deadline text default '',
  source_url text default '',
  summary text default '',
  ai_summary text default '',
  ai_recommendation text default 'watch',
  created_at timestamp default now(),
  updated_at timestamp default now()
);

create table if not exists scraper_runs (
  id bigserial primary key,
  source text default 'all',
  status text default 'started',
  items_found integer default 0,
  items_saved integer default 0,
  message text default '',
  started_at timestamp default now(),
  finished_at timestamp
);
