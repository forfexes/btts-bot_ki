-- Applied to MAIN and V4 on 2026-10-29. No historical data removed.
-- The function is identical; trigger table lists are project specific.
create or replace function public.netrattler_bulk_capacity_guard()
returns trigger language plpgsql security invoker
set search_path = pg_catalog
as $$
begin
  if pg_catalog.pg_database_size(pg_catalog.current_database()) >= 440::bigint * 1024 * 1024 then
    raise exception using errcode = '53100',
      message = 'NETRATTLER bulk collection paused at 440 MiB; preserve reserve for tips and settlement';
  end if;
  return null;
end;
$$;
revoke all on function public.netrattler_bulk_capacity_guard() from public, anon, authenticated;
grant execute on function public.netrattler_bulk_capacity_guard() to service_role;
drop trigger if exists netrattler_bulk_capacity_guard on public.odds_history;
create trigger netrattler_bulk_capacity_guard before insert on public.odds_history for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.x1_player_snapshots;
create trigger netrattler_bulk_capacity_guard before insert on public.x1_player_snapshots for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.player_game_log;
create trigger netrattler_bulk_capacity_guard before insert on public.player_game_log for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.fplci_player_match;
create trigger netrattler_bulk_capacity_guard before insert on public.fplci_player_match for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.apif_player_match;
create trigger netrattler_bulk_capacity_guard before insert on public.apif_player_match for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.player_match_stats;
create trigger netrattler_bulk_capacity_guard before insert on public.player_match_stats for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.netrattler_match_history;
create trigger netrattler_bulk_capacity_guard before insert on public.netrattler_match_history for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.netrattler_data_lake_raw;
create trigger netrattler_bulk_capacity_guard before insert on public.netrattler_data_lake_raw for each statement execute function public.netrattler_bulk_capacity_guard();
-- V4 uses the same function, with triggers on:
-- odds_history, odds_history_archive, x1_player_snapshots.
