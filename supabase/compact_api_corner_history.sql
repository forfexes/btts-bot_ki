create table if not exists public.netrattler_api_corner_history (
 fixture_id bigint primary key,
 league_id integer not null,
 match_date date not null,
 home_team text not null,
 away_team text not null,
 home_corners smallint not null check(home_corners between 0 and 30),
 away_corners smallint not null check(away_corners between 0 and 30),
 home_goals smallint not null check(home_goals >= 0),
 away_goals smallint not null check(away_goals >= 0)
);
create index if not exists api_corner_league_date on public.netrattler_api_corner_history(league_id,match_date desc);
alter table public.netrattler_api_corner_history enable row level security;
revoke all on public.netrattler_api_corner_history from public, anon, authenticated;
grant select, insert, update, delete on public.netrattler_api_corner_history to service_role;
create trigger netrattler_bulk_capacity_guard before insert on public.netrattler_api_corner_history
for each statement execute function public.netrattler_bulk_capacity_guard();
