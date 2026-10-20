"""Fill missing half-time scores of ESPN match_results rows from the ESPN public scoreboard (linescores).
Only real reported period-1 scores are written; nothing is estimated."""
import os, datetime as dt
import requests
_ESPN_LEAGUES = ("eng.1", "eng.2", "eng.3", "esp.1", "esp.2", "ger.1", "ger.2", "ita.1", "ita.2", "fra.1", "fra.2",
                 "ned.1", "por.1", "bel.1", "sco.1", "tur.1", "uefa.champions", "uefa.europa", "uefa.europa.conf",
                 "usa.1", "swe.1", "nor.1", "den.1", "aut.1", "sui.1", "gre.1")

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
SB = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SK = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or ""
H = {"apikey": SK, "Authorization": f"Bearer {SK}", "Content-Type": "application/json"}


def ht_from_event(ev):
    """(home_ht, away_ht) from the first linescore period of a completed event, else None."""
    comp = (ev.get("competitions") or [{}])[0]
    if not (comp.get("status") or ev.get("status") or {}).get("type", {}).get("completed"):
        return None
    vals = {}
    for c in comp.get("competitors") or []:
        ls = c.get("linescores") or []
        if len(ls) < 2 or not isinstance(ls[0].get("value"), (int, float)):
            return None
        vals[c.get("homeAway")] = int(ls[0]["value"])
    if "home" in vals and "away" in vals:
        return vals["home"], vals["away"]
    return None


def run(days=14):
    if not SB or not SK:
        return 0
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    rows = requests.get(f"{SB}/rest/v1/match_results", headers=H, timeout=30, params={
        "select": "id,event_id,match_date", "source": "eq.espn", "ht_home": "is.null",
        "match_date": f"gte.{since}", "limit": "2000"}).json()
    if not isinstance(rows, list) or not rows:
        return 0
    wanted = {str(r["event_id"]): r for r in rows if r.get("event_id")}
    dates = sorted({str(r["match_date"])[:10] for r in rows})
    done = 0
    for d in dates:
        for slug in _ESPN_LEAGUES:
            if not wanted:
                break
            try:
                sb = requests.get(f"{BASE}/{slug}/scoreboard", params={"dates": d.replace("-", "")}, timeout=15)
                if not sb.ok:
                    continue
                for ev in sb.json().get("events", []):
                    r = wanted.get(str(ev.get("id")))
                    ht = ht_from_event(ev) if r else None
                    if not ht:
                        continue
                    p = requests.patch(f"{SB}/rest/v1/match_results", headers=H, timeout=20,
                                       params={"id": f"eq.{r['id']}"}, json={"ht_home": ht[0], "ht_away": ht[1]})
                    if p.ok:
                        done += 1
                        wanted.pop(str(ev.get("id")), None)
            except Exception as exc:
                print("espn ht", slug, str(exc)[:80])
    print(f"ESPN HT backfill: {done} rows")
    return done


if __name__ == "__main__":
    run()
