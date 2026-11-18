#!/usr/bin/env python3
"""Read-only live-feed shape/availability diagnostics; no credentials, no sends."""
import datetime as dt
import json
import re
import requests

DAY=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
ISO=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
HEADERS={"Accept":"application/json", "User-Agent":"NETRATTLER-LMG/1.0"}

SOURCES={
    "espn_all":("https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard", {"dates":DAY,"limit":"1000"}),
    "espn_eng1":("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard", {"dates":DAY}),
    "espn_uefa":("https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard", {"dates":DAY}),
    "fotmob":("https://www.fotmob.com/api/data/matches",{"date":DAY}),
    "sofa":(f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{ISO}",None),
    "livescore":(f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{DAY}/0",{"MD":"1"}),
}
def fetch(tag,url,params):
    try:
        r=requests.get(url,params=params,timeout=13,headers=HEADERS)
        if not r.ok: return {"status":r.status_code}
        body=r.json()
        if tag.startswith("espn"):
            events=body.get("events") or []
            live=[e for e in events if ((e.get("status") or {}).get("type") or {}).get("state")=="in"]
            return {"status":200,"events":len(events),"live":len(live),
                    "sample":[{"clock":e.get("status",{}).get("displayClock"),
                               "state":e.get("status",{}).get("type"),
                               "period":e.get("status",{}).get("period")} for e in live[:2]]}
        if tag=="fotmob":
            leagues=body.get("leagues") or []
            matches=[m for l in leagues for m in l.get("matches") or []]
            live=[m for m in matches if (m.get("status") or {}).get("ongoing") is True]
            def minute(match):
                clock = str(((match.get("status") or {}).get("liveTime") or {}).get("short") or "")
                found = re.search(r"\d+", clock)
                return int(found.group()) if found else 0
            live.sort(key=lambda m: abs(minute(m)-75))
            shape={}
            if live:
                details=requests.get("https://www.fotmob.com/api/data/matchDetails",
                                     params={"matchId":live[0].get("id")}, headers=HEADERS,timeout=13)
                shape={"http":details.status_code}
                if details.ok:
                    payload=details.json()
                    root=payload.get("content") or {}
                    stats=root.get("stats") or {}
                    shape.update({"content_keys":list(root)[:20],
                                  "stats_keys":list(stats)[:12] if isinstance(stats,dict) else [],
                                  "stats_sample":str(stats)[:2400]})
            return {"status":200,"leagues":len(leagues),"matches":len(matches),"live":len(live),
                    "sample":[{"status":m.get("status"),"home":(m.get("home") or {}).get("name"),
                               "away":(m.get("away") or {}).get("name"),"id":m.get("id")} for m in live[:2]],
                    "detail":shape}
        if tag=="sofa":
            events=body.get("events") or []
            live=[e for e in events if (e.get("status") or {}).get("type")=="inprogress"]
            return {"status":200,"events":len(events),"live":len(live),
                    "sample":[{"status":e.get("status"),"period":e.get("currentPeriodStartTimestamp"),
                               "id":e.get("id")} for e in live[:2]]}
        if tag=="livescore":
            stages=body.get("Stages") or []
            evs=[e for s in stages for e in s.get("Events") or []]
            return {"status":200,"events":len(evs),
                    "sample":[{"Eps":e.get("Eps"),"Esid":e.get("Esid")} for e in evs[:2]]}
        return {"status":200,"top_keys":list(body)[:10]}
    except Exception as exc:
        return {"error":type(exc).__name__,"message":str(exc)[:90]}
for name,(url,params) in SOURCES.items():
    print("LMG_SOURCE_PROBE",name,json.dumps(fetch(name,url,params),ensure_ascii=False)[:6000],flush=True)
