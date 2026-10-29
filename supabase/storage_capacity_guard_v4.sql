-- Applied to NETRATTLER V4 on 2026-10-29.
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
drop trigger if exists netrattler_bulk_capacity_guard on public.odds_history_archive;
create trigger netrattler_bulk_capacity_guard before insert on public.odds_history_archive for each statement execute function public.netrattler_bulk_capacity_guard();
drop trigger if exists netrattler_bulk_capacity_guard on public.x1_player_snapshots;
create trigger netrattler_bulk_capacity_guard before insert on public.x1_player_snapshots for each statement execute function public.netrattler_bulk_capacity_guard();
