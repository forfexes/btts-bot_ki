"""Read-only probe: do ScraperFC (Sofascore) and soccerdata (ESPN) deliver per-player
fouls/tackles from a GitHub runner? Records only status, columns and a 3-row sample."""
import os, json, inspect, traceback, requests

out = {"probe": "github_stats", "scraperfc": {}, "soccerdata": {}}

try:
    from ScraperFC import Sofascore
    ss = Sofascore()
    out["scraperfc"]["methods"] = [m for m in dir(ss) if not m.startswith("_")]
    r = requests.get("https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-10-19",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    out["scraperfc"]["sofascore_http"] = r.status_code
    ev = [e for e in (r.json().get("events") or []) if (e.get("status") or {}).get("type") == "finished"] if r.ok else []
    out["scraperfc"]["finished_events"] = len(ev)
    if ev:
        mid = ev[0]["id"]
        fn = getattr(ss, "scrape_player_match_stats", None)
        if fn:
            df = fn(mid)
            out["scraperfc"]["cols"] = list(df.columns)[:80]
            out["scraperfc"]["rows"] = len(df)
            keep = [c for c in df.columns if any(k in c.lower() for k in ("name", "foul", "tackle", "shot", "pass"))][:12]
            out["scraperfc"]["sample"] = df[keep].head(3).astype(str).to_dict("records")
except Exception as e:
    out["scraperfc"]["error"] = (type(e).__name__ + ": " + str(e))[:300]

try:
    import soccerdata as sd
    espn = sd.ESPN(leagues="ENG-Premier League", seasons="2526", no_cache=True)
    sch = espn.read_schedule()
    out["soccerdata"]["schedule_rows"] = len(sch)
    done = sch.reset_index()
    gid = done["game_id"].dropna().iloc[-30] if len(done) > 30 else done["game_id"].dropna().iloc[0]
    lu = espn.read_lineup(match_id=int(gid))
    out["soccerdata"]["cols"] = list(lu.columns)[:80]
    out["soccerdata"]["rows"] = len(lu)
    keep = [c for c in lu.columns if any(k in str(c).lower() for k in ("foul", "tackle", "shot", "player"))][:12]
    out["soccerdata"]["sample"] = lu.reset_index()[[c for c in lu.reset_index().columns if c in keep or c == "player"]].head(3).astype(str).to_dict("records")
except Exception as e:
    out["soccerdata"]["error"] = (type(e).__name__ + ": " + str(e))[:300]

print(json.dumps(out, default=str)[:4000])
url = os.environ.get("SUPABASE_URL", "").rstrip("/"); key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
if url and key:
    print(requests.post(url + "/rest/v1/netrattler_card_diag", headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}, json={"info": json.loads(json.dumps(out, default=str))}, timeout=30).status_code)
