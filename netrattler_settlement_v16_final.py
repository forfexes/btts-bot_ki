"""NETRATTLER V25 targeted result/stat enrichment.

Uses undocumented public JSON endpoints from FotMob and SofaScore only as a
fallback for tips that could not be settled from Supabase. Calls are targeted:
daily fixture lists first, then detail/stat/lineup endpoints only for exact
home/away/date candidates. No fuzzy cross-match settlement is performed here.
"""
from __future__ import annotations
import os, re, time, unicodedata
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple
import requests

UA = {"User-Agent": "Mozilla/5.0 (NETRATTLER/25; settlement fallback)", "Accept": "application/json"}
TIMEOUT = float(os.getenv("RESULT_ENRICH_TIMEOUT", "7"))
MAX_DETAILS = int(os.getenv("RESULT_ENRICH_MAX_DETAILS", "120"))
SLEEP = float(os.getenv("RESULT_ENRICH_SLEEP", "0.08"))
USE_FOTMOB = os.getenv("RESULT_USE_FOTMOB", "true").lower() not in {"0","false","no"}
USE_SOFA = os.getenv("RESULT_USE_SOFASCORE_DETAIL", "true").lower() not in {"0","false","no"}


def norm(v: Any) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|cf|sc|afc|club|fk|sk|ac)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _same(a: Any, b: Any) -> bool:
    return bool(norm(a) and norm(a) == norm(b))


def _get(url: str, params=None) -> Dict[str, Any]:
    r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}


def _num(v):
    if isinstance(v, (int,float)): return v
    if isinstance(v, str):
        try: return float(v.replace("%","").replace(",",".").strip())
        except Exception: return None
    return None


def _sofa_stat_map(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    periods = payload.get("statistics") or []
    block = next((p for p in periods if str(p.get("period","")).upper() in {"ALL","FT","MATCH"}), periods[0] if periods else {})
    for group in block.get("groups") or []:
        for x in group.get("statisticsItems") or []:
            key = re.sub(r"[^a-z0-9]+", "", str(x.get("name") or x.get("key") or "").lower())
            h = _num(x.get("homeValue") if x.get("homeValue") is not None else x.get("home"))
            a = _num(x.get("awayValue") if x.get("awayValue") is not None else x.get("away"))
            if key in {"cornerkicks","corners"}: out.update(home_corners=h, away_corners=a)
            elif key in {"totalshots","shots"}: out.update(home_shots=h, away_shots=a)
            elif key in {"shotsontarget","shotsongoal"}: out.update(home_sot=h, away_sot=a)
            elif key in {"expectedgoals","expectedgoalsxg","xg"}: out.update(home_xg=h, away_xg=a)
    return out


def _sofa_players(payload: Dict[str, Any], event: Dict[str, Any], day: str) -> List[Dict[str, Any]]:
    out=[]
    home=(event.get("homeTeam") or {}).get("name",""); away=(event.get("awayTeam") or {}).get("name","")
    for side, team in (("home",home),("away",away)):
        block=payload.get(side) or {}
        rows=block.get("players") or [] if isinstance(block,dict) else []
        for row in rows:
            p=row.get("player") or {}; s=row.get("statistics") or {}
            if not p.get("name"): continue
            out.append({"source":"sofascore_live_fallback","match_date":day,"event_id":str(event.get("id") or ""),
                "home_team":home,"away_team":away,"team":team,"player_name":p.get("name"),
                "minutes":s.get("minutesPlayed"),"shots":s.get("totalShots"),"shots_on_target":s.get("shotsOnTarget"),
                "tackles":s.get("totalTackle"),"fouls_committed":s.get("fouls"),"fouls_won":s.get("wasFouled"),
                "yellow_cards":s.get("yellowCards"),"red_cards":s.get("redCards"),"goals":s.get("goals"),
                "assists":s.get("goalAssist"),"saves":s.get("saves")})
    return out


def _fotmob_flat_stats(payload: Dict[str, Any]) -> Dict[str, Any]:
    out={}; stats=(payload.get("content") or {}).get("stats") or payload.get("stats") or {}
    periods=stats.get("Periods") or stats.get("periods") or {}; groups=periods.get("All") or periods.get("all") or []
    for group in groups if isinstance(groups,list) else []:
        for x in (group.get("stats") or []) if isinstance(group,dict) else []:
            key=re.sub(r"[^a-z0-9]+","",str(x.get("title") or x.get("name") or "").lower())
            vals=x.get("stats") or x.get("values") or []
            if not isinstance(vals,list) or len(vals)<2: continue
            h,a=_num(vals[0]),_num(vals[1])
            if key in {"corners","cornerkicks"}: out.update(home_corners=h,away_corners=a)
            elif key in {"totalshots","shots"}: out.update(home_shots=h,away_shots=a)
            elif key in {"shotsongoal","shotsontarget"}: out.update(home_sot=h,away_sot=a)
            elif key in {"expectedgoalsxg","expectedgoals","xg"}: out.update(home_xg=h,away_xg=a)
    return out


def _fotmob_players(payload: Dict[str, Any], match_id: str, day: str, home: str, away: str) -> List[Dict[str, Any]]:
    out=[]; lu=(payload.get("content") or {}).get("lineup") or (payload.get("content") or {}).get("lineups") or {}
    for side, team in (("homeTeam",home),("awayTeam",away),("home",home),("away",away)):
        block=lu.get(side) if isinstance(lu,dict) else None
        rows=(block.get("players") or []) if isinstance(block,dict) else (block if isinstance(block,list) else [])
        for row in rows:
            p=row.get("player") if isinstance(row.get("player"),dict) else row; st=row.get("stats") or row.get("statistics") or {}
            name=p.get("name") or p.get("playerName") or row.get("name")
            if not name: continue
            def pick(*ks):
                for k in ks:
                    if st.get(k) is not None:return st.get(k)
                return None
            out.append({"source":"fotmob_live_fallback","match_date":day,"event_id":str(match_id),"home_team":home,"away_team":away,
                "team":team,"player_name":name,"minutes":pick("minutesPlayed","minutes"),"shots":pick("totalShots","shots"),
                "shots_on_target":pick("shotsOnTarget","shotsOnGoal"),"tackles":pick("tacklesWon","tackles","totalTackle"),
                "fouls_committed":pick("foulsCommitted","fouls"),"fouls_won":pick("foulsWon","wasFouled"),
                "yellow_cards":pick("yellowCards"),"red_cards":pick("redCards"),"goals":pick("goals"),"assists":pick("assists","goalAssist"),"saves":pick("saves")})
    return out


def collect_for_tips(tips: Sequence[Dict[str, Any]], match_parts, row_date, log=print, teams_match=None) -> Tuple[List[Dict[str,Any]],List[Dict[str,Any]]]:
    """Return enriched result rows + player rows for exact requested fixtures only."""
    wanted=defaultdict(list)
    def same(a,b):
        if _same(a,b): return True
        if teams_match:
            try: return bool(teams_match(a,b))
            except Exception: return False
        return False
    for t in tips:
        h,a,_=match_parts(t); d=row_date(t)
        if h and a and d: wanted[d].append((h,a))
    results=[]; players=[]; details=0
    for day, fixtures in sorted(wanted.items()):
        found=set()
        if USE_FOTMOB:
            try:
                data=_get("https://www.fotmob.com/api/matches", {"date":day.replace("-","")})
                leagues=data.get("leagues") or []
                for lg in leagues:
                    for m in lg.get("matches") or []:
                        h=(m.get("home") or {}).get("name"); a=(m.get("away") or {}).get("name")
                        target=next(((wh,wa) for wh,wa in fixtures if same(wh,h) and same(wa,a)),None)
                        if not target: continue
                        status=m.get("status") or {}; finished=bool(status.get("finished")) or "full" in str((status.get("reason") or {}).get("long") or status.get("reason") or "").lower()
                        hs=(m.get("home") or {}).get("score"); aw=(m.get("away") or {}).get("score")
                        if not finished or hs is None or aw is None: continue
                        row={"source":"FotMob","_result_table":"FotMob","match_date":day,"home_team":h,"away_team":a,"home_score":hs,"away_score":aw,"raw":m}
                        mid=str(m.get("id") or "")
                        if mid and details<MAX_DETAILS:
                            try:
                                det=_get("https://www.fotmob.com/api/matchDetails", {"matchId":mid}); details+=1
                                row.update(_fotmob_flat_stats(det)); players.extend(_fotmob_players(det,mid,day,h,a)); time.sleep(SLEEP)
                            except Exception: pass
                        results.append(row); found.add((norm(h),norm(a)))
            except Exception as e: log(f"FotMob enrichment {day}: {str(e)[:90]}")
        if USE_SOFA:
            try:
                data=_get(f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{day}")
                for ev in data.get("events") or []:
                    h=(ev.get("homeTeam") or {}).get("name"); a=(ev.get("awayTeam") or {}).get("name")
                    target=next(((wh,wa) for wh,wa in fixtures if same(wh,h) and same(wa,a)),None)
                    if not target: continue
                    status=str((ev.get("status") or {}).get("type") or "").lower()
                    hs=(ev.get("homeScore") or {}).get("current"); aw=(ev.get("awayScore") or {}).get("current")
                    if status!="finished" or hs is None or aw is None: continue
                    row={"source":"SofaScoreDetail","_result_table":"SofaScoreDetail","match_date":day,"home_team":h,"away_team":a,
                         "home_score":hs,"away_score":aw,"home_score_ht":(ev.get("homeScore") or {}).get("period1"),"away_score_ht":(ev.get("awayScore") or {}).get("period1"),"raw":ev}
                    eid=str(ev.get("id") or "")
                    if eid and details<MAX_DETAILS:
                        try:
                            st=_get(f"https://www.sofascore.com/api/v1/event/{eid}/statistics"); row.update(_sofa_stat_map(st))
                            try: players.extend(_sofa_players(_get(f"https://www.sofascore.com/api/v1/event/{eid}/lineups"),ev,day))
                            except Exception: pass
                            details+=1; time.sleep(SLEEP)
                        except Exception: pass
                    results.append(row)
            except Exception as e: log(f"SofaScore detail enrichment {day}: {str(e)[:90]}")
    log(f"Target enrichment: results={len(results)} player_rows={len(players)} detail_calls={details}")
    return results,players
