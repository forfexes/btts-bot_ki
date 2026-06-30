-- NETRATTLER BEST DATABASE SIMPLE — NETRATTLER PREFIX TABLES
-- Alle neuen Tabellen starten mit netrattler_.
-- Einmal in Supabase SQL Editor ausführen.

create table if not exists public.netrattler_source_health (
 source text primary key,
 status text,
 http_status integer,
 rows integer default 0,
 latency_ms integer,
 message text,
 checked_at timestamptz default now()
);

create table if not exists public.netrattler_source_registry (
 source text primary key,
 category text,
 source_type text,
 url text,
 is_free boolean default true,
 requires_key boolean default false,
 priority integer default 50,
 base_trust numeric default 50,
 notes text,
 updated_at timestamptz default now()
);

create table if not exists public.netrattler_source_trust_scores (
 source text not null,
 score_date date not null default current_date,
 trust_score numeric default 50,
 health_score numeric default 50,
 coverage_score numeric default 50,
 clv_score numeric default 50,
 roi_score numeric default 50,
 freshness_score numeric default 50,
 penalty_score numeric default 0,
 samples integer default 0,
 reason text,
 updated_at timestamptz default now(),
 primary key(source, score_date)
);

create table if not exists public.netrattler_news_signals (
 signal_id text primary key,
 source text not null,
 title text,
 url text,
 published_at timestamptz,
 team_name text,
 player_name text,
 signal_type text,
 sentiment numeric default 0,
 confidence numeric default 50,
 keywords text[],
 raw jsonb,
 created_at timestamptz default now()
);

create table if not exists public.netrattler_social_signals (
 signal_id text primary key,
 platform text not null,
 source text,
 url text,
 posted_at timestamptz,
 team_name text,
 player_name text,
 signal_type text,
 text text,
 engagement numeric default 0,
 confidence numeric default 50,
 raw jsonb,
 created_at timestamptz default now()
);

create table if not exists public.netrattler_github_open_source_sources (
 repo_full_name text primary key,
 url text,
 category text,
 description text,
 stars integer default 0,
 forks integer default 0,
 last_pushed_at timestamptz,
 license text,
 trust_score numeric default 50,
 tags text[],
 raw jsonb,
 updated_at timestamptz default now()
);

create table if not exists public.netrattler_source_coverage_report (
 table_name text primary key,
 row_count bigint default 0,
 status text,
 checked_at timestamptz default now(),
 message text
);

create table if not exists public.netrattler_best_database_status (
 component text primary key,
 status text,
 row_count bigint default 0,
 message text,
 checked_at timestamptz default now()
);

create table if not exists public.netrattler_learning_state (
 scope text not null,
 key text not null,
 value jsonb not null default '{}'::jsonb,
 score numeric,
 samples integer default 0,
 updated_at timestamptz default now(),
 primary key(scope,key)
);

create table if not exists public.netrattler_clv_tracking (
 tip_id text not null,
 source text default '',
 market text default '',
 selection text default '',
 open_odds numeric,
 close_odds numeric,
 clv_percent numeric,
 clv_direction text,
 match_id text,
 checked_at timestamptz default now(),
 raw jsonb,
 primary key(tip_id, checked_at)
);

create table if not exists public.netrattler_source_roi_metrics (
 source text not null,
 market text not null default '',
 period text not null default 'all_available',
 bets integer default 0,
 wins integer default 0,
 losses integer default 0,
 pushes integer default 0,
 stake numeric default 0,
 profit numeric default 0,
 roi numeric default 0,
 hit_rate numeric default 0,
 avg_odds numeric,
 avg_clv numeric,
 updated_at timestamptz default now(),
 primary key(source,market,period)
);

alter table public.netrattler_source_health disable row level security;
alter table public.netrattler_source_registry disable row level security;
alter table public.netrattler_source_trust_scores disable row level security;
alter table public.netrattler_news_signals disable row level security;
alter table public.netrattler_social_signals disable row level security;
alter table public.netrattler_github_open_source_sources disable row level security;
alter table public.netrattler_source_coverage_report disable row level security;
alter table public.netrattler_best_database_status disable row level security;
alter table public.netrattler_learning_state disable row level security;
alter table public.netrattler_clv_tracking disable row level security;
alter table public.netrattler_source_roi_metrics disable row level security;

notify pgrst, 'reload schema';

select 'NETRATTLER prefix tables ready' as status;
