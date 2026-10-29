-- Applied and verified on NETRATTLER MAIN on 2026-10-29.
-- Keep primary keys; remove only verified equivalent secondary constraints/indexes.
set lock_timeout = '5s';
alter view public.player_avg_stats set (security_invoker = true);
alter function public.set_prop_hunter_updated_at() set search_path = pg_catalog, public, pg_temp;
alter function public.ph_touch_updated_at() set search_path = pg_catalog, public, pg_temp;
alter function public.netrattler_prune_player_history_l15() set search_path = pg_catalog, public, pg_temp;
-- These indexes exactly duplicate a retained primary key or equivalent index.
-- Constraint-backed indexes are deliberately retained.
drop index if exists public.uq_netrattler_builder_picks_builder_id;
drop index if exists public.netrattler_github_open_source_sources_repo_full_name_uidx;
drop index if exists public.ix_netrattler_group_stats_group_period;
drop index if exists public.uq_netrattler_group_stats_stat_id;
drop index if exists public.uq_netrattler_performance_stats_stat_id;
drop index if exists public.ix_netrattler_settlements_group_date;
drop index if exists public.ix_netrattler_settlements_status;
set lock_timeout = '5s';
alter table public.netrattler_builder_picks drop constraint if exists netrattler_builder_picks_builder_id_key;
alter table public.netrattler_settlements drop constraint if exists uq_netrattler_settlements_sid;
alter table public.netrattler_settlements drop constraint if exists uq_netrattler_settlements_source_tip;
