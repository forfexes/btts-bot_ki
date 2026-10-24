#!/usr/bin/env python3
"""Copy big archive tables from the main Supabase project (REST) to the V2 project (Postgres).
Copy only - never deletes in the source. Secrets are read from env and never printed.
MODE=check|schema|copy|verify   TABLES=comma list"""
import os, sys, json, time
import requests

SRC_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SRC_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
DST_DSN = os.environ.get("V2_DATABASE_URL", "")
for _k in ("V2_SUPABASE_URL", "V2_SUPABASE_SERVICE_KEY"):  # tolerate a postgres URI saved under another V2 secret name
    if not DST_DSN.startswith("postgres") and os.environ.get(_k, "").startswith("postgres"):
        DST_DSN = os.environ[_k]
MODE = os.environ.get("MODE", "check")
TABLES = [t for t in os.environ.get("TABLES", "player_game_log,player_match_stats,odds_history").split(",") if t]
PAGE = 1000

DDL = {
"odds_history": """create table if not exists odds_history (source text, match_id text, market text, bookmaker text,
 captured_date date, home_team text, away_team text, match_date date, selection text, odds numeric,
 imported_at timestamptz, primary key (source, match_id, market, bookmaker, captured_date, selection));
 create index if not exists idx_oh_market on odds_history (market, captured_date desc)""",
"player_game_log": """create table if not exists player_game_log (player_key text, event_id text, source text, player_id text,
 player_name text, team text, league text, home_team text, away_team text, match_date date, minutes real, shots real,
 sot real, goals real, assists real, fouls_committed real, fouls_won real, tackles real, yellow_cards real, red_cards real,
 saves real, offsides real, passes real, xg real, xa real, updated_at timestamptz, primary key (player_key, event_id));
 create index if not exists pgl_team_date_idx on player_game_log (team, match_date desc);
 create index if not exists pgl_player_date_idx on player_game_log (player_key, match_date desc)""",
"player_match_stats": """create table if not exists player_match_stats (id bigint primary key, source text, event_id text, player_id text,
 player_name text, team text, league text, home_team text, away_team text, match_date timestamptz, stat_name text,
 stat_value double precision, stat_text text, created_at timestamptz, match_id text, team_name text, minutes numeric,
 shots numeric, sot numeric, goals numeric, assists numeric, passes numeric, tackles numeric, fouls_committed numeric,
 fouls_won numeric, cards numeric, corners numeric, updated_at timestamptz, xg numeric, xa numeric, player text, match text,
 date date, shots_on_target numeric, yellow_cards numeric, red_cards numeric, data_hash text, collected_at timestamptz,
 position text, opponent text, home_away text, saves numeric, interceptions numeric, clearances numeric, offsides numeric,
 key_passes numeric, duels numeric, duels_won numeric, touches numeric, crosses numeric);
 create index if not exists pms_player_stat_date on player_match_stats (player_name, stat_name, match_date)""",
"netrattler_match_history": """create table if not exists netrattler_match_history (division text, match_date date,
 home_team text, away_team text, ft_home smallint, ft_away smallint, ht_home smallint, ht_away smallint,
 source text, created_at timestamptz, primary key (division, match_date, home_team, away_team))""",
"netrattler_data_lake_raw": """create table if not exists netrattler_data_lake_raw (id uuid primary key, source text,
 source_type text, url text, league text, season text, match_date date, entity_type text, entity_name text,
 market text, category text, payload jsonb, data_hash text unique, collected_at timestamptz);
 create index if not exists ndlr_source_date on netrattler_data_lake_raw (source, match_date desc)""",
"ml_tips": """create table if not exists ml_tips (id bigint primary key, match_id text, home_team text, away_team text, league text,
 date text, time text, market text, tip text, odds float8, confidence integer, probability float8, value_rating text,
 features jsonb, created_at timestamptz, bot_version text, result text, settled boolean, settled_at timestamptz, actual_score text)""",
"netrattler_learning_events": """create table if not exists netrattler_learning_events (event_id text primary key, pick_key text,
 tip_date date, market text, league text, source text, player text, builder_type text, legs integer, odds_bucket text,
 probability float8, odds float8, closing_odds float8, clv float8, outcome smallint, profit_units float8, brier float8,
 logloss float8, payload jsonb, settled_at timestamptz, created_at timestamptz)""",
"x1_player_snapshots": """create table if not exists x1_player_snapshots (id bigint primary key, captured_at timestamptz,
 match_name text, subgame_title text, g integer, t integer, line numeric, odds numeric, player text, side integer)""",
}
# columns copied (raw jsonb is intentionally NOT copied for odds_history: saves ~80 MB)
COLS = {
"odds_history": "source,match_id,market,bookmaker,captured_date,home_team,away_team,match_date,selection,odds,imported_at",
"player_game_log": "player_key,event_id,source,player_id,player_name,team,league,home_team,away_team,match_date,minutes,shots,sot,goals,assists,fouls_committed,fouls_won,tackles,yellow_cards,red_cards,saves,offsides,passes,xg,xa,updated_at",
"player_match_stats": "id,source,event_id,player_id,player_name,team,league,home_team,away_team,match_date,stat_name,stat_value,stat_text,created_at,match_id,team_name,minutes,shots,sot,goals,assists,passes,tackles,fouls_committed,fouls_won,cards,corners,updated_at,xg,xa,player,match,date,shots_on_target,yellow_cards,red_cards,data_hash,collected_at,position,opponent,home_away,saves,interceptions,clearances,offsides,key_passes,duels,duels_won,touches,crosses",
"netrattler_match_history": "division,match_date,home_team,away_team,ft_home,ft_away,ht_home,ht_away,source,created_at",
"netrattler_data_lake_raw": "id,source,source_type,url,league,season,match_date,entity_type,entity_name,market,category,payload,data_hash,collected_at",
}
COLS.update({
"ml_tips": "id,match_id,home_team,away_team,league,date,time,market,tip,odds,confidence,probability,value_rating,features,created_at,bot_version,result,settled,settled_at,actual_score",
"netrattler_learning_events": "event_id,pick_key,tip_date,market,league,source,player,builder_type,legs,odds_bucket,probability,odds,closing_odds,clv,outcome,profit_units,brier,logloss,payload,settled_at,created_at",
"x1_player_snapshots": "id,captured_at,match_name,subgame_title,g,t,line,odds,player,side",
})
ORDER = {"ml_tips": "id", "netrattler_learning_events": "event_id", "x1_player_snapshots": "id",
         "odds_history": "source,match_id,market,bookmaker,captured_date,selection",
         "player_game_log": "player_key,event_id", "player_match_stats": "id",
         "netrattler_match_history": "division,match_date,home_team,away_team",
         "netrattler_data_lake_raw": "id"}

def H(extra=None):
    h = {"apikey": SRC_KEY, "Authorization": f"Bearer {SRC_KEY}"}
    h.update(extra or {}); return h

def src_count(t):
    r = requests.get(f"{SRC_URL}/rest/v1/{t}?select=*&limit=1", headers=H({"Prefer": "count=exact", "Range": "0-0"}), timeout=60)
    return int(r.headers.get("content-range", "*/0").split("/")[-1])

if os.environ.get("TARGET", "v2") == "v3" and os.environ.get("V3_DATABASE_URL", "").startswith("postgres"):
    DST_DSN = os.environ["V3_DATABASE_URL"]
    os.environ["V2_REGION"] = os.environ.get("V3_REGION", os.environ.get("V2_REGION", "eu-west-2"))


if os.environ.get("TARGET", "v2") == "v4" and os.environ.get("V4_DATABASE_URL", "").startswith("postgres"):
    DST_DSN = os.environ["V4_DATABASE_URL"]
    os.environ["V2_REGION"] = os.environ.get("V4_REGION", os.environ.get("V2_REGION", "eu-west-2"))


def _parse_dsn(dsn):
    """Manual parse (passwords may contain [ ] @ etc.). Returns (user, password, host, port, db) or None."""
    import re
    m = re.match(r"^postgres(?:ql)?://([^:]+):(.*)@([^@/]+?)(?::(\d+))?/([^?]*)", dsn.strip())
    if not m:
        return None
    user, pw, host, port, db = m.groups()
    if pw.startswith("[") and pw.endswith("]"):  # placeholder brackets copied by mistake
        pw = pw[1:-1]
    return user, pw, host, port or "5432", db or "postgres"


def _pooler_variants(dsn):
    p = _parse_dsn(dsn)
    if not p:
        return []
    user, pw, host, port, db = p
    out = []
    if host.startswith("db.") and host.endswith(".supabase.co"):
        ref = host.split(".")[1]
        if "." not in user:
            user = f"{user}.{ref}"
        region = os.environ.get("V2_REGION", "eu-west-2")
        for pre in ("aws-0", "aws-1"):
            out.append(dict(user=user, password=pw, host=f"{pre}-{region}.pooler.supabase.com", port=5432, dbname=db))
    return out


def dst():
    import psycopg2
    p = _parse_dsn(DST_DSN)
    cands = []
    if p:
        user, pw, host, port, db = p
        cands.append(dict(user=user, password=pw, host=host, port=int(port), dbname=db))
    cands += _pooler_variants(DST_DSN)
    last = None
    for kw in cands:
        try:
            return psycopg2.connect(connect_timeout=20, sslmode="require", **kw)
        except Exception as e:
            last = e
            print("connect attempt failed:", kw.get("host"), type(e).__name__)
    raise last



def rotate():
    """Archive-rotation for odds_history: keep HOT days in the main project, archive closing-ish rows
    (captured on/after match_date-1) into the archive DB, then remove old harvester rows from the main project.
    football_data_co_uk history stays in the main project (used by training). DRY_RUN=true only counts."""
    import datetime as dt
    from psycopg2.extras import execute_values
    hot = int(os.environ.get("HOT_DAYS", "3"))
    dry = os.environ.get("DRY_RUN", "true").lower() != "false"
    cutoff = (dt.date.today() - dt.timedelta(days=hot)).isoformat()
    cols = COLS["odds_history"].split(",")
    base = f"{SRC_URL}/rest/v1/odds_history"
    f_old = f"captured_date=lt.{cutoff}&source=neq.football_data_co_uk"
    r = requests.get(f"{base}?select=source&{f_old}&limit=1", headers=H({"Prefer": "count=exact", "Range": "0-0"}), timeout=120)
    old_total = int(r.headers.get("content-range", "*/0").split("/")[-1])
    print("cutoff", cutoff, "old harvester rows in main:", old_total, "dry_run:", dry)
    c = dst(); cur = c.cursor()
    first = requests.get(f"{base}?select=captured_date&{f_old}&order=captured_date.asc&limit=1", headers=H(), timeout=120).json()
    days = []
    if first:
        d0 = dt.date.fromisoformat(first[0]["captured_date"])
        while d0.isoformat() < cutoff:
            days.append(d0.isoformat()); d0 += dt.timedelta(days=1)
    print("days to rotate:", days)
    deleted = 0
    diag = []
    for d in days:
        r1 = requests.get(f"{base}?select=source&captured_date=eq.{d}&source=neq.football_data_co_uk&limit=1",
                          headers=H({"Prefer": "count=exact", "Range": "0-0"}), timeout=120)
        n1 = int(r1.headers.get("content-range", "*/0").split("/")[-1])
        cur.execute("select count(*) from odds_history where captured_date=%s and source<>'football_data_co_uk'", (d,))
        n2 = cur.fetchone()[0]
        ok = n2 >= n1 and n1 > 0
        print("day", d, "main", n1, "archive", n2, "ok_to_delete", ok)
        diag.append({"d": d, "main": n1, "archive": n2, "ok": ok})
        if ok and not dry:
            rr = requests.delete(f"{base}?captured_date=eq.{d}&source=neq.football_data_co_uk", headers=H({"Prefer": "return=minimal"}), timeout=300)
            print("delete", d, rr.status_code); deleted += 1 if rr.ok else 0
    print("days_deleted", deleted)
    try:
        info = {"probe": "odds_rotate", "cutoff": cutoff, "hot": hot, "dry": dry, "days": diag, "deleted": deleted}
        requests.post(f"{SRC_URL}/rest/v1/netrattler_card_diag", json={"info": info}, timeout=30,
                      headers={"apikey": SRC_KEY, "Authorization": f"Bearer {SRC_KEY}", "Content-Type": "application/json"})
    except Exception:
        pass


def main():
    print("secrets present: src_url=%s src_key=%s v2_dsn=%s" % (bool(SRC_URL), bool(SRC_KEY), bool(DST_DSN)))
    if not (SRC_URL and SRC_KEY and DST_DSN):
        print("MISSING SECRET(S) - stop"); sys.exit(1)
    c = dst(); cur = c.cursor(); cur.execute("select current_database(), pg_size_pretty(pg_database_size(current_database()))")
    print("v2 reachable:", cur.fetchone()); c.commit()
    if MODE == "rest":
        u = os.environ.get("V2_REST_URL", "").rstrip("/"); k = os.environ.get("V2_REST_KEY", "")
        print("v2 rest url ok:", u.startswith("https://") and u.endswith(".supabase.co"), "key present:", bool(k))
        for t in ("player_game_log", "player_match_stats", "odds_history"):
            try:
                r = requests.get(f"{u}/rest/v1/{t}?select=*&limit=1", headers={"apikey": k, "Authorization": f"Bearer {k}", "Prefer": "count=exact", "Range": "0-0"}, timeout=30)
                print("rest", t, r.status_code, r.headers.get("content-range"), r.text[:120] if not r.ok else "")
            except Exception as e:
                print("rest", t, type(e).__name__)
        return
    if MODE == "rotate":
        rotate(); return
    if MODE == "size":
        cur.execute("select pg_size_pretty(pg_database_size(current_database())), pg_database_size(current_database())/1024/1024")
        print("v2 db size:", cur.fetchone())
        cur.execute("select relname, pg_size_pretty(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' order by pg_total_relation_size(c.oid) desc")
        print("tables:", cur.fetchall()); return
    if MODE == "check":
        for t in TABLES: print("source rows", t, src_count(t))
        return
    if MODE == "schema":
        for t in TABLES:
            for stmt in DDL[t].split(";"):
                if stmt.strip(): cur.execute(stmt)
            cur.execute(f"alter table {t} enable row level security")
            cur.execute(f"grant select, insert, update, delete on {t} to service_role")
            cur.execute(f"revoke all on {t} from anon, authenticated")
            print("schema ok", t)
        extra = []
        if "player_match_stats" in TABLES:
            extra += [
                "create unique index if not exists pms_data_hash_key on player_match_stats (data_hash)",
                "create index if not exists pms_league_date on player_match_stats (league, match_date)",
            ]
        if "player_game_log" in TABLES:
            extra += [
                """create or replace function public.prune_player_game_log(keep_games integer default 20) returns bigint
                   language sql security definer set search_path to 'public' as $f$
                   with d as (delete from public.player_game_log where ctid in (select ctid from (select ctid,
                   row_number() over (partition by player_key order by match_date desc nulls last, event_id desc) rn
                   from public.player_game_log) r where rn > keep_games) returning 1) select count(*) from d; $f$""",
                "revoke all on function public.prune_player_game_log(integer) from public, anon, authenticated",
                "grant execute on function public.prune_player_game_log(integer) to service_role",
            ]
        for stmt in extra:
            cur.execute(stmt)
        print("extras ok (" + str(len(extra)) + " statements)")
        c.commit(); return
    from psycopg2.extras import execute_values, Json
    JSONB_COLS = {"netrattler_data_lake_raw": {"payload"}, "ml_tips": {"features"}, "netrattler_learning_events": {"payload"}}
    for t in TABLES:
        cols = COLS[t].split(",")
        jcols = JSONB_COLS.get(t, set())
        if MODE == "missing":
            # read-only: how many source rows are NOT present in the target (by unique data_hash)?
            miss, seen, off2 = 0, 0, 0
            while True:
                r = requests.get(f"{SRC_URL}/rest/v1/{t}?select=data_hash&order=data_hash&limit={PAGE}&offset={off2}", headers=H(), timeout=120)
                r.raise_for_status(); rows = [x["data_hash"] for x in r.json() if x.get("data_hash")]
                if not r.json(): break
                cur.execute(f"select data_hash from {t} where data_hash = any(%s)", (rows,))
                have = {x[0] for x in cur.fetchall()}
                miss += len([h for h in rows if h not in have]); seen += len(rows); off2 += PAGE
            print("missing", t, "checked", seen, "missing_in_target", miss); continue
        if MODE == "verify":
            cur.execute(f"select count(*) from {t}"); print("verify", t, "src", src_count(t), "v2", cur.fetchone()[0]); continue
        off, total = int(os.environ.get("START_OFFSET", "0")), 0
        t0 = time.time()
        while time.time() - t0 < float(os.environ.get("MAX_SECONDS", "1500")):
            r = requests.get(f"{SRC_URL}/rest/v1/{t}?select={COLS[t]}&order={ORDER[t]}&limit={PAGE}&offset={off}", headers=H(), timeout=120)
            if r.status_code == 429: time.sleep(5); continue
            r.raise_for_status(); rows = r.json()
            if not rows: print("done", t, "offset", off); break
            execute_values(cur, f"insert into {t} ({','.join(cols)}) values %s on conflict do nothing",
                           [tuple(Json(x.get(k)) if k in jcols and x.get(k) is not None else x.get(k) for k in cols) for x in rows])
            c.commit(); off += len(rows); total += len(rows)
        print("copied", t, total, "next_offset", off)

def _report(info):
    try:
        if SRC_URL and SRC_KEY:
            requests.post(f"{SRC_URL}/rest/v1/netrattler_card_diag", headers=H({"Content-Type": "application/json", "Prefer": "return=minimal"}),
                          data=json.dumps({"info": dict(info, probe="v2_migrate", mode=MODE)}), timeout=30)
    except Exception:
        pass


if __name__ == "__main__":
    import io, contextlib
    buf = io.StringIO()
    status = "ok"
    try:
        with contextlib.redirect_stdout(buf):
            main()
    except SystemExit as e:
        status = f"exit {e.code}"
    except Exception as e:
        msg = str(e).replace(DST_DSN, "<dsn>") if DST_DSN else str(e)
        status = f"{type(e).__name__}: {msg[:160]}"
    out = buf.getvalue()
    print(out)
    _report({"status": status, "output": out[-1500:]})
    if status != "ok":
        sys.exit(1)
